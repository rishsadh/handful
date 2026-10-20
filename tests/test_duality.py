"""Duality: strong duality, complementary slackness, sign conversion, perturbation."""

from __future__ import annotations

import numpy as np
import pytest

from foodcom.optimisation.dual import (
    check_duality,
    marginals_from_primal,
    perturb_band_cap,
    solve_dual,
)
from foodcom.optimisation.integrality import flow_network_description
from foodcom.optimisation.lpp import make_problem, solve_primal

LABELS = ["G1_0_15", "G2_15_30", "G3_30_60", "G4_60_plus"]


def problem_for(rng, n=30, k=6, cap=3):
    bands = rng.integers(0, 4, size=n)
    bands[:4] = np.arange(4)
    return make_problem(
        candidate_ids=np.arange(500, 500 + n),
        scores=rng.uniform(0.2, 0.95, size=n),
        bands=bands,
        k=k,
        cap=cap,
        band_labels=LABELS,
        user_id=42,
    )


def test_strong_duality_holds(rng):
    for _ in range(20):
        problem = problem_for(rng)
        _, _, report = check_duality(problem)
        assert report.strong_duality_holds, report.problems
        assert report.duality_gap < 1e-6


def test_dual_is_feasible(rng):
    for _ in range(20):
        problem = problem_for(rng)
        _, _, report = check_duality(problem)
        assert report.max_dual_constraint_violation <= 1e-6


def test_complementary_slackness_holds(rng):
    for _ in range(20):
        problem = problem_for(rng)
        _, _, report = check_duality(problem)
        assert report.complementary_slackness_holds, report.complementary_slackness


def test_beta_is_non_negative(rng):
    for _ in range(20):
        dual = solve_dual(problem_for(rng))
        assert (dual.beta >= -1e-9).all()


def test_gamma_is_non_negative(rng):
    dual = solve_dual(problem_for(rng))
    assert (dual.gamma >= -1e-9).all()


def test_dual_objective_equals_primal_objective_exactly_enough(rng):
    problem = problem_for(rng)
    primal = solve_primal(problem, prune=False)
    dual = solve_dual(problem)
    assert np.isclose(primal.objective, dual.objective, atol=1e-7)


# ------------------------------------------------------------------ sign conversion


def test_marginals_are_converted_to_maximisation_signs(rng):
    """SciPy minimises `-s`; a band-cap marginal must come back non-negative for the max."""
    problem = problem_for(rng)
    primal = solve_primal(problem, prune=False)
    marg = marginals_from_primal(primal)
    assert marg["available"]
    assert all(b >= -1e-9 for b in marg["beta"])


def test_marginals_are_withheld_for_a_pruned_solve(rng):
    problem = problem_for(rng, n=200)
    primal = solve_primal(problem, prune=True)
    marg = marginals_from_primal(primal)
    assert not marg["available"]
    assert "pruned" in marg["reason"]


def test_shadow_value_direction_matches_a_resolved_change(rng):
    """A positive beta must correspond to a non-negative gain from relaxing that cap."""
    for _ in range(10):
        problem = problem_for(rng, n=40)
        _, dual, _ = check_duality(problem)
        binding = [g for g in range(problem.n_bands) if dual.beta[g] > 1e-6]
        for band in binding:
            result = perturb_band_cap(problem, band, +1)
            if result.get("feasible_after_change"):
                assert result["actual_objective_change"] >= -1e-9


def test_relaxing_a_cap_never_lowers_the_objective(rng):
    for _ in range(10):
        problem = problem_for(rng, n=40)
        for band in range(problem.n_bands):
            result = perturb_band_cap(problem, band, +1)
            if result.get("feasible_after_change"):
                assert result["actual_objective_change"] >= -1e-9


def test_tightening_a_cap_never_raises_the_objective(rng):
    for _ in range(10):
        problem = problem_for(rng, n=40)
        for band in range(problem.n_bands):
            result = perturb_band_cap(problem, band, -1)
            if result.get("feasible_after_change"):
                assert result["actual_objective_change"] <= 1e-9


def test_perturbation_reports_infeasibility_rather_than_a_number(rng):
    problem = make_problem(
        candidate_ids=np.arange(6),
        scores=np.linspace(0.1, 0.9, 6),
        bands=np.array([0, 0, 0, 1, 1, 1]),
        k=6,
        cap=3,
        band_labels=LABELS,
    )
    result = perturb_band_cap(problem, 0, -1)
    assert result["feasible_after_change"] is False
    assert "reason" in result


# ------------------------------------------------------------------ ties + structure


def test_duality_holds_under_tied_scores(rng):
    problem = make_problem(
        candidate_ids=np.arange(20),
        scores=np.full(20, 0.5),
        bands=np.tile(np.arange(4), 5),
        k=6,
        cap=3,
        band_labels=LABELS,
    )
    _, _, report = check_duality(problem)
    assert report.strong_duality_holds
    assert report.complementary_slackness_holds


def test_flow_network_description_is_consistent(rng):
    problem = problem_for(rng)
    net = flow_network_description(problem)
    assert net["source_supply"] == problem.k
    assert net["every_recipe_has_exactly_one_parent_group"] is True
    assert len(net["source_to_group_arcs"]) == problem.n_bands
    assert sum(a["n_recipes_in_group"] for a in net["source_to_group_arcs"]) == problem.n


def test_beta_meaning_is_documented_and_not_monetary():
    from foodcom.optimisation.dual import BETA_MEANING

    lowered = BETA_MEANING.lower()
    assert "relevance score" in lowered
    assert "not money" in lowered
    assert "not cognitive load" in lowered


@pytest.mark.parametrize("cap", [1, 2, 3, 6])
def test_duality_holds_across_cap_settings(rng, cap):
    problem = problem_for(rng, n=40, k=6, cap=cap)
    if not solve_primal(problem, prune=False).feasibility.feasible:
        pytest.skip("configuration is structurally infeasible")
    _, _, report = check_duality(problem)
    assert report.strong_duality_holds, report.problems
