"""History-only user profiles.

    p_u = normalise( mean over i in positive history of e_i )

Equal weights, no post-test tuning, and the history is strictly pre-cutoff. A profile is a
summary of what a user already liked, not a prediction of what they will like.

A user with no usable positive history, or whose vectors cancel to a zero norm, is flagged
cold. Cold users are excluded from every warm-user AI claim; the demo may show them a
clearly labelled popularity fallback instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from foodcom.features.embed import EmbeddingStore
from foodcom.utils import logging as flog

log = flog.get_logger(__name__)

_ZERO_NORM_TOL = 1e-12


@dataclass
class ProfileStore:
    user_ids: np.ndarray  # (n,) int64
    vectors: np.ndarray  # (n, d) float32, unit-normalised
    n_positive_used: np.ndarray  # (n,) int64
    cold_users: list[int]
    notes: dict[str, Any]

    def __post_init__(self) -> None:
        self._pos = {int(u): i for i, u in enumerate(self.user_ids)}

    def has(self, user_id: int) -> bool:
        return int(user_id) in self._pos

    def vector(self, user_id: int) -> np.ndarray:
        return self.vectors[self._pos[int(user_id)]]

    def n_used(self, user_id: int) -> int:
        return int(self.n_positive_used[self._pos[int(user_id)]])

    def __len__(self) -> int:
        return len(self.user_ids)


def build_profiles(
    positives: dict[int, set[int]],
    store: EmbeddingStore,
    users: list[int] | None = None,
) -> ProfileStore:
    """Mean-of-positive-history profiles for the requested users.

    `positives` must already be restricted to pre-cutoff events and to recipes present in
    the frozen catalogue; `splits.build_stage_split` does that.
    """
    target = list(users) if users is not None else sorted(positives)
    dim = store.dimension

    vectors = np.zeros((len(target), dim), dtype="float32")
    counts = np.zeros(len(target), dtype="int64")
    cold: list[int] = []
    n_missing_vectors = 0

    for slot, user_id in enumerate(target):
        recipe_ids = [r for r in sorted(positives.get(int(user_id), set())) if store.has(r)]
        n_missing_vectors += len(positives.get(int(user_id), set())) - len(recipe_ids)
        counts[slot] = len(recipe_ids)
        if not recipe_ids:
            cold.append(int(user_id))
            continue
        mat = store.matrix_for(np.asarray(recipe_ids, dtype="int64"))
        mean = mat.mean(axis=0)
        norm = float(np.linalg.norm(mean))
        if norm <= _ZERO_NORM_TOL:
            cold.append(int(user_id))
            continue
        vectors[slot] = (mean / norm).astype("float32")

    log.info("profiles: %d users, %d cold", len(target), len(cold))
    return ProfileStore(
        user_ids=np.asarray(target, dtype="int64"),
        vectors=vectors,
        n_positive_used=counts,
        cold_users=cold,
        notes={
            "weighting": "equal",
            "profile": "normalised mean of positively rated historical recipe vectors",
            "n_users": len(target),
            "n_cold_users": len(cold),
            "n_positive_recipes_without_vector": int(n_missing_vectors),
            "cold_definition": (
                "no usable positive history vector, or a mean vector with zero norm"
            ),
            "cold_handling": (
                "excluded from warm-user AI claims; the demo may show a labelled "
                "popularity fallback"
            ),
        },
    )
