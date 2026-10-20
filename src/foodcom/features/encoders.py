"""Text encoders.

Three implementations behind one interface:

* `SentenceTransformerEncoder` - the real one. A frozen pretrained `all-MiniLM-L6-v2`.
  It is not a generator, not a satisfaction predictor and not a probability model. It maps
  text to a unit vector, nothing more.
* `TfidfEncoder` - a separately labelled ablation / fallback. Results produced with it are
  reported as TFIDF_*, never as the sentence-transformer model.
* `DeterministicTestEncoder` - **unit tests only**. It hashes text into a vector so the
  optimisation and evaluation code can be tested without a 2.5 GB download. It has no
  semantic content and must never appear in a research run; `is_research_grade` is False
  and the evaluation harness refuses it outside tests.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from foodcom.utils import logging as flog
from foodcom.utils.config import ModelCfg

log = flog.get_logger(__name__)


def l2_normalise(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalisation. A zero row stays zero rather than becoming NaN."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms == 0.0, 1.0, norms)
    return matrix / safe


class Encoder(ABC):
    """A frozen text encoder producing unit-normalised vectors."""

    name: str = "abstract"
    is_research_grade: bool = False

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) float32 array of unit-normalised vectors."""

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def provenance(self) -> dict[str, Any]:
        """Everything needed to identify this encoder in a run manifest."""


class SentenceTransformerEncoder(Encoder):
    name = "sentence_transformers"
    is_research_grade = True

    def __init__(self, cfg: ModelCfg) -> None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError(
                "sentence-transformers and torch are required for real AI scoring runs.\n"
                "Install them with:  python tasks.py setup-ai\n"
                "Do not substitute the TF-IDF ablation and report it as the AI model."
            ) from exc

        self.cfg = cfg
        enc = cfg.encoder
        device = enc.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        kwargs: dict[str, Any] = {"device": device}
        if enc.model_revision:
            kwargs["revision"] = enc.model_revision
        self.model = SentenceTransformer(enc.model_id, **kwargs)
        self.model.max_seq_length = enc.max_seq_length
        self.model.eval()
        for param in self.model.parameters():
            param.requires_grad_(False)

        self._resolved_revision = self._resolve_revision(enc.model_id, enc.model_revision)
        if not enc.model_revision:
            log.warning(
                "config/model.yaml -> encoder.model_revision is null. Resolved revision is "
                "%s; pin it before any final-evaluation run.",
                self._resolved_revision,
            )
        self._torch_version = torch.__version__

    @staticmethod
    def _resolve_revision(model_id: str, requested: str | None) -> str | None:
        if requested:
            return requested
        try:  # pragma: no cover - network/cache dependent
            from huggingface_hub import HfApi

            return HfApi().model_info(model_id).sha
        except Exception:
            return None

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(
            texts,
            batch_size=self.cfg.encoder.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self.cfg.encoder.normalize_embeddings,
            show_progress_bar=False,
        ).astype("float32")
        return vecs if self.cfg.encoder.normalize_embeddings else l2_normalise(vecs)

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    @property
    def tokeniser(self) -> Any:
        return self.model.tokenizer

    def provenance(self) -> dict[str, Any]:
        import importlib.metadata as md

        def _v(pkg: str) -> str:
            try:
                return md.version(pkg)
            except Exception:
                return "not-installed"

        return {
            "backend": self.name,
            "model_id": self.cfg.encoder.model_id,
            "model_revision": self._resolved_revision,
            "revision_pinned_in_config": self.cfg.encoder.model_revision is not None,
            "max_seq_length": self.cfg.encoder.max_seq_length,
            "dimension": self.dimension,
            "device": self.device,
            "precision": self.cfg.encoder.precision,
            "normalize_embeddings": self.cfg.encoder.normalize_embeddings,
            "sentence_transformers_version": _v("sentence-transformers"),
            "transformers_version": _v("transformers"),
            "torch_version": self._torch_version,
            "is_research_grade": True,
            "note": (
                "Frozen pretrained encoder. Postdates the review period and may have seen "
                "public web text in pretraining: this is retrospective offline benchmarking, "
                "not a historically deployable system."
            ),
        }


class TfidfEncoder(Encoder):
    """TF-IDF + SVD. A labelled ablation, never a silent stand-in for the AI model."""

    name = "tfidf"
    is_research_grade = True

    def __init__(self, cfg: ModelCfg, n_components: int = 128, seed: int = 42) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        ab = cfg.ablation.tfidf
        self.cfg = cfg
        self.seed = seed
        self.n_components = n_components
        self._vec = TfidfVectorizer(
            max_features=ab.max_features,
            ngram_range=tuple(ab.ngram_range),
            min_df=ab.min_df,
        )
        self._svd = TruncatedSVD(n_components=n_components, random_state=seed)
        self._fitted = False
        self._dim = n_components

    def fit(self, texts: list[str]) -> TfidfEncoder:
        matrix = self._vec.fit_transform(texts)
        n_comp = min(self.n_components, max(matrix.shape[1] - 1, 1))
        if n_comp != self.n_components:
            from sklearn.decomposition import TruncatedSVD

            self._svd = TruncatedSVD(n_components=n_comp, random_state=self.seed)
        self._svd.fit(matrix)
        self._dim = int(self._svd.n_components)
        self._fitted = True
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            self.fit(texts)
        return l2_normalise(self._svd.transform(self._vec.transform(texts)).astype("float32"))

    @property
    def dimension(self) -> int:
        return self._dim

    def provenance(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "model_id": "tfidf+truncated_svd",
            "model_revision": None,
            "dimension": self._dim,
            "max_features": self.cfg.ablation.tfidf.max_features,
            "ngram_range": list(self.cfg.ablation.tfidf.ngram_range),
            "min_df": self.cfg.ablation.tfidf.min_df,
            "seed": self.seed,
            "is_research_grade": True,
            "note": "Separately labelled ablation. Report as TFIDF_*, never as the AI model.",
        }


class DeterministicTestEncoder(Encoder):
    """Hash-based encoder for unit tests only.

    Vectors are a deterministic function of the text, so caching, scoring, LP and metric
    code can be exercised without downloading a model. There is no semantic content here
    whatsoever. `is_research_grade` is False and the evaluation harness rejects it unless
    explicitly told it is running a test.
    """

    name = "deterministic_test"
    is_research_grade = False

    def __init__(self, dimension: int = 32) -> None:
        self._dim = dimension

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype="float32")
        for i, text in enumerate(texts):
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            # Stretch the digest deterministically to the requested width.
            stream = b"".join(
                hashlib.sha256(digest + bytes([j])).digest()
                for j in range((self._dim * 4) // 32 + 1)
            )
            vals = np.frombuffer(stream[: self._dim * 4], dtype="uint32").astype("float64")
            out[i] = (vals / np.iinfo(np.uint32).max - 0.5).astype("float32")
        return l2_normalise(out)

    @property
    def dimension(self) -> int:
        return self._dim

    def provenance(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "model_id": "sha256-hash-projection",
            "model_revision": None,
            "dimension": self._dim,
            "is_research_grade": False,
            "note": "SYNTHETIC TEST ENCODER. Never a research result.",
        }


def build_encoder(cfg: ModelCfg, *, backend: str | None = None) -> Encoder:
    """Construct the configured encoder."""
    chosen = backend or cfg.encoder.backend
    if chosen == "sentence_transformers":
        return SentenceTransformerEncoder(cfg)
    if chosen == "tfidf":
        return TfidfEncoder(cfg)
    if chosen == "deterministic_test":
        return DeterministicTestEncoder()
    raise ValueError(f"unknown encoder backend {chosen!r}")
