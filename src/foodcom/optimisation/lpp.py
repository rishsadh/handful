"""The core linear programme.

For user u, over eligible unseen candidate recipes C_u with relevance scores s_ui:

    maximise    sum_{i in C_u} s_ui x_i
    subject to  sum_{i in C_u} x_i = k
                sum_{i in G_g}  x_i <= b_g     for every preparation-time band g
                0 <= x_i <= 1

The variables are **continuous**. This is not a binary MIP, and the whole point of the
model is that it does not need to be. Because the bands partition the candidates - every
recipe has exactly one parent group - the constraint matrix is that of a min-cost flow
problem with integer supplies and capacities, so a basic optimal solution is integral.
`optimisation.integrality` sets out the argument; `verify_solution` checks the claim on
every single solve rather than trusting it.

Deliberately absent: price constraints, summed calories, total preparation-time limits,
pairwise diversity penalties, overlapping quota groups, transportation costs. Each of
those either requires data this dataset does not contain, or breaks the partition
structure the integrality guarantee rests on.

SciPy minimises, so the objective vector passed to the solver is `c = -s`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from foodcom.utils import logging as flog

log = flog.get_logger(__name__)

DEFAULT_TOL = 1e-7


@dataclass(frozen=True)
class ShortlistProblem:
    """One user's shortlist problem, fully specified before any solving happens."""

    candidate_ids: np.ndarray  # (n,) int64
    scores: np.ndarray  # (n,) float64, the objective coefficients
    band_of: np.ndarray  # (n,) int64, band index per candidate
    k: int
    caps: np.ndarray  # (n_bands,) int64
    band_labels: tuple[str, ...]
    user_id: int | None = None

    def __post_init__(self) -> None:
        n = len(self.candidate_ids)
        if len(self.scores) != n or len(self.band_of) != n:
            raise ValueError("candidate_ids, scores and band_of must be the same length")
        if len(self.caps) != len(self.band_labels):
            raise ValueError("caps and band_labels must be the same length")
        if self.band_of.size and (self.band_of.min() < 0 or self.band_of.max() >= len(self.caps)):
            raise ValueError("band_of contains an index outside the configured bands")
        if self.k <= 0:
            raise ValueError("k must be positive")

    @property
    def n(self) -> int:
        return len(self.candidate_ids)

    @property
    def n_bands(self) -> int:
        return len(self.caps)

    def band_sizes(self) -> np.ndarray:
        return np.bincount(self.band_of, minlength=self.n_bands).astype("int64")


@dataclass
class FeasibilityReport:
    feasible: bool
    k: int
    band_sizes: list[int]
    caps: list[int]
    capacity: int
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "k": self.k,
            "band_sizes": self.band_sizes,
            "caps": self.caps,
            "reachable_capacity": self.capacity,
            "reason": self.reason,
        }


def check_feasibility(problem: ShortlistProblem) -> FeasibilityReport:
    """`sum_g min(b_g, |G_g ∩ C_u|) >= k` - the exact condition for a feasible shortlist.

    Cheap, exact, and run before every solve. An infeasible profile is recorded as such;
    it is never rescued by quietly relaxing a cap.
    """
    sizes = problem.band_sizes()
    capacity = int(np.minimum(problem.caps, sizes).sum())
    ok = capacity >= problem.k
    reason = None
    if not ok:
        reason = (
            f"reachable capacity {capacity} < k={problem.k}: with caps "
            f"{problem.caps.tolist()} and band sizes {sizes.tolist()} no feasible "
            "shortlist of the required length exists"
        )
    return FeasibilityReport(
        feasible=ok,
        k=problem.k,
        band_sizes=sizes.tolist(),
        caps=problem.caps.tolist(),
        capacity=capacity,
        reason=reason,
    )


@dataclass
class VerificationReport:
    """Structural checks run on every solution. All of them must pass."""

    solver_success: bool
    status: int
    message: str
    equality_residual: float
    max_bound_violation: float
    max_capacity_violation: float
    max_distance_to_integer: float
    n_selected: int
    n_unique_selected: int
    integral: bool
    tolerance: float
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "solver_success": self.solver_success,
            "solver_status": self.status,
            "solver_message": self.message,
            "equality_residual": self.equality_residual,
            "max_bound_violation": self.max_bound_violation,
            "max_capacity_violation": self.max_capacity_violation,
            "max_distance_to_integer": self.max_distance_to_integer,
            "n_selected": self.n_selected,
            "n_unique_selected": self.n_unique_selected,
            "integral_within_tolerance": self.integral,
            "tolerance": self.tolerance,
            "checks_passed": self.ok,
            "problems": self.problems,
        }


