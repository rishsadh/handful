"""Typed configuration loading.

Every config file is validated on load. A malformed protocol is a hard failure, not a
warning: silently defaulting a protocol value is how a research population changes
without anyone noticing.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

UNRECORDED = "UNRECORDED"


def repo_root() -> Path:
    """The repository root, resolved from this file's location."""
    return Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- research


class DatasetCfg(_Strict):
    name: str
    uploader: str
    source_url: str
    kaggle_version: str
    download_date: str
    licence_text: str
    licence_permits_redistribution: bool | None = None
    required_files: list[str]

    @property
    def provenance_complete(self) -> bool:
        return all(
            v != UNRECORDED
            for v in (self.kaggle_version, self.download_date, self.licence_text)
        )

    def missing_provenance_fields(self) -> list[str]:
        out = []
        for name in ("kaggle_version", "download_date", "licence_text"):
            if getattr(self, name) == UNRECORDED:
                out.append(name)
        return out


class StageWindow(_Strict):
    history_end_exclusive: dt.date
    label_start: dt.date
    label_end_inclusive: dt.date | None = None

    @model_validator(mode="after")
    def _ordered(self) -> StageWindow:
        if self.label_start < self.history_end_exclusive:
            raise ValueError(
                f"label_start {self.label_start} precedes history_end_exclusive "
                f"{self.history_end_exclusive}: history and labels would overlap"
            )
        if self.label_end_inclusive is not None and self.label_end_inclusive < self.label_start:
            raise ValueError("label_end_inclusive precedes label_start")
        return self


class SweepPoint(_Strict):
    k: int = Field(gt=0)
    b: int = Field(gt=0)


class ProtocolCfg(_Strict):
    positive_ratings: list[int]
    observed_nonpositive_ratings: list[int]
    unknown_rating_value: int
    min_distinct_positive_history: int = Field(ge=1)
    shortlist_size_k: int = Field(gt=0)
    band_cap_b: int = Field(gt=0)
    band_edges: list[float]
    band_labels: list[str]
    stages: dict[str, StageWindow]
    max_users: int | None
    cohort_seed: int
    primary_metric: str
    secondary_metric: str
    macro_average: bool
    methods: list[str]
    random_repeats: int = Field(gt=0)
    random_seed: int
    paired_comparisons: list[list[str]]
    bootstrap_resamples: int = Field(gt=0)
    bootstrap_seed: int
    bootstrap_ci: float = Field(gt=0, lt=1)

    @field_validator("band_edges")
    @classmethod
    def _edges_increasing(cls, v: list[float]) -> list[float]:
        if list(v) != sorted(v) or len(set(v)) != len(v):
            raise ValueError("band_edges must be strictly increasing")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> ProtocolCfg:
        if len(self.band_labels) != len(self.band_edges) + 1:
            raise ValueError("band_labels must be exactly one longer than band_edges")
        if set(self.positive_ratings) & set(self.observed_nonpositive_ratings):
            raise ValueError("a rating cannot be both positive and non-positive")
        if self.unknown_rating_value in self.positive_ratings:
            raise ValueError("the unknown rating value must never count as positive")
        if "validation" not in self.stages or "final" not in self.stages:
            raise ValueError("stages must define both 'validation' and 'final'")
        val, fin = self.stages["validation"], self.stages["final"]
        if fin.history_end_exclusive < val.history_end_exclusive:
            raise ValueError("final history must extend at least as far as validation history")
        for pair in self.paired_comparisons:
            if len(pair) != 2:
                raise ValueError(f"paired_comparisons entry {pair} is not a pair")
            for m in pair:
                if m not in self.methods:
                    raise ValueError(f"paired comparison references unknown method {m!r}")
        return self


class SensitivityCfg(_Strict):
    length_sweep: list[SweepPoint]
    cap_sweep: list[SweepPoint]


class PathsCfg(_Strict):
    raw_dir: str
    interim_dir: str
    processed_dir: str
    quarantine_dir: str
    runs_dir: str
    figures_dir: str
    reports_dir: str
    docs_dir: str


class ResearchCfg(_Strict):
    protocol_version: str
    dataset: DatasetCfg
    protocol: ProtocolCfg
    sensitivity: SensitivityCfg
    paths: PathsCfg


# --------------------------------------------------------------------------- cleaning


