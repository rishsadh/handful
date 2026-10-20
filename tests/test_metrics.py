"""Metrics and statistics, verified against hand calculations."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from foodcom.evaluation.metrics import (
    aggregate_per_method,
    average_random_repeats,
    band_usage,
    bands_represented,
    cap_violations,
    dcg_at_k,
    idcg_at_k,
    ndcg_at_k,
    recall_at_k,
    reduction_ratio,
)
from foodcom.evaluation.stats import paired_bootstrap, paired_matrix

# ------------------------------------------------------------------ recall


def test_recall_hand_calculation():
    # 2 of the user's 4 positives appear in the shortlist -> 0.5
    assert recall_at_k([1, 2, 9, 8, 7, 6], {1, 2, 3, 4}, k=6) == 0.5


def test_recall_with_no_hits_is_zero():
    assert recall_at_k([9, 8, 7], {1, 2}, k=3) == 0.0


def test_recall_with_all_hits_is_one():
    assert recall_at_k([1, 2, 3], {1, 2, 3}, k=3) == 1.0


def test_recall_is_undefined_without_positives():
    assert math.isnan(recall_at_k([1, 2, 3], set(), k=3))


def test_recall_only_counts_the_first_k():
    assert recall_at_k([9, 9, 9, 1], {1, 2}, k=3) == 0.0
    assert recall_at_k([9, 9, 9, 1], {1, 2}, k=4) == 0.5


def test_recall_denominator_is_the_positive_set_not_k():
    # 1 hit out of 10 positives, even though only 6 items are shown.
    assert recall_at_k([1, 20, 21, 22, 23, 24], set(range(1, 11)), k=6) == 0.1


# ------------------------------------------------------------------ dcg / ndcg


def test_dcg_hand_calculation():
    # hits at positions 1 and 3 -> 1/log2(2) + 1/log2(4) = 1.0 + 0.5
    assert math.isclose(dcg_at_k([1, 9, 2, 8], {1, 2}, k=4), 1.5)


def test_idcg_hand_calculation():
    assert math.isclose(idcg_at_k(2, 4), 1.0 + 1.0 / math.log2(3))
    assert math.isclose(idcg_at_k(10, 3), 1.0 + 1 / math.log2(3) + 1 / math.log2(4))


def test_idcg_is_capped_by_k():
    assert idcg_at_k(100, 3) == idcg_at_k(3, 3)


def test_ndcg_is_one_for_a_perfect_ranking():
    assert math.isclose(ndcg_at_k([1, 2, 3], {1, 2, 3}, k=3), 1.0)


def test_ndcg_is_zero_with_no_hits():
    assert ndcg_at_k([7, 8, 9], {1, 2}, k=3) == 0.0


def test_ndcg_is_undefined_without_positives():
    assert math.isnan(ndcg_at_k([1, 2], set(), k=2))


def test_ndcg_rewards_a_higher_position():
    early = ndcg_at_k([1, 8, 9], {1}, k=3)
    late = ndcg_at_k([8, 9, 1], {1}, k=3)
    assert early > late
    assert math.isclose(early, 1.0)


def test_ndcg_never_exceeds_one():
    for n_rel in range(1, 8):
        relevant = set(range(n_rel))
        assert ndcg_at_k(list(range(6)), relevant, k=6) <= 1.0 + 1e-12


# ------------------------------------------------------------------ bands + reduction


def test_bands_represented_counts_distinct_bands():
    band_of = {1: "G1", 2: "G1", 3: "G2", 4: "G4"}
    assert bands_represented([1, 2, 3, 4], band_of) == 3


def test_band_usage_and_cap_violations():
    band_of = dict.fromkeys(range(5), "G1")
    labels = ["G1", "G2"]
    usage = band_usage(list(range(5)), band_of, labels)
    assert usage == {"G1": 5, "G2": 0}
    assert cap_violations(usage, {"G1": 3, "G2": 3}) == 2
    assert cap_violations(usage, {"G1": 5, "G2": 3}) == 0


def test_reduction_ratio_is_the_stated_identity():
    assert math.isclose(reduction_ratio(6, 600), 0.99)
    assert math.isclose(reduction_ratio(6, 12), 0.5)


def test_reduction_ratio_is_undefined_when_candidates_are_fewer_than_k():
    assert math.isnan(reduction_ratio(6, 3))
    assert math.isnan(reduction_ratio(6, 0))


# ------------------------------------------------------------------ aggregation


def _frame(rows):
    base = {
        "stage": "validation", "k": 6, "cap": 3, "n_candidates": 100, "n_relevant": 2,
        "bands_represented": 3, "cap_violations": 0, "exact_size_ok": True,
        "feasible": True, "failed": False, "solver_status": "optimal",
        "failure_reason": None, "reduction_ratio": 0.94, "scoring_seconds": 0.01,
        "solve_seconds": 0.001, "total_seconds": 0.011, "ranked_ids": "",
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_macro_average_is_not_review_weighted():
    """A user with many positives must not dominate the mean."""
    frame = _frame(
        [
            {"user_id": 1, "method": "AI_LP", "recall_at_k": 1.0, "ndcg_at_k": 1.0,
             "n_relevant": 1},
            {"user_id": 2, "method": "AI_LP", "recall_at_k": 0.0, "ndcg_at_k": 0.0,
             "n_relevant": 500},
        ]
    )
    summary = aggregate_per_method(frame)
    assert math.isclose(summary.iloc[0]["mean_recall_at_k"], 0.5)


def test_users_without_positives_are_excluded_from_ranking_means():
    frame = _frame(
        [
            {"user_id": 1, "method": "AI_LP", "recall_at_k": 1.0, "ndcg_at_k": 1.0,
             "n_relevant": 2},
            {"user_id": 2, "method": "AI_LP", "recall_at_k": float("nan"),
             "ndcg_at_k": float("nan"), "n_relevant": 0},
        ]
    )
    summary = aggregate_per_method(frame)
    assert summary.iloc[0]["n_users_evaluated"] == 2
    assert summary.iloc[0]["n_users_with_positives"] == 1
    assert math.isclose(summary.iloc[0]["mean_recall_at_k"], 1.0)


def test_random_repeats_are_averaged_within_user_before_aggregation():
    rows = []
    for repeat in range(20):
        rows.append(
            {"user_id": 1, "method": "RANDOM", "recall_at_k": float(repeat % 2),
             "ndcg_at_k": 0.0, "repeat": repeat}
        )
    rows.append({"user_id": 1, "method": "AI_LP", "recall_at_k": 1.0, "ndcg_at_k": 1.0,
                 "repeat": 0})
    collapsed = average_random_repeats(_frame(rows))
    rnd = collapsed[collapsed["method"] == "RANDOM"]
    assert len(rnd) == 1, "20 repeats are 20 looks at one user, not 20 users"
    assert math.isclose(float(rnd.iloc[0]["recall_at_k"]), 0.5)


# ------------------------------------------------------------------ bootstrap


def test_paired_matrix_keeps_only_users_present_in_both_methods():
    frame = _frame(
        [
            {"user_id": 1, "method": "AI_LP", "recall_at_k": 0.5, "ndcg_at_k": 0.4},
            {"user_id": 1, "method": "AI_TOPK", "recall_at_k": 0.2, "ndcg_at_k": 0.1},
            {"user_id": 2, "method": "AI_LP", "recall_at_k": 0.9, "ndcg_at_k": 0.8},
        ]
    )
    wide = paired_matrix(frame, "recall_at_k", "AI_LP", "AI_TOPK")
    assert list(wide.index) == [1]


def test_bootstrap_is_reproducible_for_a_seed():
    rng = np.random.default_rng(0)
    frame = _frame(
        [
            {"user_id": u, "method": m,
             "recall_at_k": float(rng.uniform()), "ndcg_at_k": 0.0}
            for u in range(50)
            for m in ("AI_LP", "POPULARITY_LP")
        ]
    )
    a = paired_bootstrap(frame, "recall_at_k", "AI_LP", "POPULARITY_LP", seed=42,
                         n_resamples=500)
    b = paired_bootstrap(frame, "recall_at_k", "AI_LP", "POPULARITY_LP", seed=42,
                         n_resamples=500)
    assert (a.ci_low, a.ci_high) == (b.ci_low, b.ci_high)


def test_bootstrap_mean_difference_matches_the_paired_mean():
    frame = _frame(
        [
            {"user_id": 1, "method": "AI_LP", "recall_at_k": 0.8, "ndcg_at_k": 0.0},
            {"user_id": 1, "method": "POPULARITY_LP", "recall_at_k": 0.4, "ndcg_at_k": 0.0},
            {"user_id": 2, "method": "AI_LP", "recall_at_k": 0.2, "ndcg_at_k": 0.0},
            {"user_id": 2, "method": "POPULARITY_LP", "recall_at_k": 0.2, "ndcg_at_k": 0.0},
        ]
    )
    comp = paired_bootstrap(frame, "recall_at_k", "AI_LP", "POPULARITY_LP", n_resamples=200)
    assert math.isclose(comp.mean_difference, 0.2)
    assert comp.n_users == 2


def test_identical_methods_give_a_zero_difference_and_a_degenerate_interval():
    frame = _frame(
        [
            {"user_id": u, "method": m, "recall_at_k": 0.5, "ndcg_at_k": 0.0}
            for u in range(20)
            for m in ("AI_LP", "AI_TOPK")
        ]
    )
    comp = paired_bootstrap(frame, "recall_at_k", "AI_LP", "AI_TOPK", n_resamples=300)
    assert math.isclose(comp.mean_difference, 0.0)
    assert not comp.interval_excludes_zero


def test_empty_pairing_returns_nan_rather_than_raising():
    comp = paired_bootstrap(_frame([]), "recall_at_k", "AI_LP", "AI_TOPK")
    assert comp.n_users == 0
    assert math.isnan(comp.mean_difference)


def test_interval_brackets_the_point_estimate():
    rng = np.random.default_rng(7)
    frame = _frame(
        [
            {"user_id": u, "method": "AI_LP", "recall_at_k": float(rng.uniform(0.3, 0.7)),
             "ndcg_at_k": 0.0}
            for u in range(200)
        ]
        + [
            {"user_id": u, "method": "AI_TOPK", "recall_at_k": float(rng.uniform(0.1, 0.5)),
             "ndcg_at_k": 0.0}
            for u in range(200)
        ]
    )
    comp = paired_bootstrap(frame, "recall_at_k", "AI_LP", "AI_TOPK", n_resamples=2000,
                            seed=42)
    assert comp.ci_low <= comp.mean_difference <= comp.ci_high


@pytest.mark.parametrize("n_resamples", [100, 500])
def test_bootstrap_respects_the_resample_count(n_resamples):
    frame = _frame(
        [
            {"user_id": u, "method": m, "recall_at_k": float(u % 3) / 2, "ndcg_at_k": 0.0}
            for u in range(30)
            for m in ("AI_LP", "AI_TOPK")
        ]
    )
    comp = paired_bootstrap(frame, "recall_at_k", "AI_LP", "AI_TOPK",
                            n_resamples=n_resamples)
    assert comp.n_resamples == n_resamples