@dataclass
class PrimalSolution:
    problem: ShortlistProblem
    x: np.ndarray
    objective: float
    selected_ids: np.ndarray
    ranked_ids: np.ndarray
    verification: VerificationReport
    feasibility: FeasibilityReport
    solve_seconds: float
    pruned: bool
    n_variables_solved: int
    raw_result: Any = None

    @property
    def ok(self) -> bool:
        return self.verification.ok

    def band_usage(self) -> dict[str, int]:
        pos = {int(r): i for i, r in enumerate(self.problem.candidate_ids)}
        usage = dict.fromkeys(self.problem.band_labels, 0)
        for rid in self.selected_ids:
            usage[self.problem.band_labels[int(self.problem.band_of[pos[int(rid)]])]] += 1
        return usage

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.problem.user_id,
            "k": self.problem.k,
            "caps": self.problem.caps.tolist(),
            "n_candidates": self.problem.n,
            "n_variables_solved": self.n_variables_solved,
            "band_pruning_applied": self.pruned,
            "objective_value": self.objective,
            "selected_recipe_ids": self.selected_ids.tolist(),
            "ranked_recipe_ids": self.ranked_ids.tolist(),
            "band_usage": self.band_usage(),
            "feasibility": self.feasibility.as_dict(),
            "verification": self.verification.as_dict(),
            "solve_seconds": self.solve_seconds,
        }


# --------------------------------------------------------------------------- building


def build_constraints(problem: ShortlistProblem) -> dict[str, Any]:
    """The LP matrices, in the form SciPy's `linprog` expects (a minimisation)."""
    n = problem.n
    a_eq = csr_matrix(np.ones((1, n), dtype="float64"))
    b_eq = np.array([float(problem.k)])

    rows, cols = [], []
    for i, g in enumerate(problem.band_of):
        rows.append(int(g))
        cols.append(i)
    a_ub = csr_matrix(
        (np.ones(n, dtype="float64"), (rows, cols)), shape=(problem.n_bands, n)
    )
    b_ub = problem.caps.astype("float64")

    return {
        "c": -problem.scores.astype("float64"),  # SciPy minimises; we maximise score
        "A_eq": a_eq,
        "b_eq": b_eq,
        "A_ub": a_ub,
        "b_ub": b_ub,
        "bounds": (0.0, 1.0),
    }


def prune_to_top_per_band(problem: ShortlistProblem) -> tuple[ShortlistProblem, np.ndarray]:
    """Keep at most the top `b_g` scored candidates in each band.

    Exact for this restricted structure: no optimal solution can ever use a
    (b_g + 1)-th best candidate in band g, because it could be swapped for a
    better-scoring one in the same band without touching any constraint.

    This is a primal-shortlist speedup only. Evaluation denominators still use the full
    catalogue, and reported dual certificates are produced from the unpruned problem,
    since pruning removes the very constraints whose sensitivity we want to interpret.
    """
    keep: list[int] = []
    # Deterministic tie handling: higher score first, then lower recipe id.
    order = np.lexsort((problem.candidate_ids, -problem.scores))
    remaining = problem.caps.copy()
    for idx in order:
        g = int(problem.band_of[idx])
        if remaining[g] > 0:
            keep.append(int(idx))
            remaining[g] -= 1
    keep_arr = np.sort(np.asarray(keep, dtype="int64"))
    pruned = ShortlistProblem(
        candidate_ids=problem.candidate_ids[keep_arr],
        scores=problem.scores[keep_arr],
        band_of=problem.band_of[keep_arr],
        k=problem.k,
        caps=problem.caps,
        band_labels=problem.band_labels,
        user_id=problem.user_id,
    )
    return pruned, keep_arr


# --------------------------------------------------------------------------- solving


def verify_solution(
    problem: ShortlistProblem,
    x: np.ndarray,
    *,
    success: bool,
    status: int,
    message: str,
    tol: float = DEFAULT_TOL,
) -> VerificationReport:
    """Check the solver's answer against every structural property the model claims."""
    problems: list[str] = []

    eq_residual = float(abs(x.sum() - problem.k))
    bound_violation = float(max(0.0, float((-x).max(initial=0.0)),
                                float((x - 1.0).max(initial=0.0))))

    usage = np.zeros(problem.n_bands, dtype="float64")
    np.add.at(usage, problem.band_of, x)
    cap_violation = float((usage - problem.caps).max(initial=0.0))
    cap_violation = max(cap_violation, 0.0)

    dist_to_int = float(np.abs(x - np.round(x)).max(initial=0.0))
    selected = np.where(np.round(x) > 0.5)[0]
    n_selected = len(selected)
    n_unique = len(np.unique(problem.candidate_ids[selected]))

    if not success:
        problems.append(f"solver did not report success (status {status}: {message})")
    if eq_residual > tol:
        problems.append(f"equality residual {eq_residual:.3g} exceeds tolerance {tol:g}")
    if bound_violation > tol:
        problems.append(f"bound violation {bound_violation:.3g} exceeds tolerance {tol:g}")
    if cap_violation > tol:
        problems.append(f"band capacity violation {cap_violation:.3g} exceeds tolerance {tol:g}")
    if dist_to_int > tol:
        problems.append(
            f"fractional solution: max distance to integer {dist_to_int:.3g} exceeds "
            f"tolerance {tol:g}. This is a FAILED STRUCTURAL TEST, not permission to round."
        )
    if n_selected != problem.k:
        problems.append(f"selected {n_selected} items, expected exactly k={problem.k}")
    if n_unique != n_selected:
        problems.append(f"selection contains duplicates: {n_selected} items, {n_unique} unique")

    return VerificationReport(
        solver_success=bool(success),
        status=int(status),
        message=str(message),
        equality_residual=eq_residual,
        max_bound_violation=bound_violation,
        max_capacity_violation=cap_violation,
        max_distance_to_integer=dist_to_int,
        n_selected=n_selected,
        n_unique_selected=n_unique,
        integral=dist_to_int <= tol,
        tolerance=tol,
        problems=problems,
    )