class CleaningCfg(BaseModel):
    """Cleaning rules.

    Kept as a permissive model on purpose: the ledger stage lists are data, and adding a
    documented stage should not require a code change. The fields the pipeline actually
    reads are declared and validated; the rest travels along for the run manifest.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    recipes: dict[str, Any]
    interactions: dict[str, Any]

    @property
    def recipe_stages(self) -> list[str]:
        return list(self.recipes["recipe_stages"])

    @property
    def interaction_stages(self) -> list[str]:
        return list(self.interactions["interaction_stages"])

    @model_validator(mode="after")
    def _required_keys(self) -> CleaningCfg:
        for key in ("required_for_core", "minutes", "list_fields", "recipe_stages"):
            if key not in self.recipes:
                raise ValueError(f"cleaning.recipes is missing {key!r}")
        for key in ("required_columns", "rating", "repeat_pairs", "interaction_stages"):
            if key not in self.interactions:
                raise ValueError(f"cleaning.interactions is missing {key!r}")
        if self.recipes.get("parser") not in ("ast.literal_eval", None):
            raise ValueError("only ast.literal_eval is an accepted list parser")
        return self


# --------------------------------------------------------------------------- model


class EncoderCfg(_Strict):
    backend: Literal["sentence_transformers", "tfidf", "deterministic_test"]
    model_id: str
    model_revision: str | None
    max_seq_length: int = Field(gt=0)
    normalize_embeddings: bool
    device: str
    precision: str
    batch_size: int = Field(gt=0)


class TextRenderCfg(_Strict):
    field_order: list[str]
    separator: str
    description_max_chars: int = Field(ge=0)
    lowercase: bool
    forbidden_fields: list[str]

    @model_validator(mode="after")
    def _no_forbidden_in_order(self) -> TextRenderCfg:
        overlap = set(self.field_order) & set(self.forbidden_fields)
        if overlap:
            raise ValueError(f"rendered text would include forbidden fields: {sorted(overlap)}")
        return self


class ScoringCfg(_Strict):
    formula: Literal["half_shifted_cosine"]
    clip_range: tuple[float, float]
    profile: Literal["mean_of_positive_history"]
    profile_weights: Literal["equal"]
    cold_start_policy: str


class EmbeddingCacheCfg(_Strict):
    enabled: bool
    dir: str
    key_fields: list[str]


class SolverCfg(_Strict):
    library: str
    method: str
    tolerance: float = Field(gt=0)
    primal_band_pruning: bool
    dual_uses_full_problem: bool
    tie_break: str


class TfidfAblationCfg(_Strict):
    enabled: bool
    max_features: int
    ngram_range: tuple[int, int]
    min_df: int


class AblationCfg(_Strict):
    tfidf: TfidfAblationCfg


class ModelCfg(_Strict):
    encoder: EncoderCfg
    text_render: TextRenderCfg
    scoring: ScoringCfg
    embedding_cache: EmbeddingCacheCfg
    solver: SolverCfg
    ablation: AblationCfg


# --------------------------------------------------------------------------- tags


class TagRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unknown_tag_policy: Literal["exclude", "include"]
    max_tags_per_recipe: int = Field(ge=0)
    tag_order: str
    deny_regex: list[str]
    allow_exact: list[str]
    allow_prefix: list[str]

    # Compiled once at construction: `allowed` is called once per tag per recipe, which is
    # millions of calls on the real catalogue, and recompiling regexes there is the
    # difference between seconds and minutes.
    _deny: tuple[re.Pattern[str], ...] = PrivateAttr(default=())
    _allow: frozenset[str] = PrivateAttr(default=frozenset())
    _prefixes: tuple[str, ...] = PrivateAttr(default=())

    def model_post_init(self, __context: Any) -> None:
        self._deny = tuple(re.compile(p) for p in self.deny_regex)
        self._allow = frozenset(t.strip().lower() for t in self.allow_exact)
        self._prefixes = tuple(p.strip().lower() for p in self.allow_prefix)

    def compiled_deny(self) -> list[re.Pattern[str]]:
        return list(self._deny)

    def allowed(self, tag: str) -> bool:
        """True when `tag` may appear in the rendered recipe text.

        Deny rules are evaluated first and are absolute.
        """
        if not isinstance(tag, str):
            return False
        t = tag.strip().lower()
        if not t:
            return False
        for pat in self._deny:
            if pat.search(t):
                return False
        if t in self._allow:
            return True
        if any(t.startswith(p) for p in self._prefixes):
            return True
        return self.unknown_tag_policy == "include"


# --------------------------------------------------------------------------- bundle


class Configs(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    research: ResearchCfg
    cleaning: CleaningCfg
    model: ModelCfg
    tags: TagRules
    root: Path

    def path(self, key: str) -> Path:
        """Resolve a `paths` key from research.yaml to an absolute path."""
        return self.root / getattr(self.research.paths, key)

    def as_snapshot(self) -> dict[str, Any]:
        """A JSON-serialisable snapshot of every config, for the run manifest."""
        return {
            "research": self.research.model_dump(mode="json"),
            "cleaning": self.cleaning.model_dump(mode="json"),
            "model": self.model.model_dump(mode="json"),
            "tags": self.tags.model_dump(mode="json"),
        }


def load_configs(config_dir: Path | str | None = None, root: Path | None = None) -> Configs:
    """Load and validate every configuration file."""
    root = Path(root) if root is not None else repo_root()
    cdir = Path(config_dir) if config_dir is not None else root / "config"
    return Configs(
        research=ResearchCfg(**_read_yaml(cdir / "research.yaml")),
        cleaning=CleaningCfg(**_read_yaml(cdir / "cleaning.yaml")),
        model=ModelCfg(**_read_yaml(cdir / "model.yaml")),
        tags=TagRules(**_read_yaml(cdir / "tag_rules.yaml")),
        root=root,
    )
