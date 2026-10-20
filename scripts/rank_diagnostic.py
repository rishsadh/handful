#!/usr/bin/env python
"""Post-hoc rank diagnostic. NOT a protocol metric.

**Read this before using the output.**

This was written *after* seeing that Recall@6 came back as exactly 0.000 for three of the
four methods on the validation stage. It is therefore post-hoc by construction, and it is
deliberately kept out of the evaluation pipeline so that separation is structural rather
than a footnote: `tasks.py validate` and `tasks.py final` do not call it, and it cannot
change a single number in the Results Pack.

**It does not replace the primary metric.** Recall@6 remains primary and NDCG@6 secondary,
exactly as locked in `config/research.yaml`, and both are reported as computed. Swapping in
a friendlier metric after seeing an unfavourable result is precisely the practice the
protocol forbids.

**What it is for.** Recall@6 answers "did a hit land in six slots out of ~230,000?" and the
answer is almost always no, for every method. That makes it nearly non-discriminating on
this task, which is itself a finding worth stating. The rank of the user's best true
positive is a purely descriptive quantity that shows *where* each method places the target
even when nothing lands in the top six. It distinguishes a model that is weak from a model
that is inert, and those are different claims.

**What it still cannot support.** Nothing about choice overload, satisfaction, decision
speed or any human outcome. It is a ranking position, nothing more.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from foodcom import pipeline
from foodcom.models.scoring import score_candidates
from foodcom.utils import logging as flog
from foodcom.utils.config import load_configs

log = flog.get_logger(__name__)


def rank_of_best_positive(scores: np.ndarray, positive_idx: np.ndarray) -> int:
    """1-based rank of the highest-scoring true positive. Ties broken pessimistically."""
    order = np.argsort(-scores, kind="stable")
    rank = np.empty(len(scores), dtype=np.int64)
    rank[order] = np.arange(1, len(scores) + 1)
    return int(rank[positive_idx].min())


def run(stage: str = "validation", max_users: int | None = None) -> pd.DataFrame:
    cfg = load_configs()
    ctx, split = pipeline._prepare_context(cfg, stage)
    users = split.ranking_users[:max_users] if max_users else split.ranking_users
    log.info("rank diagnostic over %d users (%s stage)", len(users), stage)

    rows = []
    for n_done, u in enumerate(users, start=1):
        u = int(u)
        mask = ctx.candidate_mask(u)
        ids = ctx.catalogue_ids[mask]
        rel = split.label_positives.get(u, set())
        pos_idx = np.where(np.isin(ids, list(rel)))[0]
        if not len(pos_idx):
            continue
        ai = score_candidates(u, ids, ctx.profiles, ctx.store)
        pop = ctx.popularity[mask]
        rng = np.random.default_rng(cfg.research.protocol.random_seed + u)
        rows.append(
            {
                "user_id": u,
                "n_candidates": len(ids),
                "n_positives": len(pos_idx),
                "AI_score": rank_of_best_positive(ai, pos_idx),
                "POPULARITY": rank_of_best_positive(pop, pos_idx),
                "RANDOM": rank_of_best_positive(rng.random(len(ids)), pos_idx),
            }
        )
        if n_done % 100 == 0:
            log.info("  %d/%d", n_done, len(users))
    return pd.DataFrame(rows)


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    out = []
    n_cand = int(frame["n_candidates"].median())
    for method in ("AI_score", "POPULARITY", "RANDOM"):
        r = frame[method].to_numpy()
        out.append(
            {
                "scorer": method,
                "n_users": len(r),
                "median_rank_of_best_positive": int(np.median(r)),
                "p10_rank": int(np.percentile(r, 10)),
                "best_rank": int(r.min()),
                "pct_in_top_100": round(100.0 * (r <= 100).mean(), 2),
                "pct_in_top_1000": round(100.0 * (r <= 1000).mean(), 2),
                "pct_in_top_10000": round(100.0 * (r <= 10000).mean(), 2),
                "median_candidates": n_cand,
            }
        )
    return pd.DataFrame(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="validation", choices=["validation", "final"])
    parser.add_argument("--max-users", type=int, default=None)
    parser.add_argument("--out", default="reports/rank_diagnostic")
    args = parser.parse_args()

    flog.configure()
    frame = run(args.stage, args.max_users)
    if frame.empty:
        print("no users with eligible positives; nothing to report")
        return 1
    summary = summarise(frame)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / f"{args.stage}_per_user.csv", index=False)
    summary.to_csv(out / f"{args.stage}_summary.csv", index=False)
    (out / f"{args.stage}_meta.json").write_text(
        json.dumps(
            {
                "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
                "stage": args.stage,
                "status": "POST-HOC DESCRIPTIVE DIAGNOSTIC - not a protocol metric",
                "why_it_exists": (
                    "Recall@6 returned exactly 0.000 for three of four methods, so the "
                    "primary metric does not discriminate on this task. This shows where "
                    "each scorer places the target instead."
                ),
                "does_not_replace": "Recall@6 primary, NDCG@6 secondary, both unchanged.",
                "supports_no_claim_about": [
                    "choice overload", "satisfaction", "decision speed", "any human outcome",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nPOST-HOC diagnostic (does not replace Recall@6). Stage: {args.stage}\n")
    print(summary.to_string(index=False))
    print(f"\nwritten to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
