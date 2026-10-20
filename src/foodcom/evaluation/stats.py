"""Paired user bootstrap.

Two preplanned comparisons, declared before any result was seen:

    AI_LP - POPULARITY_LP
    AI_LP - AI_TOPK

Both are paired on the same users. Each bootstrap resample draws users **with their whole
paired record**, because the user is the unit that varies; resampling (user, method) rows
independently would break the pairing and understate the correlation between methods that
share a candidate catalogue.

The 20 RANDOM repeats are averaged within each user before any of this runs. They are 20
looks at one user, not 20 users.

Formal p-values are not part of this protocol. If the professor asks for one, the test and
any correction must be specified before the final test set is touched. A test is never
chosen after seeing which one produces significance.

Reading the intervals honestly:

* They describe resampling uncertainty within this benchmark, on this catalogue, for this
  cohort. Users share recipes and were not sampled from any population of interest.
* An interval containing zero is not evidence of equivalence. Claiming "preserved quality"
  needs a non-inferiority margin declared in advance, which this protocol does not have.
* Where a baseline is near zero, report the absolute difference. A relative lift on a tiny
  base is a headline, not a finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


def interval_meaning(ci: float = 0.95, n_resamples: int = 2000, seed: int = 42) -> str:
    """How to read the intervals, stating the numbers the run actually used.

    Built from the live values rather than hardcoded: a caption claiming 2,000 resamples
    beneath a table computed from 200 is a small lie that a reader has no way to catch.
    """
    return (
        f"{ci:.0%} paired user-bootstrap interval over {n_resamples:,} resamples of users, "
        f"seed {seed}. Describes resampling uncertainty within this benchmark only. Not a "
        "population inference, and an interval containing zero is not evidence of "
        "equivalence."
    )


INTERVAL_MEANING = interval_meaning()


@dataclass
class PairedComparison:
    metric: str
    method_a: str
    method_b: str
    n_users: int
    mean_a: float
    mean_b: float
    mean_difference: float
    ci_low: float
    ci_high: float
    ci_level: float
    n_resamples: int
    seed: int
    interval_excludes_zero: bool

    def as_row(self) -> dict[str, Any]:
        # Fixed column names, so every comparison lines up in one table instead of
        # producing a sparse column per method name.
        return {
            "metric": self.metric,
            "method_a": self.method_a,
            "method_b": self.method_b,
            "n_paired_users": self.n_users,
            "mean_a": self.mean_a,
            "mean_b": self.mean_b,
            "mean_absolute_difference": self.mean_difference,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_level": self.ci_level,
            "n_bootstrap_resamples": self.n_resamples,
            "seed": self.seed,
            "interval_excludes_zero": self.interval_excludes_zero,
        }

    def as_dict(self) -> dict[str, Any]:
        # The JSON record carries the caption; the CSV does not, so the table is not
        # padded with the same paragraph on every row.
        return {
            **self.as_row(),
            "interval_meaning": interval_meaning(
                self.ci_level, self.n_resamples, self.seed
            ),
        }


def paired_matrix(
    results: pd.DataFrame, metric: str, method_a: str, method_b: str
) -> pd.DataFrame:
    """Users evaluated by both methods, with one row per user.

    Users missing from either method are dropped - a paired comparison over different
    populations is not a paired comparison - and the drop is reported by the caller.
    """
    required = {"method", "user_id", metric}
    if results.empty or not required <= set(results.columns):
        return pd.DataFrame(columns=[method_a, method_b])

    needed = results[results["method"].isin([method_a, method_b])]
    wide = needed.pivot_table(
        index="user_id", columns="method", values=metric, aggfunc="mean"
    )
    for m in (method_a, method_b):
        if m not in wide.columns:
            return pd.DataFrame(columns=[method_a, method_b])
    return wide[[method_a, method_b]].dropna()


def paired_bootstrap(
    results: pd.DataFrame,
    metric: str,
    method_a: str,
    method_b: str,
    *,
    n_resamples: int = 2000,
    seed: int = 42,
    ci: float = 0.95,
) -> PairedComparison:
    """Percentile bootstrap over users for `mean(a) - mean(b)`."""
    wide = paired_matrix(results, metric, method_a, method_b)
    n = len(wide)
    if n == 0:
        return PairedComparison(
            metric=metric, method_a=method_a, method_b=method_b, n_users=0,
            mean_a=float("nan"), mean_b=float("nan"), mean_difference=float("nan"),
            ci_low=float("nan"), ci_high=float("nan"), ci_level=ci,
            n_resamples=n_resamples, seed=seed, interval_excludes_zero=False,
        )

    a = wide[method_a].to_numpy(dtype="float64")
    b = wide[method_b].to_numpy(dtype="float64")
    diff = a - b

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    # Each row of `idx` is one resample of users; the paired difference travels with the
    # user, which is what keeps the pairing intact.
    boot = diff[idx].mean(axis=1)

    alpha = (1.0 - ci) / 2.0
    low, high = np.quantile(boot, [alpha, 1.0 - alpha])
    return PairedComparison(
        metric=metric,
        method_a=method_a,
        method_b=method_b,
        n_users=int(n),
        mean_a=float(a.mean()),
        mean_b=float(b.mean()),
        mean_difference=float(diff.mean()),
        ci_low=float(low),
        ci_high=float(high),
        ci_level=ci,
        n_resamples=n_resamples,
        seed=seed,
        interval_excludes_zero=bool(low > 0.0 or high < 0.0),
    )


def run_preplanned_comparisons(
    results: pd.DataFrame, cfg: Any
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Every preplanned comparison for both the primary and secondary metric."""
    from foodcom.evaluation.metrics import average_random_repeats

    protocol = cfg.research.protocol
    collapsed = average_random_repeats(results)
    rankable = collapsed[collapsed["n_relevant"] > 0]

    rows, details = [], []
    for metric in (protocol.primary_metric, protocol.secondary_metric):
        col = {"recall_at_k": "recall_at_k", "ndcg_at_k": "ndcg_at_k"}.get(metric, metric)
        for method_a, method_b in protocol.paired_comparisons:
            comp = paired_bootstrap(
                rankable,
                col,
                method_a,
                method_b,
                n_resamples=protocol.bootstrap_resamples,
                seed=protocol.bootstrap_seed,
                ci=protocol.bootstrap_ci,
            )
            rows.append(comp.as_row())
            details.append(comp.as_dict())
    return pd.DataFrame(rows), details