def rank_selection(problem: ShortlistProblem, selected_idx: np.ndarray) -> np.ndarray:
    """Order the chosen set: score descending, then recipe id ascending.

    The LP returns a set, not a ranking, but NDCG needs positions. This tie-break is
    documented and deterministic, so a repeated run produces an identical ranked list.
    """
    ids = problem.candidate_ids[selected_idx]
    scores = problem.scores[selected_idx]
    order = np.lexsort((ids, -scores))
    return ids[order]


def solve_primal(
    problem: ShortlistProblem,
    *,
    method: str = "highs-ds",
    tol: float = DEFAULT_TOL,
    prune: bool = True,
) -> PrimalSolution:
    """Solve one user's shortlist LP and verify the answer."""
    import time

    feas = check_feasibility(problem)
    if not feas.feasible:
        return PrimalSolution(
            problem=problem,
            x=np.zeros(problem.n),
            objective=float("nan"),
            selected_ids=np.array([], dtype="int64"),
            ranked_ids=np.array([], dtype="int64"),
            verification=VerificationReport(
                solver_success=False,
                status=-1,
                message="not solved: structurally infeasible",
                equality_residual=float("nan"),
                max_bound_violation=float("nan"),
                max_capacity_violation=float("nan"),
                max_distance_to_integer=float("nan"),
                n_selected=0,
                n_unique_selected=0,
                integral=False,
                tolerance=tol,
                problems=[feas.reason or "infeasible"],
            ),
            feasibility=feas,
            solve_seconds=0.0,
            pruned=False,
            n_variables_solved=0,
        )

    solve_problem, keep_idx = (prune_to_top_per_band(problem) if prune else (problem, None))
    parts = build_constraints(solve_problem)

    t0 = time.perf_counter()
    res = linprog(
        c=parts["c"],
        A_ub=parts["A_ub"],
        b_ub=parts["b_ub"],
        A_eq=parts["A_eq"],
        b_eq=parts["b_eq"],
        bounds=parts["bounds"],
        method=method,
    )
    elapsed = time.perf_counter() - t0

    x_solved = np.asarray(res.x, dtype="float64") if res.x is not None else np.zeros(
        solve_problem.n
    )
    verification = verify_solution(
        solve_problem,
        x_solved,
        success=bool(res.success),
        status=int(res.status),
        message=str(res.message),
        tol=tol,
    )

    # Lift the solution back onto the full candidate vector so callers always see the
    # same coordinate system regardless of pruning.
    if keep_idx is not None:
        x_full = np.zeros(problem.n, dtype="float64")
        x_full[keep_idx] = x_solved
    else:
        x_full = x_solved

    selected_idx = np.where(np.round(x_full) > 0.5)[0]
    objective = float(problem.scores[selected_idx].sum()) if verification.ok else float(
        -res.fun if res.fun is not None else np.nan
    )

    return PrimalSolution(
        problem=problem,
        x=x_full,
        objective=objective,
        selected_ids=problem.candidate_ids[selected_idx],
        ranked_ids=rank_selection(problem, selected_idx),
        verification=verification,
        feasibility=feas,
        solve_seconds=elapsed,
        pruned=keep_idx is not None,
        n_variables_solved=solve_problem.n,
        raw_result=res,
    )


def make_problem(
    candidate_ids: np.ndarray,
    scores: np.ndarray,
    bands: np.ndarray,
    k: int,
    cap: int,
    band_labels: list[str] | tuple[str, ...],
    user_id: int | None = None,
) -> ShortlistProblem:
    """Convenience builder with a uniform cap across all bands."""
    return ShortlistProblem(
        candidate_ids=np.asarray(candidate_ids, dtype="int64"),
        scores=np.asarray(scores, dtype="float64"),
        band_of=np.asarray(bands, dtype="int64"),
        k=int(k),
        caps=np.full(len(band_labels), int(cap), dtype="int64"),
        band_labels=tuple(band_labels),
        user_id=user_id,
    )
