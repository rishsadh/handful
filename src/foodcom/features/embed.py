"""Recipe embedding cache.

A cached vector is keyed by `(recipe_id, text_sha256, model_id, model_revision)`. All four
matter: the same recipe re-rendered after a tag-rule change is a different text and must
be re-encoded, and the same text under a different model revision is a different vector.
Reusing a stale vector would silently mix two models' outputs into one result table.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from foodcom.features.encoders import Encoder
from foodcom.utils import logging as flog

log = flog.get_logger(__name__)

# Chunk size for progress reporting. Large enough that per-chunk overhead is
# negligible, small enough that a long run reports every minute or two.
_PROGRESS_CHUNK = 5000

_INDEX = "index.parquet"
_VECTORS = "vectors.npy"
_META = "meta.json"


@dataclass
class EmbeddingStore:
    """Recipe vectors plus the identity of what produced them."""

    recipe_ids: np.ndarray  # (n,) int64
    vectors: np.ndarray  # (n, d) float32, unit-normalised
    text_sha256: np.ndarray  # (n,) object
    provenance: dict[str, Any]

    def __post_init__(self) -> None:
        if len(self.recipe_ids) != self.vectors.shape[0]:
            raise ValueError("recipe_ids and vectors disagree in length")
        self._pos = {int(r): i for i, r in enumerate(self.recipe_ids)}

    @property
    def dimension(self) -> int:
        return int(self.vectors.shape[1])

    def position(self, recipe_id: int) -> int:
        return self._pos[int(recipe_id)]

    def has(self, recipe_id: int) -> bool:
        return int(recipe_id) in self._pos

    def matrix_for(self, recipe_ids: np.ndarray) -> np.ndarray:
        """Vectors for the given ids, in the given order. Unknown ids raise."""
        idx = np.fromiter((self._pos[int(r)] for r in recipe_ids), dtype="int64",
                          count=len(recipe_ids))
        return self.vectors[idx]

    def subset(self, recipe_ids: np.ndarray) -> EmbeddingStore:
        idx = np.fromiter((self._pos[int(r)] for r in recipe_ids), dtype="int64",
                          count=len(recipe_ids))
        return EmbeddingStore(
            recipe_ids=np.asarray(recipe_ids, dtype="int64"),
            vectors=self.vectors[idx],
            text_sha256=self.text_sha256[idx],
            provenance=self.provenance,
        )

    # ---------------------------------------------------------------- persistence

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / _VECTORS, self.vectors)
        pd.DataFrame(
            {"recipe_id": self.recipe_ids, "text_sha256": self.text_sha256}
        ).to_parquet(directory / _INDEX, index=False)
        (directory / _META).write_text(
            json.dumps(self.provenance, indent=2, default=str), encoding="utf-8"
        )
        log.info("embedding store saved: %d vectors, dim %d -> %s",
                 len(self.recipe_ids), self.dimension, directory)
        return directory

    @classmethod
    def load(cls, directory: Path) -> EmbeddingStore:
        idx = pd.read_parquet(directory / _INDEX)
        return cls(
            recipe_ids=idx["recipe_id"].to_numpy(dtype="int64"),
            vectors=np.load(directory / _VECTORS),
            text_sha256=idx["text_sha256"].to_numpy(),
            provenance=json.loads((directory / _META).read_text(encoding="utf-8")),
        )

    @classmethod
    def exists(cls, directory: Path) -> bool:
        return all((directory / f).exists() for f in (_INDEX, _VECTORS, _META))


def cache_key_frame(rendered: pd.DataFrame, provenance: dict[str, Any]) -> pd.DataFrame:
    """The four-part cache key, materialised so a mismatch is inspectable."""
    return pd.DataFrame(
        {
            "recipe_id": rendered["recipe_id"].to_numpy(dtype="int64"),
            "text_sha256": rendered["text_sha256"].to_numpy(),
            "model_id": provenance.get("model_id"),
            "model_revision": provenance.get("model_revision"),
        }
    )


def build_embeddings(
    rendered: pd.DataFrame,
    encoder: Encoder,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
) -> EmbeddingStore:
    """Encode every rendered recipe text, reusing cached vectors whose key still matches.

    Returns a store covering exactly the rows in `rendered`, in that order.
    """
    provenance = encoder.provenance()
    ids = rendered["recipe_id"].to_numpy(dtype="int64")
    hashes = rendered["text_sha256"].to_numpy()
    texts = rendered["text"].tolist()

    cached: dict[tuple[int, str], np.ndarray] = {}
    if use_cache and cache_dir is not None and EmbeddingStore.exists(cache_dir):
        old = EmbeddingStore.load(cache_dir)
        same_model = (
            old.provenance.get("model_id") == provenance.get("model_id")
            and old.provenance.get("model_revision") == provenance.get("model_revision")
        )
        if same_model:
            for i, rid in enumerate(old.recipe_ids):
                cached[(int(rid), str(old.text_sha256[i]))] = old.vectors[i]
            log.info("embedding cache: %d reusable vectors", len(cached))
        else:
            log.warning(
                "embedding cache ignored: model identity changed (%s@%s -> %s@%s)",
                old.provenance.get("model_id"),
                old.provenance.get("model_revision"),
                provenance.get("model_id"),
                provenance.get("model_revision"),
            )

    need = [i for i in range(len(ids)) if (int(ids[i]), str(hashes[i])) not in cached]
    log.info("embedding: %d cached, %d to encode", len(ids) - len(need), len(need))

    dim = encoder.dimension if not need else None
    new_vectors: dict[int, np.ndarray] = {}
    if need:
        # Encode in chunks so a long pass reports progress. The real catalogue took over
        # two hours on CPU and printed nothing at all the first time it ran, which left no
        # way to tell a slow job from a hung one except by reading process CPU counters.
        #
        # Any encoder that has to be fitted (TF-IDF) is fitted on the FULL set first.
        # Fitting inside the loop would build the vocabulary from the first chunk alone
        # and silently change what every later chunk means.
        fit = getattr(encoder, "fit", None)
        if callable(fit):
            fit([texts[i] for i in need])

        t0 = time.perf_counter()
        for start in range(0, len(need), _PROGRESS_CHUNK):
            block = need[start : start + _PROGRESS_CHUNK]
            encoded = encoder.encode([texts[i] for i in block])
            if dim is None:
                dim = encoded.shape[1]
            for slot, i in enumerate(block):
                new_vectors[i] = encoded[slot]

            done = start + len(block)
            elapsed = time.perf_counter() - t0
            rate = done / elapsed if elapsed > 0 else 0.0
            remaining = (len(need) - done) / rate if rate > 0 else float("nan")
            log.info(
                "encoding %d/%d (%.1f%%) - %.0f texts/s, ~%.0f min remaining",
                done, len(need), 100.0 * done / len(need), rate, remaining / 60.0,
            )

    if dim is None:  # every vector came from cache
        dim = next(iter(cached.values())).shape[0]

    vectors = np.zeros((len(ids), dim), dtype="float32")
    for i in range(len(ids)):
        vectors[i] = new_vectors[i] if i in new_vectors else cached[(int(ids[i]), str(hashes[i]))]

    store = EmbeddingStore(
        recipe_ids=ids,
        vectors=vectors,
        text_sha256=hashes,
        provenance={**provenance, "n_recipes": len(ids)},
    )
    if cache_dir is not None:
        store.save(cache_dir)
    return store
