"""Why the continuous LP returns whole recipes.

The argument
------------
Map the model to a min-cost flow network:

    source --(capacity b_g, cost 0)--> group g
    group g --(capacity 1, cost -s_ui)--> recipe i,  for each i in G_g
    recipe i --(capacity 1, cost 0)--> sink

with the source supplying exactly `k` units and the sink absorbing `k`.

Because the bands **partition** the candidates, every recipe node has exactly one parent
group, so the node-arc incidence matrix of this network is totally unimodular. All
supplies and capacities are integers, so the flow polytope's vertices are integral, and a
basic optimal flow is integral. Projecting the group-to-recipe arc flows gives the
selection variables x_i, and the projected values are 0 or 1. A flow of 1 on the arc into
recipe i is exactly "recipe i is shortlisted".

Boundaries of the guarantee
---------------------------
This justifies **our** model. It is not a claim that arbitrary linear programmes return
whole items. It breaks if:

* quota groups overlap, so a recipe has more than one parent;
* pairwise diversity or similarity penalties are added, which are not flow constraints at
  all;
* general weighted resource constraints (a calorie budget, a total-time budget, a price
  cap) are added, since arbitrary coefficients destroy unimodularity.

None of those may be added without revising the protocol.

One more caveat: a **non-basic** optimal solution at a tied optimum can be fractional even
when an integral optimum exists. That is why the solver is `highs-ds` (dual simplex,
which returns a basic solution) and why every solve is verified rather than assumed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from foodcom.optimisation.greedy import enumerate_optimal, greedy_select, unconstrained_topk
from foodcom.optimisation.lpp import DEFAULT_TOL, ShortlistProblem, solve_primal

ARGUMENT_SUMMARY = (
    "The disjoint preparation-time bands make the constraint matrix that of a min-cost "
    "flow problem with integer supplies and capacities, whose basic optimal solutions are "
    "integral. The continuous LP therefore returns whole recipes without a binary "
    "formulation. This holds for this restricted structure only."
)

HONEST_CLAIM = (
    "A score-sorted, capacity-respecting greedy selection also solves this special case. "
    "The LP is not claimed to be computationally necessary here. Its contribution is a "
    "transparent formulation, an exact feasibility condition, a certified optimum and an "
    "interpretable dual."
)


def flow_network_description(problem: ShortlistProblem) -> dict[str, Any]:
    """The network the model maps onto, as data - used in the Results Pack and the demo."""
    sizes = problem.band_sizes()
    return {
        "source_supply": int(problem.k),
        "sink_demand": int(problem.k),
        "source_to_group_arcs": [
            {
                "group": problem.band_labels[g],
                "capacity": int(problem.caps[g]),
                "cost": 0.0,
                "n_recipes_in_group": int(sizes[g]),
            }
            for g in range(problem.n_bands)
        ],
        "group_to_recipe_arcs": {
            "capacity_each": 1,
            "cost_each": "-s_ui (negated so a min-cost flow maximises relevance)",
            "count": int(problem.n),
        },
        "recipe_to_sink_arcs": {"capacity_each": 1, "cost_each": 0.0, "count": int(problem.n)},
        "every_recipe_has_exactly_one_parent_group": True,
        "argument": ARGUMENT_SUMMARY,
        "honest_claim": HONEST_CLAIM,
    }


def verify_partition(problem: ShortlistProblem) -> dict[str, Any]:
    """Bands must be disjoint and exhaustive over the candidate set."""
    counts = np.bincount(problem.band_of, minlength=problem.n_bands)
    problems = []
    if int(counts.sum()) != problem.n:
        problems.append("band membership does not cover every candidate exactly once")
    if problem.band_of.size and (
        problem.band_of.min() < 0 or problem.band_of.max() >= problem.n_bands
    ):
        problems.append("a candidate is assigned to a band index outside the configured set")
    return {
        "n_candidates": int(problem.n),
        "band_sizes": counts.tolist(),
        "disjoint_and_exhaustive": not problems,
        "problems": problems,
    }


def verify_against_oracles(
    problem: ShortlistProblem,
    *,
    tol: float = DEFAULT_TOL,
    enumerate_if_small: bool = True,
    max_combinations: int = 200_000,
    prune: bool = True,
) -> dict[str, Any]:
    """Cross-check one LP solve against greedy, enumeration and the cap-free top-k identity.

    Every check compares **objective values**, not sets: at a tied optimum two different
    sets can both be optimal, and demanding set equality would fail a correct solver.

    `prune=True` by default because band pruning is exact here and the unpruned simplex is
    intractable at catalogue scale. Pass `prune=False` on small fixtures where the two
    should be compared directly.
    """
    lp = solve_primal(problem, tol=tol, prune=prune)
    out: dict[str, Any] = {
        "user_id": problem.user_id,
        "n_candidates": problem.n,
        "k": problem.k,
        "caps": problem.caps.tolist(),
        "partition": verify_partition(problem),
        "lp_feasible": lp.feasibility.feasible,
        "lp_objective": lp.objective,
        "lp_verification": lp.verification.as_dict(),
        "problems": list(lp.verification.problems),
    }
    if not lp.feasibility.feasible:
        return out

    _, greedy_obj = greedy_select(problem)
    out["greedy_objective"] = greedy_obj
    out["greedy_matches_lp"] = bool(abs(greedy_obj - lp.objective) <= max(tol, 1e-9))
    if not out["greedy_matches_lp"]:
        out["problems"].append(
            f"greedy objective {greedy_obj:.9f} != LP objective {lp.objective:.9f}"
        )

    from math import comb

    if enumerate_if_small and problem.k <= problem.n:
        total = comb(problem.n, problem.k)
        if total <= max_combinations:
            _, enum_obj = enumerate_optimal(problem, max_combinations=max_combinations)
            out["enumeration_objective"] = enum_obj
            out["enumeration_combinations"] = int(total)
            out["enumeration_matches_lp"] = bool(abs(enum_obj - lp.objective) <= max(tol, 1e-9))
            if not out["enumeration_matches_lp"]:
                out["problems"].append(
                    f"enumeration objective {enum_obj:.9f} != LP objective {lp.objective:.9f}"
                )
        else:
            out["enumeration_skipped"] = f"C({problem.n},{problem.k}) = {total} too large"

    # Cap-free identity: with every b_g = k the LP optimum must equal the top-k sum.
    uncapped = ShortlistProblem(
        candidate_ids=problem.candidate_ids,
        scores=problem.scores,
        band_of=problem.band_of,
        k=problem.k,
        caps=np.full(problem.n_bands, problem.k, dtype="int64"),
        band_labels=problem.band_labels,
        user_id=problem.user_id,
    )
    _, topk_obj = unconstrained_topk(uncapped)
    lp_uncapped = solve_primal(uncapped, tol=tol, prune=prune)
    out["cap_free_topk_objective"] = topk_obj
    out["cap_free_lp_objective"] = lp_uncapped.objective
    out["cap_free_matches_topk"] = bool(
        abs(topk_obj - lp_uncapped.objective) <= max(tol, 1e-9)
    )
    if not out["cap_free_matches_topk"]:
        out["problems"].append(
            f"with b_g=k the LP objective {lp_uncapped.objective:.9f} != top-k sum "
            f"{topk_obj:.9f}"
        )

    out["all_checks_passed"] = not out["problems"]
    return out
