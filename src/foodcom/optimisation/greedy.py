"""Independent oracles that must agree with the LP.

Two of them, deliberately written in a completely different style from the LP so a shared
mistake is unlikely:

* `greedy_select` - sort by score, take the best candidate whose band still has room. For
  this partition-cap structure that is provably optimal, and it is what makes the honest
  claim about the model possible: the LP is **not** computationally necessary here. Its
  value is a transparent formulation, a feasibility condition and a dual analysis, not
  speed.
* `enumerate_optimal` - brute force over every feasible k-subset. Only usable on tiny
  fixtures, which is exactly where it is used.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

from foodcom.optimisation.lpp import ShortlistProblem


def greedy_select(problem: ShortlistProblem) -> tuple[np.ndarray, float]:
    """Score-sorted, capacity-respecting greedy selection.

    Returns `(selected recipe ids in ranked order, objective)`. Returns an empty
    selection when the problem is structurally infeasible.
    """
    order = np.lexsort((problem.candidate_ids, -problem.scores))
    remaining = problem.caps.copy()
    chosen: list[int] = []
    for idx in order:
        if len(chosen) == problem.k:
            break
        g = int(problem.band_of[idx])
        if remaining[g] > 0:
            chosen.append(int(idx))
            remaining[g] -= 1
    if len(chosen) < problem.k:
        return np.array([], dtype="int64"), float("nan")
    chosen_arr = np.asarray(chosen, dtype="int64")
    return problem.candidate_ids[chosen_arr], float(problem.scores[chosen_arr].sum())


def enumerate_optimal(problem: ShortlistProblem, max_combinations: int = 500_000) -> tuple[
    np.ndarray, float
]:
    """Exhaustive search over feasible k-subsets. Tiny fixtures only.

    Raises if the search space exceeds `max_combinations` rather than running for hours.
    """
    from math import comb

    total = comb(problem.n, problem.k) if problem.k <= problem.n else 0
    if total == 0:
        return np.array([], dtype="int64"), float("nan")
    if total > max_combinations:
        raise ValueError(
            f"C({problem.n}, {problem.k}) = {total} exceeds max_combinations="
            f"{max_combinations}; enumeration is a fixture-scale check only"
        )

    best_idx: tuple[int, ...] | None = None
    best_obj = -np.inf
    for combo in combinations(range(problem.n), problem.k):
        arr = np.asarray(combo, dtype="int64")
        usage = np.bincount(problem.band_of[arr], minlength=problem.n_bands)
        if np.any(usage > problem.caps):
            continue
        obj = float(problem.scores[arr].sum())
        if obj > best_obj:
            best_obj, best_idx = obj, combo

    if best_idx is None:
        return np.array([], dtype="int64"), float("nan")
    arr = np.asarray(best_idx, dtype="int64")
    order = np.lexsort((problem.candidate_ids[arr], -problem.scores[arr]))
    return problem.candidate_ids[arr][order], best_obj


def unconstrained_topk(problem: ShortlistProblem) -> tuple[np.ndarray, float]:
    """Top-k by score, ignoring band caps.

    When every cap equals k the LP optimum must equal this objective exactly; that
    equality is one of the release tests.
    """
    order = np.lexsort((problem.candidate_ids, -problem.scores))[: problem.k]
    if len(order) < problem.k:
        return np.array([], dtype="int64"), float("nan")
    return problem.candidate_ids[order], float(problem.scores[order].sum())
