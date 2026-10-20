"""Preparation-time bands.

Four disjoint, exhaustive groups over positive finite reported minutes:

    G1: 0 < m <= 15
    G2: 15 < m <= 30
    G3: 30 < m <= 60
    G4:      m > 60

Upper-inclusive boundaries. A 15-minute recipe is in G1, not G2. The bands must stay
disjoint and exhaustive: the integrality argument for the LP depends on every recipe
having exactly one parent group.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from foodcom.utils.config import ProtocolCfg


def band_index(minutes: float, edges: list[float]) -> int:
    """0-based band index for a single positive minutes value."""
    if not np.isfinite(minutes) or minutes <= 0:
        raise ValueError(
            f"minutes={minutes!r} is not positive and finite; such recipes are excluded "
            "from the core banded model rather than assigned to a band"
        )
    for i, edge in enumerate(edges):
        if minutes <= edge:
            return i
    return len(edges)


def band_label(minutes: float, protocol: ProtocolCfg) -> str:
    return protocol.band_labels[band_index(minutes, protocol.band_edges)]


def assign_bands(minutes: pd.Series, protocol: ProtocolCfg) -> pd.Series:
    """Vectorised band labels for a Series of minutes.

    Non-positive or non-finite values yield `pd.NA`; the caller is expected to have
    excluded them already, and the NA makes an oversight visible instead of silent.
    """
    m = pd.to_numeric(minutes, errors="coerce").astype("Float64")
    valid = m.notna() & (m > 0) & np.isfinite(m.fillna(0).astype(float))

    edges = protocol.band_edges
    labels = protocol.band_labels
    # np.searchsorted with side="left" maps m <= edges[i] to index i, which is exactly
    # the upper-inclusive rule.
    idx = np.searchsorted(np.asarray(edges, dtype=float), m.fillna(-1).astype(float), side="left")
    out = pd.Series(pd.NA, index=minutes.index, dtype="string")
    out.loc[valid] = pd.Series(
        [labels[i] for i in idx], index=minutes.index, dtype="string"
    ).loc[valid]
    return out


def band_counts(minutes: pd.Series, protocol: ProtocolCfg) -> pd.DataFrame:
    bands = assign_bands(minutes, protocol)
    counts = bands.value_counts(dropna=False)
    rows = []
    for label in protocol.band_labels:
        rows.append({"band": label, "n_recipes": int(counts.get(label, 0))})
    unassigned = int(counts.get(pd.NA, 0)) if pd.NA in counts.index else int(bands.isna().sum())
    rows.append({"band": "unassigned_invalid_minutes", "n_recipes": unassigned})
    return pd.DataFrame(rows)


def band_bounds_text(protocol: ProtocolCfg) -> dict[str, str]:
    """Human-readable band definitions, for figure captions and the demo."""
    edges = protocol.band_edges
    labels = protocol.band_labels
    out: dict[str, str] = {}
    lo = 0.0
    for i, label in enumerate(labels):
        if i < len(edges):
            out[label] = f"{lo:g} < minutes <= {edges[i]:g}"
            lo = edges[i]
        else:
            out[label] = f"minutes > {lo:g}"
    return out
