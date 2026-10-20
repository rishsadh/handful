"""The four comparison methods.

All four see the same user, the same eligible candidate catalogue and the same shortlist
length. What differs is only the score they optimise and whether the band caps apply.

    RANDOM         random-priority feasible selection, caps respected, 20 seeded repeats
    POPULARITY_LP  pre-cutoff positive-review counts, caps respected, same LP
    AI_TOPK        highest AI scores, caps NOT applied  (ablation: isolates the caps)
    AI_LP          AI scores, caps applied              (the proposed method)
    TFIDF_LP       optional, separately labelled ablation

AI_TOPK is expected to violate the caps. That is the entire point of including it - it
separates "the AI score helped" from "the constraint helped". Its cap violations are
reported transparently and are not a solver bug. For identical scores its total relevance
score upper-bounds AI_LP, because it optimises the same objective over a superset of the
feasible region.

RANDOM is *random-priority* feasible selection: shuffle the catalogue, accept recipes in
that order while their band has room. It is not a uniform sample over feasible shortlists,
and is never described as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from foodcom.optimisation.greedy import unconstrained_topk
from foodcom.optimisation.lpp import (
    DEFAULT_TOL,
    ShortlistProblem,
    check_feasibility,
    solve_primal,
)

METHOD_DESCRIPTIONS: dict[str, str] = {
    "RANDOM": (
        "Random-priority feasible selection: the eligible catalogue is shuffled with a "
        "fixed seed and recipes are accepted in that order while their band has capacity. "
        "Repeated 20 times per user and averaged within the user. Not a uniform sample "
        "over feasible shortlists."
    ),
    "POPULARITY_LP": (
        "Recipes scored by their count of positive ratings before the history cutoff, then "
        "the same band-capped LP. Ties resolved by ascending recipe id."
    ),
    "AI_TOPK": (
        "The six highest AI relevance scores, with no band caps applied. An ablation that "
        "isolates the effect of the optimisation constraints; it may violate the caps."
    ),
    "AI_LP": (
        "AI relevance scores with the band-capped LP. The proposed method."
    ),
    "TFIDF_LP": (
        "TF-IDF relevance scores with the band-capped LP. A separately labelled ablation, "
        "never a substitute for the sentence-transformer model."
    ),
}


@dataclass
class MethodOutput:
    ranked_ids: np.ndarray
    objective: float
    feasible: bool
    solver_status: str
    solve_seconds: float
    failed: bool
    failure_reason: str | None
    verification: dict[str, Any] | None = None


def _empty(reason: str, feasible: bool = True) -> MethodOutput:
    return MethodOutput(
        ranked_ids=np.array([], dtype="int64"),
        objective=float("nan"),
        feasible=feasible,
        solver_status="not_produced",
        solve_seconds=0.0,
        failed=True,
        failure_reason=reason,
    )


def run_lp_method(
    problem: ShortlistProblem, *, method: str = "highs-ds", tol: float = DEFAULT_TOL,
    prune: bool = True, canonical_tie_break: bool = True,
) -> MethodOutput:
    """Shared body of POPULARITY_LP, AI_LP and TFIDF_LP.

    `canonical_tie_break` addresses a real reproducibility problem. With tied scores -
    which POPULARITY_LP produces in bulk, since most recipes share a positive-review count
    of zero - several different sets are equally optimal, and the solver may return any of
    them. Rather than perturbing the scores (which would silently change the objective),
    the optimum is recomputed with the documented lexicographic rule (score descending,
    then recipe id ascending) and accepted **only after** its objective is confirmed equal
    to the LP's. The score definition is untouched; only the choice among equally optimal
    sets is made deterministic.
    """
    solution = solve_primal(problem, method=method, tol=tol, prune=prune)
    if not solution.feasibility.feasible:
        return MethodOutput(
            ranked_ids=np.array([], dtype="int64"),
            objective=float("nan"),
            feasible=False,
            solver_status="infeasible",
            solve_seconds=solution.solve_seconds,
            failed=False,  # structurally infeasible is not a method failure
            failure_reason=solution.feasibility.reason,
            verification=solution.verification.as_dict(),
        )
    if not solution.ok:
        return MethodOutput(
            ranked_ids=solution.ranked_ids,
            objective=solution.objective,
            feasible=True,
            solver_status=f"verification_failed: {solution.verification.problems}",
            solve_seconds=solution.solve_seconds,
            failed=True,
            failure_reason="; ".join(solution.verification.problems),
            verification=solution.verification.as_dict(),
        )
    ranked = solution.ranked_ids
    status = "optimal"
    if canonical_tie_break:
        from foodcom.optimisation.greedy import greedy_select

        canonical_ids, canonical_obj = greedy_select(problem)
        if len(canonical_ids) == problem.k and abs(canonical_obj - solution.objective) <= max(
            tol, 1e-9
        ):
            if set(canonical_ids.tolist()) != set(ranked.tolist()):
                status = "optimal_canonical_tie_break"
            ranked = canonical_ids
        else:
            return MethodOutput(
                ranked_ids=solution.ranked_ids,
                objective=solution.objective,
                feasible=True,
                solver_status="canonical_objective_mismatch",
                solve_seconds=solution.solve_seconds,
                failed=True,
                failure_reason=(
                    f"lexicographic optimum objective {canonical_obj!r} does not match the "
                    f"LP objective {solution.objective!r}; this is a structural failure, "
                    "not a tie"
                ),
                verification=solution.verification.as_dict(),
            )

    return MethodOutput(
        ranked_ids=ranked,
        objective=solution.objective,
        feasible=True,
        solver_status=status,
        solve_seconds=solution.solve_seconds,
        failed=False,
        failure_reason=None,
        verification=solution.verification.as_dict(),
    )


def run_ai_topk(problem: ShortlistProblem) -> MethodOutput:
    """Top-k by score with no caps. Cap violations are expected and reported."""
    import time

    t0 = time.perf_counter()
    if problem.n < problem.k:
        return _empty(f"only {problem.n} candidates for k={problem.k}", feasible=False)
    ids, obj = unconstrained_topk(problem)
    return MethodOutput(
        ranked_ids=ids,
        objective=obj,
        feasible=True,
        solver_status="topk_no_constraints",
        solve_seconds=time.perf_counter() - t0,
        failed=False,
        failure_reason=None,
    )


def run_random(problem: ShortlistProblem, seed: int) -> MethodOutput:
    """Random-priority feasible selection under the same caps."""
    import time

    t0 = time.perf_counter()
    feas = check_feasibility(problem)
    if not feas.feasible:
        return MethodOutput(
            ranked_ids=np.array([], dtype="int64"),
            objective=float("nan"),
            feasible=False,
            solver_status="infeasible",
            solve_seconds=time.perf_counter() - t0,
            failed=False,
            failure_reason=feas.reason,
        )

    rng = np.random.default_rng(seed)
    order = rng.permutation(problem.n)
    remaining = problem.caps.copy()
    chosen: list[int] = []
    for idx in order:
        if len(chosen) == problem.k:
            break
        g = int(problem.band_of[idx])
        if remaining[g] > 0:
            chosen.append(int(idx))
            remaining[g] -= 1

    if len(chosen) < problem.k:  # pragma: no cover - excluded by the feasibility check
        return _empty("random-priority pass did not reach k despite feasibility")

    arr = np.asarray(chosen, dtype="int64")
    return MethodOutput(
        # The shuffle order IS the ranking here: re-sorting by score would import the
        # very signal this baseline is meant to lack.
        ranked_ids=problem.candidate_ids[arr],
        objective=float(problem.scores[arr].sum()),
        feasible=True,
        solver_status="random_priority",
        solve_seconds=time.perf_counter() - t0,
        failed=False,
        failure_reason=None,
    )


def uncapped_problem(problem: ShortlistProblem) -> ShortlistProblem:
    """The same problem with every cap set to k, i.e. no effective band constraint."""
    return ShortlistProblem(
        candidate_ids=problem.candidate_ids,
        scores=problem.scores,
        band_of=problem.band_of,
        k=problem.k,
        caps=np.full(problem.n_bands, problem.k, dtype="int64"),
        band_labels=problem.band_labels,
        user_id=problem.user_id,
    )
