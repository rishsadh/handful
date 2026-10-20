"""Relevance scoring.

    s(u, i) = (1 + cosine(p_u, e_i)) / 2

Both operands are unit vectors, so the cosine is a dot product and the result lands in
[0, 1] by construction. Clipping exists only to absorb floating-point drift a few ulps
outside the interval - if a value ever lands meaningfully outside, that is a bug in
normalisation, not something to quietly clamp.

What the score means: estimated semantic similarity between a recipe's text and the mean
of the texts a user rated 4-5 in the past. It is **not** a predicted rating, a probability
of enjoyment, or a satisfaction estimate. Every table and figure label must say
"AI relevance score".
"""

from __future__ import annotations

import numpy as np

from foodcom.features.embed import EmbeddingStore
from foodcom.features.profiles import ProfileStore

SCORE_MEANING = (
    "Estimated semantic relevance: the shifted cosine between a frozen sentence-encoder "
    "representation of the recipe text and the mean representation of the user's "
    "pre-cutoff positively rated recipes. Not a predicted rating, not a probability, not "
    "a satisfaction estimate."
)

_DRIFT_TOL = 1e-5


def half_shifted_cosine(profile: np.ndarray, recipes: np.ndarray) -> np.ndarray:
    """`(1 + cos) / 2` for one profile against an (n, d) recipe matrix."""
    cos = recipes @ profile
    scores = (1.0 + cos) / 2.0
    if np.any(scores < -_DRIFT_TOL) or np.any(scores > 1.0 + _DRIFT_TOL):
        raise AssertionError(
            "score left [0,1] by more than floating-point drift; check that both the "
            "profile and the recipe vectors are unit-normalised"
        )
    return np.clip(scores, 0.0, 1.0).astype("float64")


def score_candidates(
    user_id: int,
    candidate_ids: np.ndarray,
    profiles: ProfileStore,
    store: EmbeddingStore,
) -> np.ndarray:
    """AI relevance scores for one user over an array of candidate recipe ids."""
    if not profiles.has(user_id):
        raise KeyError(f"no profile for user {user_id}; cold users have no AI score")
    profile = profiles.vector(user_id)
    if float(np.linalg.norm(profile)) == 0.0:
        raise ValueError(f"user {user_id} has a zero-norm profile and is cold")
    return half_shifted_cosine(profile, store.matrix_for(candidate_ids))


def popularity_candidate_scores(
    candidate_ids: np.ndarray, popularity: dict[int, int] | np.ndarray
) -> np.ndarray:
    """Pre-cutoff positive-review counts, aligned to `candidate_ids`.

    Returned as raw counts. The LP maximises them directly; no normalisation is applied
    because a monotone transform would not change the selection.
    """
    if isinstance(popularity, dict):
        return np.fromiter(
            (float(popularity.get(int(r), 0)) for r in candidate_ids),
            dtype="float64",
            count=len(candidate_ids),
        )
    return np.asarray(popularity, dtype="float64")
