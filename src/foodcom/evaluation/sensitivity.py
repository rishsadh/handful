"""Predeclared sensitivity sweeps.

    length sweep:  (k=4, b=2), (k=6, b=3), (k=8, b=4)
    cap sweep:     k=6 with b=2, b=3, b=6      (b=6 removes the effective band cap)

Both are declared in `config/research.yaml` before any result is seen. Within a sweep
everything else is held fixed: the same users, the same profiles, the same candidate rules,
the same scores, the same dates and the same positive-rating definition. Only k and b move.

Infeasibility is recorded, not dropped. Tightening a cap makes some users structurally
infeasible, and losing them silently would make a tighter cap look better than it is by
quietly removing the users it hurt.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from foodcom.evaluation.harness import EvalContext, evaluate_stage
from foodcom.evaluation.metrics import aggregate_per_method
from foodcom.utils import logging as flog

log = flog.get_logger(__name__)


def run_sweep(
    ctx: EvalContext,
    points: list[dict[str, int]],
    *,
    sweep_name: str,
    methods: list[str] | None = None,
    users: list[int] | None = None,
    run: Any | None = None,
    allow_non_research_encoder: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run one sweep. Returns `(per-user rows, aggregated summary)`."""
    frames = []
    # Fixed across every point in the sweep: the population must not move with k.
    target = users if users is not None else ctx.split.ranking_users
    for point in points:
        k, cap = int(point["k"]), int(point["b"])
        log.info("sweep %s: k=%d b=%d", sweep_name, k, cap)
        frame = evaluate_stage(
            ctx,
            k=k,
            cap=cap,
            methods=methods,
            users=target,
            run=run,
            allow_non_research_encoder=allow_non_research_encoder,
        )
        frame["sweep"] = sweep_name
        frames.append(frame)

    per_user = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    summary = aggregate_per_method(per_user) if not per_user.empty else pd.DataFrame()
    if not summary.empty:
        summary["sweep"] = sweep_name
    return per_user, summary


def infeasibility_report(per_user: pd.DataFrame) -> pd.DataFrame:
    """How many users each (k, b) point makes structurally infeasible, by method."""
    if per_user.empty:
        return pd.DataFrame()
    rows = []
    for (sweep, method, k, cap), grp in per_user.groupby(
        ["sweep", "method", "k", "cap"], dropna=False
    ):
        rows.append(
            {
                "sweep": sweep,
                "method": method,
                "k": int(k),
                "cap": int(cap),
                "n_users": len(grp),
                "n_infeasible": int((~grp["feasible"].astype(bool)).sum()),
                "pct_infeasible": float(100.0 * (~grp["feasible"].astype(bool)).mean()),
                "n_failed_on_feasible": int(
                    ((grp["failed"].astype(float) > 0) & grp["feasible"].astype(bool)).sum()
                ),
                "n_exact_size_ok": int(grp["exact_size_ok"].astype(bool).sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["sweep", "k", "cap", "method"]).reset_index(drop=True)


def run_all_sweeps(
    ctx: EvalContext,
    cfg: Any,
    *,
    methods: list[str] | None = None,
    users: list[int] | None = None,
    run: Any | None = None,
    allow_non_research_encoder: bool = False,
) -> dict[str, pd.DataFrame]:
    sens = cfg.research.sensitivity
    out: dict[str, pd.DataFrame] = {}
    per_user_frames = []

    for name, points in (
        ("length_sweep", [p.model_dump() for p in sens.length_sweep]),
        ("cap_sweep", [p.model_dump() for p in sens.cap_sweep]),
    ):
        per_user, summary = run_sweep(
            ctx,
            points,
            sweep_name=name,
            methods=methods,
            users=users,
            run=run,
            allow_non_research_encoder=allow_non_research_encoder,
        )
        out[f"{name}_summary"] = summary
        per_user_frames.append(per_user)

    all_per_user = (
        pd.concat(per_user_frames, ignore_index=True) if per_user_frames else pd.DataFrame()
    )
    out["per_user"] = all_per_user
    out["infeasibility"] = infeasibility_report(all_per_user)
    return out
