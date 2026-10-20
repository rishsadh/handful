"""The locked temporal protocol.

    validation:  history = everything before 2017-01-01, labels = calendar 2017
    final:       history = everything before 2018-01-01, labels = 2018 .. observed endpoint

Three rules do the real work here, and each one exists to stop a specific way of
accidentally cheating:

* A candidate recipe must have been **submitted** before the cutoff. Otherwise a recipe
  gets introduced into the catalogue by the very review we are trying to predict.
* A user's profile, and the popularity baseline, may only read history events. A single
  future rating leaking into a profile makes every metric downstream meaningless.
* The eligible cohort is defined from history **before** any label is examined. Choosing
  who to evaluate after seeing their future is selection on the outcome.

Anything the user has interacted with before the cutoff - including an unknown (0) rating -
counts as SEEN and is removed from the candidate set. Recommending something already
reviewed is not a novel recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from foodcom.utils import logging as flog
from foodcom.utils.config import Configs, StageWindow

log = flog.get_logger(__name__)


@dataclass
class StageSplit:
    """Everything one evaluation stage needs, and the denominators that describe it."""

    stage: str
    window: StageWindow
    history: pd.DataFrame
    labels: pd.DataFrame
    catalogue: pd.DataFrame
    seen: dict[int, set[int]]
    positives: dict[int, set[int]]
    history_eligible_users: list[int]
    cohort_users: list[int]
    ranking_users: list[int]
    label_positives: dict[int, set[int]]
    denominators: dict[str, Any] = field(default_factory=dict)

    @property
    def catalogue_ids(self) -> np.ndarray:
        return self.catalogue["id"].to_numpy(dtype="int64")

    def candidates_for(self, user_id: int) -> np.ndarray:
        """Eligible, previously unseen catalogue recipes for one user."""
        seen = self.seen.get(user_id, set())
        if not seen:
            return self.catalogue_ids
        ids = self.catalogue_ids
        mask = ~np.isin(ids, np.fromiter(seen, dtype="int64", count=len(seen)))
        return ids[mask]

    def denominator_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"stage": self.stage, "quantity": k, "value": v} for k, v in self.denominators.items()]
        )


def _resolve_label_end(window: StageWindow, interactions: pd.DataFrame) -> pd.Timestamp:
    if window.label_end_inclusive is not None:
        return pd.Timestamp(window.label_end_inclusive)
    observed = pd.to_datetime(interactions["date"]).max()
    if pd.isna(observed):
        raise ValueError("cannot resolve the observed endpoint: no valid interaction dates")
    return observed.normalize()


def build_stage_split(
    stage: str,
    interactions: pd.DataFrame,
    recipes: pd.DataFrame,
    cfg: Configs,
) -> StageSplit:
    protocol = cfg.research.protocol
    if stage not in protocol.stages:
        raise KeyError(f"unknown stage {stage!r}; configured stages: {sorted(protocol.stages)}")
    window = protocol.stages[stage]

    hist_end = pd.Timestamp(window.history_end_exclusive)
    lab_start = pd.Timestamp(window.label_start)
    lab_end = _resolve_label_end(window, interactions)

    dates = pd.to_datetime(interactions["date"])
    history = interactions[dates < hist_end].copy()
    labels = interactions[(dates >= lab_start) & (dates <= lab_end)].copy()

    # Candidate catalogue: submitted strictly before the cutoff.
    submitted = pd.to_datetime(recipes["submitted"])
    catalogue = recipes[submitted < hist_end].copy().reset_index(drop=True)
    cat_ids = set(catalogue["id"].astype("int64").tolist())

    # SEEN: any earlier event at all, whatever the rating.
    seen: dict[int, set[int]] = (
        history.groupby("user_id")["recipe_id"].apply(lambda s: set(s.astype("int64")))
        .to_dict()
    )

    # Historical positives, restricted to recipes that exist in the frozen catalogue.
    hist_pos = history[history["is_positive"] & history["recipe_id"].isin(cat_ids)]
    positives: dict[int, set[int]] = (
        hist_pos.groupby("user_id")["recipe_id"].apply(lambda s: set(s.astype("int64"))).to_dict()
    )

    # --- history-eligible cohort, defined without looking at any label ---
    min_pos = protocol.min_distinct_positive_history
    history_eligible = sorted(u for u, r in positives.items() if len(r) >= min_pos)

    # --- deterministic seeded cap, still before looking at labels ---
    cohort = list(history_eligible)
    capped = False
    if protocol.max_users is not None and len(cohort) > protocol.max_users:
        rng = np.random.default_rng(protocol.cohort_seed)
        idx = rng.choice(len(cohort), size=protocol.max_users, replace=False)
        cohort = sorted(cohort[i] for i in np.sort(idx))
        capped = True

    # --- labels: eligible, novel, positive ---
    lab = labels[labels["label_eligible"] & labels["is_positive"]]
    lab = lab[lab["recipe_id"].isin(cat_ids)]
    label_positives: dict[int, set[int]] = {}
    cohort_set = set(cohort)
    for user_id, grp in lab.groupby("user_id"):
        if user_id not in cohort_set:
            continue
        novel = set(grp["recipe_id"].astype("int64")) - seen.get(user_id, set())
        if novel:
            label_positives[int(user_id)] = novel
    ranking_users = sorted(label_positives)

    users_with_any_future = len(
        set(labels["user_id"].astype("int64").unique().tolist()) & cohort_set
    )

    denominators = {
        "history_end_exclusive": str(window.history_end_exclusive),
        "label_start": str(window.label_start),
        "label_end_inclusive": str(lab_end.date()),
        "n_history_events": len(history),
        "n_label_events": len(labels),
        "n_catalogue_recipes": len(catalogue),
        "n_users_in_history": int(history["user_id"].nunique()),
        "n_users_with_any_positive_history": len(positives),
        "n_history_eligible_users": len(history_eligible),
        "cohort_capped": capped,
        "cohort_cap": protocol.max_users,
        "cohort_seed": protocol.cohort_seed,
        "n_cohort_users": len(cohort),
        "n_cohort_users_with_any_future_event": int(users_with_any_future),
        "n_ranking_eligible_users": len(ranking_users),
        "min_distinct_positive_history": min_pos,
    }
    log.info(
        "stage %s: %d catalogue recipes, %d history-eligible users, %d in cohort, "
        "%d rankable",
        stage,
        len(catalogue),
        len(history_eligible),
        len(cohort),
        len(ranking_users),
    )

    return StageSplit(
        stage=stage,
        window=window,
        history=history.reset_index(drop=True),
        labels=labels.reset_index(drop=True),
        catalogue=catalogue,
        seen=seen,
        positives=positives,
        history_eligible_users=history_eligible,
        cohort_users=cohort,
        ranking_users=ranking_users,
        label_positives=label_positives,
        denominators=denominators,
    )


def popularity_scores(split: StageSplit) -> pd.Series:
    """Count of positive ratings received BEFORE the cutoff, per catalogue recipe.

    History only. A popularity baseline built from the full dataset would beat every
    method for the wrong reason.
    """
    pos = split.history[split.history["is_positive"]]
    counts = pos.groupby("recipe_id").size()
    return counts.reindex(split.catalogue["id"].astype("int64"), fill_value=0).astype("int64")


def assert_no_leakage(split: StageSplit) -> dict[str, Any]:
    """Structural leakage checks. Raises on violation; returns the evidence when clean."""
    hist_dates = pd.to_datetime(split.history["date"])
    lab_dates = pd.to_datetime(split.labels["date"])
    hist_end = pd.Timestamp(split.window.history_end_exclusive)
    lab_start = pd.Timestamp(split.window.label_start)

    if len(hist_dates) and hist_dates.max() >= hist_end:
        raise AssertionError(f"{split.stage}: a history event is dated on/after the cutoff")
    if len(lab_dates) and lab_dates.min() < lab_start:
        raise AssertionError(f"{split.stage}: a label event predates the label window")

    submitted = pd.to_datetime(split.catalogue["submitted"])
    if len(submitted) and submitted.max() >= hist_end:
        raise AssertionError(
            f"{split.stage}: a catalogue recipe was submitted on/after the cutoff"
        )

    for user_id, positives in split.label_positives.items():
        overlap = positives & split.seen.get(user_id, set())
        if overlap:
            raise AssertionError(
                f"{split.stage}: user {user_id} has label positives already seen in history: "
                f"{sorted(overlap)[:5]}"
            )

    return {
        "stage": split.stage,
        "history_max_date": str(hist_dates.max()) if len(hist_dates) else None,
        "history_end_exclusive": str(hist_end.date()),
        "label_min_date": str(lab_dates.min()) if len(lab_dates) else None,
        "catalogue_max_submitted": str(submitted.max()) if len(submitted) else None,
        "checks_passed": [
            "history events strictly before the cutoff",
            "label events on or after the label start",
            "catalogue recipes submitted strictly before the cutoff",
            "no label positive appears in the user's seen set",
        ],
    }


def build_all_splits(
    interactions: pd.DataFrame, recipes: pd.DataFrame, cfg: Configs
) -> dict[str, StageSplit]:
    return {
        stage: build_stage_split(stage, interactions, recipes, cfg)
        for stage in cfg.research.protocol.stages
    }
