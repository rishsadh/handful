"""The primal LP: feasibility, exact size, capacity compliance, integrality, oracles."""

from __future__ import annotations

import numpy as np
import pytest

from foodcom.evaluation.methods import run_ai_topk, run_lp_method, run_random
from foodcom.optimisation.greedy import enumerate_optimal, greedy_select, unconstrained_topk
from foodcom.optimisation.integrality import (
    verify_against_oracles,
    verify_partition,
)
from foodcom.optimisation.lpp import (
    ShortlistProblem,
    check_feasibility,
    make_problem,
    prune_to_top_per_band,
    solve_primal,
)

LABELS = ["G1_0_15", "G2_15_30", "G3_30_60", "G4_60_plus"]


def random_problem(rng, n=40, k=6, cap=3, n_bands=4, tie_scores=False):
    scores = (
        np.full(n, 0.5) if tie_scores else rng.uniform(0.0, 1.0, size=n)
    )
    bands = rng.integers(0, n_bands, size=n)
    # Guarantee every band is populated, otherwise feasibility is trivially varied.
    bands[:n_bands] = np.arange(n_bands)
    return make_problem(
        candidate_ids=np.arange(1000, 1000 + n),
        scores=scores,
        bands=bands,
        k=k,
        cap=cap,
        band_labels=LABELS[:n_bands],
        user_id=1,
    )


# ------------------------------------------------------------------ feasibility


def test_feasibility_rule_matches_the_definition(rng):
    problem = random_problem(rng, n=40)
    report = check_feasibility(problem)
    sizes = problem.band_sizes()
    expected = int(np.minimum(problem.caps, sizes).sum())
    assert report.capacity == expected
    assert report.feasible == (expected >= problem.k)


def test_infeasible_problem_is_reported_not_solved():
    # Two bands with one recipe each, k=6: no shortlist of length 6 can exist.
    problem = make_problem(
        candidate_ids=np.array([1, 2]),
        scores=np.array([0.9, 0.8]),
        bands=np.array([0, 1]),
        k=6,
        cap=3,
        band_labels=LABELS,
    )
    report = check_feasibility(problem)
    assert not report.feasible
    solution = solve_primal(problem)
    assert not solution.ok
    assert len(solution.selected_ids) == 0
    assert "reachable capacity" in solution.verification.problems[0]


def test_boundary_case_capacity_exactly_equals_k():
    problem = make_problem(
        candidate_ids=np.arange(6),
        scores=np.linspace(0.1, 0.9, 6),
        bands=np.array([0, 0, 0, 1, 1, 1]),
        k=6,
        cap=3,
        band_labels=LABELS,
    )
    assert check_feasibility(problem).feasible
    solution = solve_primal(problem)
    assert solution.ok
    assert len(solution.selected_ids) == 6


# ------------------------------------------------------------------ structure


def test_bands_partition_the_candidates(rng):
    assert verify_partition(random_problem(rng))["disjoint_and_exhaustive"]


def test_solution_has_exactly_k_unique_items(rng):
    for _ in range(20):
        solution = solve_primal(random_problem(rng))
        assert solution.ok
        assert len(solution.selected_ids) == 6
        assert len(set(solution.selected_ids.tolist())) == 6


def test_capacities_are_respected(rng):
    for _ in range(20):
        problem = random_problem(rng)
        solution = solve_primal(problem)
        usage = solution.band_usage()
        for label, used in usage.items():
            assert used <= problem.caps[LABELS.index(label)]


def test_solution_is_integral_within_tolerance(rng):
    for _ in range(30):
        solution = solve_primal(random_problem(rng))
        assert solution.verification.integral
        assert solution.verification.max_distance_to_integer <= solution.verification.tolerance


def test_equality_residual_is_within_tolerance(rng):
    solution = solve_primal(random_problem(rng))
    assert solution.verification.equality_residual <= solution.verification.tolerance


def test_fractional_solution_is_a_failure_not_a_rounding_opportunity(rng):
    """The verifier must refuse a fractional vector rather than round it."""
    from foodcom.optimisation.lpp import verify_solution

    problem = random_problem(rng)
    fractional = np.zeros(problem.n)
    fractional[:12] = 0.5  # sums to 6, but nothing is whole
    report = verify_solution(
        problem, fractional, success=True, status=0, message="ok", tol=1e-7
    )
    assert not report.ok
    assert any("FAILED STRUCTURAL TEST" in p for p in report.problems)


# ------------------------------------------------------------------ oracles


def test_lp_matches_greedy(rng):
    for _ in range(30):
        problem = random_problem(rng)
        lp = solve_primal(problem, prune=False)
        _, greedy_obj = greedy_select(problem)
        assert np.isclose(lp.objective, greedy_obj, atol=1e-9)


def test_lp_matches_exhaustive_enumeration_on_tiny_cases(rng):
    for _ in range(15):
        problem = random_problem(rng, n=10, k=3, cap=2, n_bands=3)
        lp = solve_primal(problem, prune=False)
        if not lp.feasibility.feasible:
            continue
        _, enum_obj = enumerate_optimal(problem)
        assert np.isclose(lp.objective, enum_obj, atol=1e-9)


