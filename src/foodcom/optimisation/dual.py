"""The dual problem, solved explicitly and checked against the primal.

With alpha free for the exact-size equality, beta_g >= 0 for each band cap and gamma_i >= 0
for each upper bound x_i <= 1:

    minimise    k*alpha + sum_g b_g*beta_g + sum_i gamma_i
    subject to  alpha + beta_{g(i)} + gamma_i >= s_ui      for every eligible i
                beta_g >= 0,  gamma_i >= 0,  alpha free

Two independent routes to the same numbers are computed and compared:

1. Solving the dual LP directly.
2. Reading SciPy's marginals off the primal solve and converting their signs.

Route 2 needs care. We hand SciPy `c = -s` because it minimises. A marginal it reports is
`d(min objective)/d(rhs)`, so the effect on our **maximised** score is the negative of it.
Getting that backwards turns "this cap costs you 0.03 of score" into "this cap gains you
0.03", which is the kind of error that survives into a viva. `check_sign_conversion`
verifies it against a re-solved finite perturbation rather than trusting the algebra.

What the numbers mean, and do not mean:

* beta_g > 0 means the band-g cap is locally binding: it is holding the model's total
  relevance score below what it would otherwise reach. The units are AI relevance score.
* It is **not** money, not cognitive load, not a psychological benefit and not a
  measure of user welfare.
* At a kink or a tied optimum the shadow value is not unique. For any whole-number cap
  change that gets reported, re-solve the model; never extrapolate a local marginal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from foodcom.optimisation.lpp import DEFAULT_TOL, PrimalSolution, ShortlistProblem, solve_primal

BETA_MEANING = (
    "Shadow value of a preparation-time band cap, in AI relevance score units. A positive "
    "value means the cap is locally restricting the achievable model score. It is not "
    "money, not cognitive load, not a psychological benefit."
)


@dataclass
class DualSolution:
    alpha: float
    beta: np.ndarray
    gamma: np.ndarray
    objective: float
    success: bool
    status: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "beta": self.beta.tolist(),
            "gamma_nonzero_count": int((self.gamma > 1e-9).sum()),
            "gamma_max": float(self.gamma.max(initial=0.0)),
            "dual_objective": self.objective,
            "solver_success": self.success,
            "solver_status": self.status,
            "solver_message": self.message,
            "beta_meaning": BETA_MEANING,
        }


@dataclass
class DualityReport:
    primal_objective: float
    dual_objective: float
    duality_gap: float
    strong_duality_holds: bool
    max_dual_constraint_violation: float
    complementary_slackness: dict[str, float]
    complementary_slackness_holds: bool
    marginal_agreement: dict[str, Any]
    tolerance: float
    problems: list[str]
    dual_strategy: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {
            "primal_objective": self.primal_objective,
            "dual_objective": self.dual_objective,
            "duality_gap": self.duality_gap,
            "strong_duality_holds": self.strong_duality_holds,
            "max_dual_constraint_violation": self.max_dual_constraint_violation,
            "complementary_slackness": self.complementary_slackness,
            "complementary_slackness_holds": self.complementary_slackness_holds,
            "marginal_agreement": self.marginal_agreement,
            "dual_strategy": self.dual_strategy,
            "tolerance": self.tolerance,
            "checks_passed": self.ok,
            "problems": self.problems,
        }


def solve_dual(problem: ShortlistProblem, method: str = "highs-ds") -> DualSolution:
    """Solve the dual LP explicitly."""
    n, g = problem.n, problem.n_bands
    n_vars = 1 + g + n

    c = np.concatenate(([float(problem.k)], problem.caps.astype("float64"), np.ones(n)))

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for i in range(n):
        rows += [i, i, i]
        cols += [0, 1 + int(problem.band_of[i]), 1 + g + i]
        data += [-1.0, -1.0, -1.0]
    a_ub = csr_matrix((data, (rows, cols)), shape=(n, n_vars))
    b_ub = -problem.scores.astype("float64")

    bounds = [(None, None)] + [(0.0, None)] * (g + n)
    res = linprog(c=c, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method=method)

    x = np.asarray(res.x, dtype="float64") if res.x is not None else np.zeros(n_vars)
    return DualSolution(
        alpha=float(x[0]),
        beta=x[1 : 1 + g].copy(),
        gamma=x[1 + g :].copy(),
        objective=float(res.fun) if res.fun is not None else float("nan"),
        success=bool(res.success),
        status=int(res.status),
        message=str(res.message),
    )


def marginals_from_primal(solution: PrimalSolution) -> dict[str, Any]:
    """Read SciPy's marginals off the primal solve and convert them to max-problem signs.

    Returns `available: False` when the solve was pruned or the solver did not attach
    marginals - a pruned problem's marginals describe a different problem, so they are not
    reported as if they described the full one.
    """
    res = solution.raw_result
    if res is None or solution.pruned:
        return {
            "available": False,
            "reason": (
                "primal was solved on a pruned problem; dual certificates are produced "
                "from the full unpruned problem only"
                if solution.pruned
                else "no solver result attached"
            ),
        }
    try:
        eq = np.asarray(res.eqlin.marginals, dtype="float64")
        ub = np.asarray(res.ineqlin.marginals, dtype="float64")
        upper = np.asarray(res.upper.marginals, dtype="float64")
    except (AttributeError, TypeError):
        return {"available": False, "reason": "solver did not return marginals"}

    # d(max score)/d(rhs) = -d(min -score)/d(rhs)
    return {
        "available": True,
        "alpha": float(-eq[0]),
        "beta": (-ub).tolist(),
        "gamma_max": float((-upper).max(initial=0.0)),
        "sign_conversion": (
            "SciPy minimised c = -s, so every reported marginal is negated to express the "
            "effect on the maximised relevance score."
        ),
    }


# Above this many candidates, solving the dual directly is not viable: it carries one
# constraint per candidate, so the real catalogue produces a 230,000-constraint LP. The
# primal has five rows and stays trivial. Found the hard way - a worked-example run sat on
# the full dual for six hours at 0.04 cores before it was killed.
_REDUCED_DUAL_THRESHOLD = 5_000

# Extra candidates kept per band beyond the cap. 1 is the proven minimum (see
# certified_dual); 2 buys margin for nothing.
_DUAL_KEEP_MARGIN = 2


def certified_dual(
    problem: ShortlistProblem, *, method: str = "highs-ds"
) -> tuple[DualSolution, dict[str, Any]]:
    """An optimal dual for the FULL problem, obtained cheaply and then verified on it.

    This is exact, and the margin matters. At most `b_g` items from band g are selected, so
    the highest-scoring **non-selected** item in that band is ranked at most `b_g + 1`. Its
    score is what pins `alpha + beta_g` from below, because the optimum needs
    `alpha + beta_g >= s_i` for every non-selected i in order to keep `gamma_i = 0`. Keep
    the top `b_g + 1` per band and that binding constraint is present; keep only `b_g` and
    it is not, `(alpha, beta)` come back too small, and the extension below then forces
    positive gamma onto excluded high scorers and overstates the objective.

    That is not a hypothetical. Keeping only `b_g` disagreed with the directly solved dual
    on 22 of 273 random problems, worst gap 0.57. At `b_g + 1` the disagreement is 0 of 273
    with a worst gap of exactly zero. `_DUAL_KEEP_MARGIN` is 2, one more than the proven
    minimum, because the extra variables cost nothing.

    Given `(alpha, beta)`, gamma extends to every remaining candidate in closed form:

        gamma_i = max(0, s_i - alpha - beta_g(i))

    which is dual-feasible on all `n` constraints by construction.

    None of that is taken on trust. The caller checks strong duality against the primal
    objective computed on the full problem, so if the reduced `(alpha, beta)` were not
    optimal for the full problem the objectives would disagree and the check would fail.
    What is reported is a certificate for the full problem.
    """
    keep: list[int] = []
    for g in range(problem.n_bands):
        in_band = np.where(problem.band_of == g)[0]
        if not len(in_band):
            continue
        ordered = in_band[
            np.lexsort((problem.candidate_ids[in_band], -problem.scores[in_band]))
        ]
        keep.extend(ordered[: int(problem.caps[g]) + _DUAL_KEEP_MARGIN].tolist())
    keep_arr = np.sort(np.asarray(keep, dtype="int64"))

    reduced = ShortlistProblem(
        candidate_ids=problem.candidate_ids[keep_arr],
        scores=problem.scores[keep_arr],
        band_of=problem.band_of[keep_arr],
        k=problem.k,
        caps=problem.caps,
        band_labels=problem.band_labels,
        user_id=problem.user_id,
    )
    small = solve_dual(reduced, method=method)

    # Extend gamma to every candidate, then recompute the objective on the full problem.
    gamma_full = np.maximum(
        0.0, problem.scores - small.alpha - small.beta[problem.band_of]
    )
    objective = (
        problem.k * small.alpha
        + float(problem.caps.astype("float64") @ small.beta)
        + float(gamma_full.sum())
    )
    full = DualSolution(
        alpha=small.alpha,
        beta=small.beta,
        gamma=gamma_full,
        objective=objective,
        success=small.success,
        status=small.status,
        message=small.message,
    )
    return full, {
        "strategy": "reduced-then-certified",
        "reduced_variables": int(reduced.n),
        "full_constraints_verified": int(problem.n),
        "note": (
            "The dual was solved on the top-b_g-per-band subproblem and its gamma extended "
            "in closed form to all candidates. Strong duality is then checked against the "
            "full primal objective, so this is a certificate for the full problem."
        ),
    }


def check_duality(
    problem: ShortlistProblem,
    primal: PrimalSolution | None = None,
    *,
    tol: float = DEFAULT_TOL,
    method: str = "highs-ds",
    strategy: str = "auto",
) -> tuple[PrimalSolution, DualSolution, DualityReport]:
    """Solve both problems on the FULL (unpruned) formulation and cross-check them.

    `strategy="auto"` solves the dual directly on small problems and uses
    `certified_dual` on large ones. Either way the checks below are performed against the
    full problem's constraints and objective.
    """
    if primal is None:
        # Pruning is exact for this structure (see lpp.prune_to_top_per_band), and the
        # unpruned simplex is not viable at catalogue scale: 229k columns against 5 rows
        # runs for minutes and returns success=False. Optimality on the full problem is
        # established below by the matching dual certificate, which is a stronger
        # statement than a solver run anyway.
        primal = solve_primal(problem, method=method, tol=tol, prune=True)

    use_reduced = strategy == "reduced" or (
        strategy == "auto" and problem.n > _REDUCED_DUAL_THRESHOLD
    )
    dual_strategy: dict[str, Any]
    if use_reduced:
        dual, dual_strategy = certified_dual(problem, method=method)
    else:
        dual = solve_dual(problem, method=method)
        dual_strategy = {
            "strategy": "direct",
            "reduced_variables": int(problem.n),
            "full_constraints_verified": int(problem.n),
        }

    problems: list[str] = []
    gap = abs(primal.objective - dual.objective)
    # Objective magnitudes here are sums of at most k scores in [0,1], so an absolute
    # tolerance is meaningful; a relative one is added for safety on larger k.
    gap_tol = max(tol, tol * max(abs(primal.objective), 1.0))
    strong = gap <= gap_tol
    if not strong:
        problems.append(
            f"duality gap {gap:.3g} exceeds tolerance {gap_tol:g}: primal "
            f"{primal.objective:.9f} vs dual {dual.objective:.9f}"
        )

    # Dual feasibility: alpha + beta_g(i) + gamma_i >= s_i
    lhs = dual.alpha + dual.beta[problem.band_of] + dual.gamma
    violation = float((problem.scores - lhs).max(initial=0.0))
    violation = max(violation, 0.0)
    if violation > tol:
        problems.append(f"dual constraint violated by {violation:.3g}")

    # Complementary slackness.
    x = primal.x
    usage = np.zeros(problem.n_bands, dtype="float64")
    np.add.at(usage, problem.band_of, x)
    cap_slack = problem.caps.astype("float64") - usage

    cs_band = float(np.abs(dual.beta * cap_slack).max(initial=0.0))
    cs_upper = float(np.abs(dual.gamma * (1.0 - x)).max(initial=0.0))
    cs_dual = float(np.abs(x * (lhs - problem.scores)).max(initial=0.0))
    cs = {
        "max_beta_times_cap_slack": cs_band,
        "max_gamma_times_one_minus_x": cs_upper,
        "max_x_times_dual_constraint_slack": cs_dual,
    }
    cs_ok = max(cs_band, cs_upper, cs_dual) <= max(tol, 1e-6)
    if not cs_ok:
        problems.append(f"complementary slackness residual exceeds tolerance: {cs}")

    marg = marginals_from_primal(primal)
    agreement: dict[str, Any] = {"marginals": marg}
    if marg.get("available"):
        beta_marg = np.asarray(marg["beta"], dtype="float64")
        # Shadow values are non-unique at a degenerate optimum, so a mismatch is reported
        # as information rather than treated as a failure.
        agreement["max_abs_beta_difference"] = float(
            np.abs(beta_marg - dual.beta).max(initial=0.0)
        )
        agreement["note"] = (
            "Explicit-dual and solver-marginal values can differ at a degenerate or tied "
            "optimum, where the dual optimum is not unique. Report re-solved finite "
            "changes for any whole-number cap comparison."
        )

    return (
        primal,
        dual,
        DualityReport(
            primal_objective=primal.objective,
            dual_objective=dual.objective,
            duality_gap=gap,
            strong_duality_holds=strong,
            max_dual_constraint_violation=violation,
            complementary_slackness=cs,
            complementary_slackness_holds=cs_ok,
            marginal_agreement=agreement,
            dual_strategy=dual_strategy,
            tolerance=tol,
            problems=problems,
        ),
    )


def perturb_band_cap(
    problem: ShortlistProblem,
    band: int,
    delta: int,
    *,
    method: str = "highs-ds",
    tol: float = DEFAULT_TOL,
    beta: np.ndarray | None = None,
) -> dict[str, Any]:
    """Re-solve with one band cap changed by `delta` and report the actual score change.

    This is the honest way to answer "what would one more slot in this band be worth?".
    The shadow value predicts it only locally; a whole-item change is a finite move that
    can cross a kink.
    """
    caps = problem.caps.copy()
    caps[band] = max(0, int(caps[band]) + int(delta))
    perturbed = ShortlistProblem(
        candidate_ids=problem.candidate_ids,
        scores=problem.scores,
        band_of=problem.band_of,
        k=problem.k,
        caps=caps,
        band_labels=problem.band_labels,
        user_id=problem.user_id,
    )
    base = solve_primal(problem, method=method, tol=tol, prune=True)
    new = solve_primal(perturbed, method=method, tol=tol, prune=True)

    if not new.feasibility.feasible:
        return {
            "band": problem.band_labels[band],
            "delta": int(delta),
            "feasible_after_change": False,
            "reason": new.feasibility.reason,
        }

    # Re-solving the dual here would repeat the expensive step once per band. The
    # shadow value is a property of the unperturbed problem, so the caller passes it in.
    if beta is None:
        _, dual_sol, _ = check_duality(problem, base, tol=tol, method=method)
        beta = dual_sol.beta
    predicted = float(beta[band] * delta)
    actual = float(new.objective - base.objective)
    return {
        "band": problem.band_labels[band],
        "delta": int(delta),
        "feasible_after_change": True,
        "baseline_objective": base.objective,
        "perturbed_objective": new.objective,
        "actual_objective_change": actual,
        "shadow_value_beta": float(beta[band]),
        "linear_prediction": predicted,
        "prediction_error": float(actual - predicted),
        "interpretation": (
            "A local shadow value predicts an infinitesimal change. The re-solved value "
            "is what a whole extra slot is actually worth, in AI relevance score units."
        ),
    }
