"""The two-variable graphical slice.

Optional supporting syllabus material, not the solver. It takes a real solved user case,
fixes every selection variable except two, and leaves exactly one shortlist position open.
What remains is a genuine two-variable linear programme:

    maximise    s_a x_a + s_b x_b
    subject to  x_a + x_b = 1
                0 <= x_a <= 1,  0 <= x_b <= 1

whose feasible region is the segment from (1, 0) to (0, 1) in the unit square. The optimum
sits at whichever endpoint carries the higher score - which is exactly the intuition the
full model generalises.

This is a **slice** of the real model, and every export says so. It is not a claim that
the model has two variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from foodcom.optimisation.lpp import PrimalSolution, ShortlistProblem


@dataclass
class GraphicalSlice:
    user_id: int | None
    recipe_a: int
    recipe_b: int
    score_a: float
    score_b: float
    band_a: str
    band_b: str
    fixed_recipe_ids: list[int]
    fixed_objective: float
    optimal_vertex: tuple[float, float]
    optimal_recipe: int
    caption: str
    explanation: str

    def vertices(self) -> list[tuple[float, float]]:
        return [(1.0, 0.0), (0.0, 1.0)]

    def objective_at(self, xa: float, xb: float) -> float:
        return self.score_a * xa + self.score_b * xb

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "recipe_a": self.recipe_a,
            "recipe_b": self.recipe_b,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "band_a": self.band_a,
            "band_b": self.band_b,
            "fixed_recipe_ids": self.fixed_recipe_ids,
            "fixed_objective": self.fixed_objective,
            "feasible_segment": self.vertices(),
            "objective_at_vertices": [
                self.objective_at(*v) for v in self.vertices()
            ],
            "optimal_vertex": list(self.optimal_vertex),
            "optimal_recipe": self.optimal_recipe,
            "caption": self.caption,
            "explanation": self.explanation,
        }

    def to_frame(self):
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "vertex": f"({xa:g}, {xb:g})",
                    "x_a": xa,
                    "x_b": xb,
                    "recipe_selected": self.recipe_a if xa > 0.5 else self.recipe_b,
                    "slice_objective": self.objective_at(xa, xb),
                    "full_shortlist_objective": self.fixed_objective + self.objective_at(xa, xb),
                    "optimal": bool((xa, xb) == self.optimal_vertex),
                }
                for xa, xb in self.vertices()
            ]
        )


class SliceNotAvailable(RuntimeError):
    """Raised when a solved case cannot yield a valid two-variable slice."""


def build_slice(problem: ShortlistProblem, solution: PrimalSolution) -> GraphicalSlice:
    """Construct a two-variable slice from a solved case.

    Method: hold k-1 of the selected recipes fixed, freeing one position. Candidate `a` is
    the released recipe; candidate `b` is the best-scoring unselected recipe whose band
    still has room once the k-1 fixed items are accounted for. Both must fit the remaining
    capacities, otherwise the slice would not be a faithful piece of the real model.
    """
    if not solution.ok or len(solution.selected_ids) != problem.k:
        raise SliceNotAvailable("the source case must be a verified, exactly-k solution")
    if problem.k < 2:
        raise SliceNotAvailable("a slice needs at least two shortlist positions")

    pos = {int(r): i for i, r in enumerate(problem.candidate_ids)}
    selected_idx = np.asarray([pos[int(r)] for r in solution.selected_ids], dtype="int64")

    # Release the lowest-scoring selected recipe: it is the one most likely to have a
    # genuine competitor, which makes the picture informative rather than trivial.
    release_slot = int(np.argmin(problem.scores[selected_idx]))
    idx_a = int(selected_idx[release_slot])
    fixed_idx = np.delete(selected_idx, release_slot)

    used = np.zeros(problem.n_bands, dtype="int64")
    np.add.at(used, problem.band_of[fixed_idx], 1)
    remaining = problem.caps - used

    selected_set = {int(r) for r in solution.selected_ids}
    order = np.lexsort((problem.candidate_ids, -problem.scores))
    idx_b = None
    for cand in order:
        if int(problem.candidate_ids[cand]) in selected_set:
            continue
        if remaining[int(problem.band_of[cand])] >= 1:
            idx_b = int(cand)
            break
    if idx_b is None:
        raise SliceNotAvailable(
            "no unselected candidate fits the remaining band capacity; this user's case "
            "cannot produce a two-variable slice"
        )
    if remaining[int(problem.band_of[idx_a])] < 1:  # pragma: no cover - defensive
        raise SliceNotAvailable("the released recipe no longer fits the remaining capacity")

    score_a = float(problem.scores[idx_a])
    score_b = float(problem.scores[idx_b])
    fixed_objective = float(problem.scores[fixed_idx].sum())
    optimal_vertex = (1.0, 0.0) if score_a >= score_b else (0.0, 1.0)
    optimal_recipe = int(
        problem.candidate_ids[idx_a] if score_a >= score_b else problem.candidate_ids[idx_b]
    )

    winner, loser = (
        (score_a, score_b) if score_a >= score_b else (score_b, score_a)
    )
    explanation = (
        f"With {problem.k - 1} of the {problem.k} shortlist positions held fixed, one "
        f"position remains and exactly two candidates compete for it. The equality "
        f"constraint becomes x_a + x_b = 1, so the feasible region is the straight segment "
        f"between (1, 0) and (0, 1); the unit-interval bounds add nothing beyond it here. "
        f"The objective s_a x_a + s_b x_b is linear, so its maximum sits at an endpoint. "
        f"Recipe {optimal_recipe} wins with a relevance score of {winner:.4f} against "
        f"{loser:.4f}, a difference of {abs(score_a - score_b):.4f} score units. Any "
        f"interior point - splitting the position between the two - scores strictly less "
        f"than the better endpoint, which is why a fractional answer never pays here."
    )
    caption = (
        f"Two-variable slice of the shortlist LP for one real user"
        f"{f' (user {problem.user_id})' if problem.user_id is not None else ''}: "
        f"recipes {int(problem.candidate_ids[idx_a])} (band "
        f"{problem.band_labels[int(problem.band_of[idx_a])]}) and "
        f"{int(problem.candidate_ids[idx_b])} (band "
        f"{problem.band_labels[int(problem.band_of[idx_b])]}) competing for the final "
        f"position, with the other {problem.k - 1} selections held fixed. This is a slice "
        f"of the full {problem.n}-variable model, not the model itself."
    )

    return GraphicalSlice(
        user_id=problem.user_id,
        recipe_a=int(problem.candidate_ids[idx_a]),
        recipe_b=int(problem.candidate_ids[idx_b]),
        score_a=score_a,
        score_b=score_b,
        band_a=problem.band_labels[int(problem.band_of[idx_a])],
        band_b=problem.band_labels[int(problem.band_of[idx_b])],
        fixed_recipe_ids=[int(problem.candidate_ids[i]) for i in fixed_idx],
        fixed_objective=fixed_objective,
        optimal_vertex=optimal_vertex,
        optimal_recipe=optimal_recipe,
        caption=caption,
        explanation=explanation,
    )