def denominator_table(results: pd.DataFrame, split_denominators: dict[str, Any]) -> pd.DataFrame:
    """Every denominator a reader needs to interpret the comparison table."""
    from foodcom.evaluation.metrics import average_random_repeats

    collapsed = average_random_repeats(results)
    rows = [{"quantity": k, "value": v} for k, v in split_denominators.items()]

    for method, grp in collapsed.groupby("method"):
        rows.extend(
            [
                {"quantity": f"{method}: users evaluated", "value": len(grp)},
                {
                    "quantity": f"{method}: users with >=1 eligible positive",
                    "value": int((grp["n_relevant"] > 0).sum()),
                },
                {
                    "quantity": f"{method}: users with a feasible shortlist",
                    "value": int(grp["feasible"].sum()),
                },
                {
                    "quantity": f"{method}: users in the paired metric denominator",
                    "value": int(((grp["n_relevant"] > 0) & grp["feasible"]).sum()),
                },
                {
                    "quantity": f"{method}: method failures on feasible input",
                    "value": int((grp["failed"] > 0).sum()),
                },
            ]
        )
    return pd.DataFrame(rows)


def common_success_subset(results: pd.DataFrame, methods: list[str]) -> pd.DataFrame:
    """Users where every method produced a feasible, non-failed shortlist.

    The primary table charges a failure as recall zero. This subset answers the different
    question "how do the methods compare where all of them worked?", and the two are
    reported side by side rather than one replacing the other.
    """
    from foodcom.evaluation.metrics import average_random_repeats

    collapsed = average_random_repeats(results)
    ok = collapsed[collapsed["method"].isin(methods)]
    good = ok[(ok["feasible"]) & (ok["failed"] == 0) & (ok["exact_size_ok"])]
    counts = good.groupby("user_id")["method"].nunique()
    users = set(counts[counts == len(methods)].index)
    return collapsed[collapsed["user_id"].isin(users)]
