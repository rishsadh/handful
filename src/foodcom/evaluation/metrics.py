"""Offline metrics.

    Recall@k  = |L_u ∩ R_u| / |R_u|
    DCG@k     = sum_{j=1..k} 1[item_j ∈ R_u] / log2(j + 1)
    NDCG@k    = DCG@k / IDCG@k,  IDCG@k = sum_{j=1..min(k, |R_u|)} 1 / log2(j + 1)

where R_u is the set of eligible novel recipes the user rated 4 or 5 in the label window,
and L_u is the ranked k-item output.

Two disciplines are enforced here rather than left to the caller:

* Ranking metrics are defined only for users with |R_u| > 0. A user with no observed
  positive is not a zero - they are outside the conditional population, and averaging them
  in as zeros would silently depend on how many such users exist.
* Everything is macro-averaged per user. A review-weighted average would let the handful
  of users with hundreds of reviews decide the headline number.

Naming discipline: `reduction_ratio` is a descriptive identity, `1 - k/|C_u|`. It is not
a measure of psychological overload reduction, and runtimes are machine runtimes, never
human decision times.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

REDUCTION_MEANING = (
    "Descriptive identity 1 - k/|C_u|: the proportion of the eligible catalogue not shown. "
    "It is a property of the arithmetic, not evidence about attention, effort or "
    "psychological choice overload."
)

RUNTIME_MEANING = (
    "Machine runtime of the scoring and solving code. Never a human decision time."
)


def recall_at_k(ranked: Sequence[int], relevant: Iterable[int], k: int | None = None) -> float:
    """Fraction of the user's observed positives that appear in the shortlist.

    Undefined when the user has no observed positive; the caller must not evaluate such
    users. Returns NaN rather than 0 so a mistake surfaces instead of biasing a mean.
    """
    rel = {int(r) for r in relevant}
    if not rel:
        return float("nan")
    shortlist = list(ranked)[: k] if k is not None else list(ranked)
    hits = len({int(i) for i in shortlist} & rel)
    return hits / len(rel)


def dcg_at_k(ranked: Sequence[int], relevant: Iterable[int], k: int) -> float:
    rel = {int(r) for r in relevant}
    total = 0.0
    for j, item in enumerate(list(ranked)[:k], start=1):
        if int(item) in rel:
            total += 1.0 / math.log2(j + 1)
    return total


def idcg_at_k(n_relevant: int, k: int) -> float:
    """Best achievable DCG@k for a user with `n_relevant` observed positives."""
    return sum(1.0 / math.log2(j + 1) for j in range(1, min(k, n_relevant) + 1))


def ndcg_at_k(ranked: Sequence[int], relevant: Iterable[int], k: int) -> float:
    rel = {int(r) for r in relevant}
    if not rel:
        return float("nan")
    ideal = idcg_at_k(len(rel), k)
    if ideal == 0.0:  # pragma: no cover - unreachable while rel is non-empty and k >= 1
        return float("nan")
    return dcg_at_k(ranked, rel, k) / ideal


def bands_represented(ranked: Sequence[int], band_of: dict[int, str]) -> int:
    """How many distinct preparation-time bands the shortlist covers."""
    return len({band_of[int(i)] for i in ranked if int(i) in band_of})


def band_usage(ranked: Sequence[int], band_of: dict[int, str], labels: Sequence[str]) -> dict[
    str, int
]:
    usage = dict.fromkeys(labels, 0)
    for item in ranked:
        label = band_of.get(int(item))
        if label is not None:
            usage[label] += 1
    return usage


def cap_violations(usage: dict[str, int], caps: dict[str, int]) -> int:
    """Total overflow beyond the declared caps. AI_TOPK is expected to be non-zero here."""
    return sum(max(0, n - caps.get(label, n)) for label, n in usage.items())


def reduction_ratio(k: int, n_candidates: int) -> float:
    """`1 - k/|C_u|`, defined only when |C_u| >= k."""
    if n_candidates < k or n_candidates == 0:
        return float("nan")
    return 1.0 - (k / n_candidates)


@dataclass
class UserResult:
    """One (user, method) evaluation outcome."""

    user_id: int
    method: str
    stage: str
    k: int
    cap: int
    ranked_ids: list[int]
    n_candidates: int
    n_relevant: int
    recall: float
    ndcg: float
    bands_represented: int
    band_usage: dict[str, int]
    cap_violations: int
    exact_size_ok: bool
    feasible: bool
    solver_status: str
    failed: bool
    failure_reason: str | None
    reduction_ratio: float
    scoring_seconds: float
    solve_seconds: float
    total_seconds: float

    def as_row(self) -> dict[str, Any]:
        row = {
            "user_id": self.user_id,
            "method": self.method,
            "stage": self.stage,
            "k": self.k,
            "cap": self.cap,
            "n_candidates": self.n_candidates,
            "n_relevant": self.n_relevant,
            "recall_at_k": self.recall,
            "ndcg_at_k": self.ndcg,
            "bands_represented": self.bands_represented,
            "cap_violations": self.cap_violations,
            "exact_size_ok": self.exact_size_ok,
            "feasible": self.feasible,
            "solver_status": self.solver_status,
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "reduction_ratio": self.reduction_ratio,
            "scoring_seconds": self.scoring_seconds,
            "solve_seconds": self.solve_seconds,
            "total_seconds": self.total_seconds,
            "ranked_ids": ",".join(str(i) for i in self.ranked_ids),
        }
        for label, n in self.band_usage.items():
            row[f"band_{label}"] = n
        return row


def aggregate_per_method(results: pd.DataFrame) -> pd.DataFrame:
    """Macro-averaged per-method summary.

    Ranking metrics average only over rows where they are defined (n_relevant > 0). A
    failed method on a feasible input keeps its row with recall 0 - see
    `harness.evaluate_user` - so failures depress the mean rather than vanishing from it.
    """
    if results.empty:
        return pd.DataFrame()

    rows = []
    for (stage, method, k, cap), grp in results.groupby(
        ["stage", "method", "k", "cap"], dropna=False
    ):
        rankable = grp[grp["n_relevant"] > 0]
        rows.append(
            {
                "stage": stage,
                "method": method,
                "k": int(k),
                "cap": int(cap),
                "n_users_evaluated": len(grp),
                "n_users_with_positives": len(rankable),
                "mean_recall_at_k": float(rankable["recall_at_k"].mean())
                if len(rankable)
                else float("nan"),
                "mean_ndcg_at_k": float(rankable["ndcg_at_k"].mean())
                if len(rankable)
                else float("nan"),
                "mean_bands_represented": float(grp["bands_represented"].mean()),
                "mean_cap_violations": float(grp["cap_violations"].mean()),
                "pct_exact_size_ok": float(100.0 * grp["exact_size_ok"].mean()),
                "pct_feasible": float(100.0 * grp["feasible"].mean()),
                "failure_rate_pct": float(100.0 * grp["failed"].mean()),
                "mean_candidates": float(grp["n_candidates"].mean()),
                "mean_reduction_ratio": float(grp["reduction_ratio"].mean()),
                "mean_scoring_seconds": float(grp["scoring_seconds"].mean()),
                "mean_solve_seconds": float(grp["solve_seconds"].mean()),
                "mean_total_seconds": float(grp["total_seconds"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["stage", "k", "cap", "method"]).reset_index(drop=True)


def average_random_repeats(results: pd.DataFrame, method: str = "RANDOM") -> pd.DataFrame:
    """Collapse a method's repeated runs into one row per user.

    Twenty random draws for one user are twenty looks at the same user, not twenty
    independent samples. Averaging them here means the bootstrap that follows resamples
    users, which is the unit that actually varies.
    """
    if "repeat" not in results.columns:
        return results
    mask = results["method"] == method
    if not mask.any():
        return results.drop(columns=["repeat"], errors="ignore")

    numeric = [
        "recall_at_k",
        "ndcg_at_k",
        "bands_represented",
        "cap_violations",
        "reduction_ratio",
        "scoring_seconds",
        "solve_seconds",
        "total_seconds",
    ]
    keys = ["user_id", "method", "stage", "k", "cap"]
    rnd = results[mask]
    agg: dict[str, Any] = {c: "mean" for c in numeric if c in rnd.columns}
    agg.update(
        {
            "n_candidates": "first",
            "n_relevant": "first",
            "exact_size_ok": "mean",
            "feasible": "mean",
            "failed": "mean",
            "solver_status": "first",
            "failure_reason": "first",
        }
    )
    band_cols = [c for c in rnd.columns if c.startswith("band_")]
    agg.update(dict.fromkeys(band_cols, "mean"))

    collapsed = rnd.groupby(keys, as_index=False).agg(agg)
    collapsed["exact_size_ok"] = collapsed["exact_size_ok"] >= 0.5
    collapsed["feasible"] = collapsed["feasible"] >= 0.5
    collapsed["ranked_ids"] = "averaged over repeats"

    others = results[~mask].drop(columns=["repeat"], errors="ignore")
    return pd.concat([others, collapsed], ignore_index=True)