def test_uncapped_lp_equals_top_k(rng):
    for _ in range(20):
        problem = random_problem(rng, cap=6)  # b_g == k removes the effective cap
        lp = solve_primal(problem, prune=False)
        _, topk_obj = unconstrained_topk(problem)
        assert np.isclose(lp.objective, topk_obj, atol=1e-9)


def test_capped_objective_never_exceeds_uncapped(rng):
    for _ in range(20):
        capped = random_problem(rng, cap=3)
        uncapped = ShortlistProblem(
            candidate_ids=capped.candidate_ids,
            scores=capped.scores,
            band_of=capped.band_of,
            k=capped.k,
            caps=np.full(capped.n_bands, capped.k, dtype="int64"),
            band_labels=capped.band_labels,
        )
        assert solve_primal(capped).objective <= solve_primal(uncapped).objective + 1e-9


def test_full_oracle_battery(rng):
    result = verify_against_oracles(random_problem(rng, n=12, k=3, cap=2, n_bands=3))
    assert result["all_checks_passed"], result["problems"]
    assert result["greedy_matches_lp"]
    assert result["enumeration_matches_lp"]
    assert result["cap_free_matches_topk"]


# ------------------------------------------------------------------ pruning


def test_pruning_keeps_at_most_b_per_band(rng):
    problem = random_problem(rng, n=200)
    pruned, _ = prune_to_top_per_band(problem)
    sizes = pruned.band_sizes()
    assert (sizes <= problem.caps).all()


def test_pruning_does_not_change_the_optimum(rng):
    for _ in range(25):
        problem = random_problem(rng, n=120)
        assert np.isclose(
            solve_primal(problem, prune=True).objective,
            solve_primal(problem, prune=False).objective,
            atol=1e-9,
        )


def test_pruned_solution_is_lifted_back_to_full_coordinates(rng):
    problem = random_problem(rng, n=120)
    solution = solve_primal(problem, prune=True)
    assert len(solution.x) == problem.n
    assert set(solution.selected_ids.tolist()) <= set(problem.candidate_ids.tolist())


# ------------------------------------------------------------------ ties


def test_tied_scores_produce_a_valid_optimum(rng):
    problem = random_problem(rng, tie_scores=True)
    solution = solve_primal(problem, prune=False)
    assert solution.ok
    assert np.isclose(solution.objective, 0.5 * problem.k)


def test_tie_break_is_deterministic_across_repeated_solves(rng):
    problem = random_problem(rng, tie_scores=True)
    first = run_lp_method(problem).ranked_ids
    for _ in range(5):
        assert list(run_lp_method(problem).ranked_ids) == list(first)


def test_canonical_tie_break_matches_score_then_id_order(rng):
    problem = random_problem(rng, tie_scores=True)
    out = run_lp_method(problem)
    ids = list(out.ranked_ids)
    assert ids == sorted(ids)  # all scores equal, so ascending id


def test_ranking_is_score_descending(rng):
    problem = random_problem(rng)
    solution = solve_primal(problem, prune=False)
    pos = {int(r): i for i, r in enumerate(problem.candidate_ids)}
    ranked_scores = [problem.scores[pos[int(r)]] for r in solution.ranked_ids]
    assert ranked_scores == sorted(ranked_scores, reverse=True)


# ------------------------------------------------------------------ methods


def test_ai_topk_may_violate_caps_and_that_is_by_design(rng):
    # Concentrate the good scores in one band so top-k must overflow it.
    n = 30
    scores = np.linspace(0.99, 0.1, n)
    bands = np.zeros(n, dtype="int64")
    bands[10:] = 1
    problem = make_problem(np.arange(n), scores, bands, k=6, cap=3, band_labels=LABELS[:2])
    out = run_ai_topk(problem)
    usage = np.bincount(bands[[int(i) for i in out.ranked_ids]], minlength=2)
    assert usage.max() > 3
    assert not out.failed


def test_random_respects_caps_and_returns_k(rng):
    problem = random_problem(rng)
    for seed in range(10):
        out = run_random(problem, seed=seed)
        assert len(out.ranked_ids) == problem.k
        pos = {int(r): i for i, r in enumerate(problem.candidate_ids)}
        usage = np.bincount(
            [problem.band_of[pos[int(r)]] for r in out.ranked_ids], minlength=problem.n_bands
        )
        assert (usage <= problem.caps).all()


def test_random_is_reproducible_for_a_seed(rng):
    problem = random_problem(rng)
    a = run_random(problem, seed=99).ranked_ids
    b = run_random(problem, seed=99).ranked_ids
    assert list(a) == list(b)


def test_random_differs_across_seeds(rng):
    problem = random_problem(rng, n=200)
    outputs = {tuple(run_random(problem, seed=s).ranked_ids) for s in range(10)}
    assert len(outputs) > 1


# ------------------------------------------------------------------ guards


def test_problem_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        ShortlistProblem(
            candidate_ids=np.array([1, 2]),
            scores=np.array([0.5]),
            band_of=np.array([0, 1]),
            k=1,
            caps=np.array([1, 1]),
            band_labels=("a", "b"),
        )


def test_problem_rejects_band_index_outside_the_configured_bands():
    with pytest.raises(ValueError, match="outside the configured bands"):
        ShortlistProblem(
            candidate_ids=np.array([1]),
            scores=np.array([0.5]),
            band_of=np.array([5]),
            k=1,
            caps=np.array([1, 1]),
            band_labels=("a", "b"),
        )
