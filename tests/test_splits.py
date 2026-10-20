"""Temporal protocol: history/label separation, catalogue availability, cohorts, leakage."""

from __future__ import annotations

import pandas as pd
import pytest

from foodcom.data.splits import (
    assert_no_leakage,
    build_all_splits,
    build_stage_split,
    popularity_scores,
)
from foodcom.models.bands import assign_bands, band_index, band_label


@pytest.fixture
def splits(cfg, cleaned):
    rec, inter = cleaned
    return build_all_splits(inter.frame, rec.frame, cfg), rec, inter


def test_both_stages_are_built(splits):
    all_splits, _, _ = splits
    assert set(all_splits) == {"validation", "final"}


def test_history_is_strictly_before_the_cutoff(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        cutoff = pd.Timestamp(split.window.history_end_exclusive)
        assert (pd.to_datetime(split.history["date"]) < cutoff).all()


def test_labels_lie_inside_the_label_window(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        dates = pd.to_datetime(split.labels["date"])
        assert (dates >= pd.Timestamp(split.window.label_start)).all()


def test_history_and_labels_never_overlap(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        hist = set(map(tuple, split.history[["user_id", "recipe_id", "date"]].to_numpy()))
        lab = set(map(tuple, split.labels[["user_id", "recipe_id", "date"]].to_numpy()))
        assert not hist & lab


def test_catalogue_contains_only_recipes_submitted_before_the_cutoff(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        cutoff = pd.Timestamp(split.window.history_end_exclusive)
        assert (pd.to_datetime(split.catalogue["submitted"]) < cutoff).all()


def test_seen_recipes_are_excluded_from_candidates(splits):
    all_splits, _, _ = splits
    split = all_splits["validation"]
    for user_id in split.cohort_users[:10]:
        candidates = set(split.candidates_for(user_id).tolist())
        assert not candidates & split.seen.get(user_id, set())


def test_any_earlier_event_including_unknown_rating_marks_a_recipe_seen(splits):
    all_splits, _, inter = splits
    split = all_splits["validation"]
    cutoff = pd.Timestamp(split.window.history_end_exclusive)
    unknown = inter.frame[
        (inter.frame["rating"] == 0) & (pd.to_datetime(inter.frame["date"]) < cutoff)
    ]
    assert len(unknown) > 0, "the fixture should contain pre-cutoff unknown ratings"
    for row in unknown.head(20).itertuples():
        assert int(row.recipe_id) in split.seen[int(row.user_id)]


def test_no_label_positive_is_already_seen(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        for user_id, positives in split.label_positives.items():
            assert not positives & split.seen.get(user_id, set())


def test_eligibility_threshold_uses_history_only(splits, cfg):
    all_splits, _, _ = splits
    split = all_splits["validation"]
    minimum = cfg.research.protocol.min_distinct_positive_history
    for user_id in split.history_eligible_users:
        assert len(split.positives[user_id]) >= minimum


def test_ranking_cohort_is_a_subset_of_the_selected_cohort(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        assert set(split.ranking_users) <= set(split.cohort_users)
        assert set(split.cohort_users) <= set(split.history_eligible_users)


def test_denominators_report_every_population(splits):
    all_splits, _, _ = splits
    d = all_splits["validation"].denominators
    for key in (
        "n_history_eligible_users",
        "n_cohort_users",
        "n_cohort_users_with_any_future_event",
        "n_ranking_eligible_users",
        "n_catalogue_recipes",
    ):
        assert key in d


def test_cohort_selection_is_deterministic(cfg, cleaned):
    rec, inter = cleaned
    a = build_stage_split("validation", inter.frame, rec.frame, cfg)
    b = build_stage_split("validation", inter.frame, rec.frame, cfg)
    assert a.cohort_users == b.cohort_users
    assert a.ranking_users == b.ranking_users


def test_leakage_checks_pass(splits):
    all_splits, _, _ = splits
    for split in all_splits.values():
        report = assert_no_leakage(split)
        assert len(report["checks_passed"]) == 4


def test_leakage_check_catches_a_planted_future_event(splits):
    all_splits, _, _ = splits
    split = all_splits["validation"]
    poisoned = split.history.copy()
    poisoned.loc[poisoned.index[0], "date"] = pd.Timestamp("2017-06-01")
    split.history = poisoned
    with pytest.raises(AssertionError, match="history event"):
        assert_no_leakage(split)


def test_popularity_uses_history_only(splits):
    all_splits, _, _ = splits
    split = all_splits["validation"]
    pop = popularity_scores(split)
    manual = (
        split.history[split.history["is_positive"]].groupby("recipe_id").size()
    )
    for rid, count in manual.head(20).items():
        if rid in pop.index:
            assert pop.loc[rid] == count
    assert pop.sum() == split.history["is_positive"].sum() - (
        split.history[split.history["is_positive"]]["recipe_id"]
        .isin(set(split.catalogue["id"]))
        .eq(False)
        .sum()
    )


def test_final_history_extends_beyond_validation_history(splits):
    all_splits, _, _ = splits
    assert (
        all_splits["final"].denominators["n_history_events"]
        >= all_splits["validation"].denominators["n_history_events"]
    )


# ------------------------------------------------------------------ band boundaries


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (1, "G1_0_15"),
        (15, "G1_0_15"),      # upper-inclusive: 15 is G1, not G2
        (15.0001, "G2_15_30"),
        (30, "G2_15_30"),
        (30.5, "G3_30_60"),
        (60, "G3_30_60"),
        (61, "G4_60_plus"),
        (10_000, "G4_60_plus"),
    ],
)
def test_band_boundaries_are_upper_inclusive(minutes, expected, real_config):
    assert band_label(minutes, real_config.research.protocol) == expected


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_invalid_minutes_are_refused_a_band(bad, real_config):
    with pytest.raises(ValueError, match="positive and finite"):
        band_index(bad, real_config.research.protocol.band_edges)


def test_bands_are_disjoint_and_exhaustive(cleaned, real_config):
    rec, _ = cleaned
    bands = assign_bands(rec.frame["minutes"], real_config.research.protocol)
    assert bands.notna().all()
    assert set(bands.unique()) <= set(real_config.research.protocol.band_labels)
    assert len(bands) == len(rec.frame)
