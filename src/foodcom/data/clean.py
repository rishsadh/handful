"""Cleaning, quarantine and the exclusion ledger.

Two principles run through this module.

1. Nothing disappears without a count. Every ordered stage records rows in, rows out and
   why, so the ledger in the Results Pack reconciles the raw download to the final
   catalogue.
2. Ambiguity is quarantined, not resolved by convenience. Conflicting recipe ids and
   tied-conflicting repeat events go to `data/interim/quarantine/` where they can be
   inspected, rather than being silently resolved with keep-first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from foodcom.data.schema import (
    RECIPE_LIST_COLUMNS,
    normalise_whitespace,
    parse_list_field,
)
from foodcom.models.bands import assign_bands
from foodcom.utils import logging as flog
from foodcom.utils.config import Configs

log = flog.get_logger(__name__)

_IDENTITY_FIELDS = ["name", "minutes", "submitted", "ingredients", "steps"]


@dataclass
class Ledger:
    """An ordered record of how many rows each cleaning stage removed."""

    entity: str
    rows: list[dict[str, Any]] = field(default_factory=list)

    def record(self, stage: str, n_in: int, n_out: int, reason: str = "") -> None:
        self.rows.append(
            {
                "entity": self.entity,
                "order": len(self.rows),
                "stage": stage,
                "n_in": int(n_in),
                "n_out": int(n_out),
                "n_removed": int(n_in - n_out),
                "reason": reason,
            }
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.rows,
            columns=["entity", "order", "stage", "n_in", "n_out", "n_removed", "reason"],
        )


@dataclass
class CleanResult:
    frame: pd.DataFrame
    ledger: Ledger
    quarantine: dict[str, pd.DataFrame] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)

    def write_quarantine(self, out_dir: Path) -> list[Path]:
        """Write quarantined frames. Keys starting with `_` are private and skipped."""
        written = []
        for name, frame in self.quarantine.items():
            if frame.empty or name.startswith("_"):
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / f"{name}.parquet"
            frame.to_parquet(p, index=False)
            written.append(p)
        return written


# --------------------------------------------------------------------------- recipes


def clean_recipes(raw: pd.DataFrame, cfg: Configs) -> CleanResult:
    rules = cfg.cleaning.recipes
    ledger = Ledger("recipes")
    quarantine: dict[str, pd.DataFrame] = {}
    notes: dict[str, Any] = {}

    df = raw.copy()
    ledger.record("raw", len(df), len(df), "as downloaded")

    # --- exact duplicate rows ---
    n_in = len(df)
    if rules["duplicates"]["drop_exact_duplicate_rows"]:
        df = df.drop_duplicates(keep="first")
    ledger.record("drop_exact_duplicate_rows", n_in, len(df), "byte-identical rows")

    # --- conflicting recipe ids -> quarantine ---
    n_in = len(df)
    fields = [f for f in _IDENTITY_FIELDS if f in df.columns]
    dup_mask = df["id"].duplicated(keep=False) & df["id"].notna()
    conflicting_ids: list[int] = []
    if dup_mask.any() and fields:
        sub = df.loc[dup_mask, ["id", *fields]].astype(dict.fromkeys(fields, "string"))
        for rid, grp in sub.groupby("id", dropna=True):
            if grp.drop(columns=["id"]).drop_duplicates().shape[0] > 1:
                conflicting_ids.append(int(rid))
    if conflicting_ids:
        quarantine["recipes_conflicting_ids"] = df[df["id"].isin(conflicting_ids)].copy()
        df = df[~df["id"].isin(conflicting_ids)]
    # Ids duplicated but fully identical on the identity fields collapse to one row.
    df = df.drop_duplicates(subset=["id"], keep="first")
    ledger.record(
        "quarantine_conflicting_ids",
        n_in,
        len(df),
        f"{len(conflicting_ids)} recipe ids had disagreeing rows and were quarantined; "
        "identical repeats collapsed",
    )
    notes["n_conflicting_recipe_ids_quarantined"] = len(conflicting_ids)

    # --- required id ---
    n_in = len(df)
    df = df[df["id"].notna()].copy()
    df["id"] = df["id"].astype("int64")
    ledger.record("require_valid_id", n_in, len(df), "recipe id is the primary key")

    # --- name ---
    n_in = len(df)
    df["name"] = df["name"].map(normalise_whitespace)
    df = df[df["name"] != ""]
    ledger.record("require_name", n_in, len(df), "empty or missing recipe name")

    # --- submitted date ---
    n_in = len(df)
    df["submitted"] = pd.to_datetime(df["submitted"], errors="coerce", format="mixed")
    df = df[df["submitted"].notna()]
    ledger.record(
        "require_valid_submitted_date",
        n_in,
        len(df),
        "catalogue availability date is required for historical evaluation",
    )

    # --- minutes ---
    n_in = len(df)
    minutes = pd.to_numeric(df["minutes"], errors="coerce").astype("float64")
    keep = minutes.notna() & np.isfinite(minutes.to_numpy(dtype="float64", na_value=np.nan))
    if rules["minutes"].get("require_positive", True):
        keep &= minutes > 0
    df = df[keep.fillna(False)].copy()
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").astype("int64")
    ledger.record(
        "require_positive_finite_minutes",
        n_in,
        len(df),
        "non-positive or non-finite reported minutes cannot be banded",
    )
    # A sentinel is not a long recipe. This excludes named overflow values only; the
    # genuine long tail is kept and merely flagged below.
    sentinels = list(rules["minutes"].get("sentinel_values") or [])
    if sentinels:
        n_in = len(df)
        bad = df["minutes"].isin(sentinels)
        if bad.any():
            quarantine["recipes_sentinel_minutes"] = df[bad].copy()
        df = df[~bad].copy()
        ledger.record(
            "exclude_sentinel_minutes",
            n_in,
            len(df),
            f"reported minutes exactly equal to a known overflow sentinel {sentinels}",
        )
        notes["n_sentinel_minutes_excluded"] = int(n_in - len(df))

    flag_above = rules["minutes"].get("flag_above_minutes")
    if flag_above is not None:
        df["minutes_flagged_long"] = df["minutes"] > float(flag_above)
        notes["n_minutes_flagged_long"] = int(df["minutes_flagged_long"].sum())
        notes["minutes_flag_threshold"] = float(flag_above)
        notes["minutes_policy"] = (
            "Long durations are flagged, never auto-deleted: marinating, chilling and slow "
            "cooking are legitimate. No IQR trimming is applied."
        )

    # --- list fields ---
    for col in RECIPE_LIST_COLUMNS:
        if col not in df.columns:
            continue
        if rules.get("keep_raw_strings", True):
            df[f"raw_{col}"] = df[col].astype("string")
        parsed = df[col].map(parse_list_field)
        df[col] = parsed.map(lambda t: t[0] if t[0] is not None else [])
        df[f"{col}_parse_status"] = parsed.map(lambda t: t[1]).astype("string")

    n_in = len(df)
    usable_ingredients = df["ingredients"].map(len) > 0
    quarantine["recipes_unusable_ingredients"] = df[~usable_ingredients].copy()
    df = df[usable_ingredients].copy()
    ledger.record(
        "require_parsable_ingredients",
        n_in,
        len(df),
        "an empty or unparsable ingredient list cannot produce recipe text",
    )

    # --- description ---
    if "description" in df.columns:
        df["description_missing"] = df["description"].isna() | (
            df["description"].map(lambda v: isinstance(v, str) and not v.strip())
        )
        if rules["text"].get("missing_description_to_empty", True):
            df["description"] = df["description"].map(normalise_whitespace)

    # --- derived counts, kept separate from the source columns ---
    df["n_ingredients_parsed"] = df["ingredients"].map(len).astype("int64")
    df["n_steps_parsed"] = df["steps"].map(len).astype("int64") if "steps" in df else 0
    for spec in rules.get("derived_count_checks", []):
        src, parsed_col = spec["source"], spec["parsed"]
        derived = f"n_{parsed_col}_parsed"
        if src in df.columns and derived in df.columns:
            df[f"{src}_matches_parsed"] = pd.to_numeric(df[src], errors="coerce") == df[derived]

    # --- nutrition, retained but not used in the core model ---
    if "nutrition" in df.columns:
        expected = int(rules["nutrition"]["expected_length"])
        df["nutrition_length"] = df["nutrition"].map(len).astype("int64")
        df["nutrition_length_expected"] = df["nutrition_length"] == expected
        notes["nutrition"] = {
            "expected_length": expected,
            "units_verified": bool(rules["nutrition"]["units_verified"]),
            "used_in_core_model": False,
        }

    # --- bands ---
    df["band"] = assign_bands(df["minutes"], cfg.research.protocol)
    if df["band"].isna().any():  # pragma: no cover - guarded by the minutes stage above
        raise AssertionError("a surviving recipe failed band assignment")

    ledger.record("core_catalogue", len(df), len(df), "final cleaned recipe catalogue")
    log.info("cleaned recipes: %d rows", len(df))
    return CleanResult(
        frame=df.reset_index(drop=True), ledger=ledger, quarantine=quarantine, notes=notes
    )


# ---------------------------------------------------------------------- interactions


def clean_interactions(
    raw: pd.DataFrame, recipes_clean: pd.DataFrame, cfg: Configs
) -> CleanResult:
    rules = cfg.cleaning.interactions
    protocol = cfg.research.protocol
    ledger = Ledger("interactions")
    quarantine: dict[str, pd.DataFrame] = {}
    notes: dict[str, Any] = {}

    df = raw.copy()
    ledger.record("raw", len(df), len(df), "as downloaded")

    # Review text is separated immediately: it is never a feature and never leaves here.
    review_text = None
    if "review" in df.columns and rules["review_text"].get("retain_locally", True):
        review_text = df[["user_id", "recipe_id", "date", "review"]].copy()
    df = df.drop(columns=["review"], errors="ignore")

    n_in = len(df)
    if rules["duplicates"]["drop_exact_duplicate_rows"]:
        df = df.drop_duplicates(keep="first")
    ledger.record("drop_exact_duplicate_rows", n_in, len(df), "byte-identical rows")

    # --- keys ---
    n_in = len(df)
    bad_keys = df["user_id"].isna() | df["recipe_id"].isna()
    if bad_keys.any():
        quarantine["interactions_missing_keys"] = df[bad_keys].copy()
    df = df[~bad_keys].copy()
    df["user_id"] = df["user_id"].astype("int64")
    df["recipe_id"] = df["recipe_id"].astype("int64")
    ledger.record("quarantine_missing_keys", n_in, len(df), "missing user_id or recipe_id")

    # --- dates ---
    n_in = len(df)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
    bad_dates = df["date"].isna()
    if bad_dates.any():
        quarantine["interactions_invalid_dates"] = df[bad_dates].copy()
    df = df[~bad_dates].copy()
    ledger.record("quarantine_invalid_dates", n_in, len(df), "unparsable review date")

    # --- ratings ---
    n_in = len(df)
    valid = set(rules["rating"]["valid_explicit"])
    unknown = int(rules["rating"]["unknown_value"])
    r = pd.to_numeric(df["rating"], errors="coerce")
    in_range = r.isin(valid | {unknown})
    if rules["rating"].get("quarantine_out_of_range", True) and (~in_range).any():
        quarantine["interactions_invalid_ratings"] = df[~in_range].copy()
        df = df[in_range].copy()
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce").astype("int64")
    ledger.record(
        "quarantine_invalid_ratings",
        n_in,
        len(df),
        f"rating outside {sorted(valid)} or the unknown value {unknown}",
    )

    df["is_positive"] = df["rating"].isin(protocol.positive_ratings)
    df["is_unknown_rating"] = df["rating"] == unknown
    notes["rating_semantics"] = {
        "positive": sorted(protocol.positive_ratings),
        "observed_nonpositive": sorted(protocol.observed_nonpositive_ratings),
        "unknown": unknown,
        "note": (
            f"rating {unknown} means unknown/unrated. It is never a zero-star dislike and "
            "never inferred positive from review text. Unreviewed recipes are not negatives."
        ),
    }

    # --- orphan recipe ids ---
    n_in = len(df)
    if rules["joins"].get("drop_orphan_recipe_ids", True):
        known = set(recipes_clean["id"].astype("int64").tolist())
        orphan = ~df["recipe_id"].isin(known)
        notes["n_orphan_interactions"] = int(orphan.sum())
        notes["n_orphan_recipe_ids"] = int(df.loc[orphan, "recipe_id"].nunique())
        df = df[~orphan].copy()
    ledger.record(
        "drop_orphan_recipe_ids", n_in, len(df), "recipe_id absent from the clean catalogue"
    )

    if rules["joins"].get("enforce_many_to_one", True) and not recipes_clean["id"].is_unique:
        raise AssertionError(
            "recipe id is not unique in the clean catalogue: an interaction join would "
            "multiply rows and inflate every count downstream"
        )

    # --- collapse repeated (user, recipe) pairs to the earliest event ---
    n_in = len(df)
    df = df.sort_values(["user_id", "recipe_id", "date"], kind="mergesort")
    grp = df.groupby(["user_id", "recipe_id"], sort=False)

    first_date = grp["date"].transform("min")
    is_earliest = df["date"] == first_date
    earliest = df[is_earliest]

    # Tied earliest dates that disagree on rating: unusable as a label, still SEEN.
    tie_stats = earliest.groupby(["user_id", "recipe_id"])["rating"].agg(["nunique", "size"])
    conflicted = tie_stats[(tie_stats["nunique"] > 1)].index
    n_conflicted = len(conflicted)

    collapsed = (
        earliest.drop_duplicates(subset=["user_id", "recipe_id"], keep="first")
        .copy()
        .reset_index(drop=True)
    )
    collapsed["n_events_for_pair"] = (
        grp.size().reindex(pd.MultiIndex.from_frame(collapsed[["user_id", "recipe_id"]])).to_numpy()
    )
    conflicted_set = {(int(u), int(r)) for u, r in conflicted}
    collapsed["tied_earliest_conflict"] = [
        (int(u), int(rid)) in conflicted_set
        for u, rid in zip(collapsed["user_id"], collapsed["recipe_id"], strict=True)
    ]
    # A conflicted pair is excluded from label evaluation but still marks the recipe seen.
    collapsed["label_eligible"] = ~collapsed["tied_earliest_conflict"]
    collapsed.loc[collapsed["tied_earliest_conflict"], "is_positive"] = False

    if n_conflicted:
        quarantine["interactions_tied_earliest_conflicts"] = df[
            df.set_index(["user_id", "recipe_id"]).index.isin(conflicted)
        ].copy()

    notes["n_repeated_pairs_collapsed"] = int(n_in - len(collapsed))
    notes["n_tied_earliest_conflicts"] = n_conflicted
    notes["repeat_pair_policy"] = (
        "Earliest event retained per (user, recipe). A later rating is never averaged into "
        "an earlier history. Any earlier event - including an unknown rating - makes the "
        "recipe SEEN and therefore ineligible as a novel recommendation."
    )
    df = collapsed
    ledger.record(
        "collapse_repeat_pairs_to_earliest",
        n_in,
        len(df),
        f"one row per (user, recipe); {n_conflicted} tied-earliest conflicts kept as seen "
        "but excluded from labels",
    )

    # --- interactions dated before recipe submission ---
    n_in = len(df)
    if rules["temporal"].get("exclude_interaction_before_submission", True):
        sub = recipes_clean[["id", "submitted"]].rename(
            columns={"id": "recipe_id", "submitted": "recipe_submitted"}
        )
        df = df.merge(sub, on="recipe_id", how="left")
        before = df["date"] < df["recipe_submitted"]
        notes["n_interactions_before_submission"] = int(before.sum())
        if before.any():
            quarantine["interactions_before_submission"] = df[before].copy()
        df = df[~before].copy()
    ledger.record(
        "exclude_interaction_before_submission",
        n_in,
        len(df),
        "a review dated before the recipe existed is an unresolved inconsistency",
    )

    ledger.record("core_interactions", len(df), len(df), "final cleaned interaction events")
    log.info("cleaned interactions: %d rows", len(df))

    result = CleanResult(
        frame=df.reset_index(drop=True), ledger=ledger, quarantine=quarantine, notes=notes
    )
    if review_text is not None:
        result.notes["review_text_rows"] = len(review_text)
        result.notes["review_text_location"] = "data/interim/review_text.parquet (gitignored)"
        result.quarantine["_review_text_private"] = review_text
    return result


def combined_ledger(*results: CleanResult) -> pd.DataFrame:
    return pd.concat([r.ledger.to_frame() for r in results], ignore_index=True)
