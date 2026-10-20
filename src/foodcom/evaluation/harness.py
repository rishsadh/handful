"""The evaluation harness.

Runs every configured method over the ranking-eligible cohort of one stage, against the
full frozen candidate catalogue. Nothing is scored against a small sampled set of
negatives: sampled-negative evaluation systematically distorts the ranking of recommenders,
so the denominator here is the whole eligible catalogue even though it costs more compute.

Scoring is done in user chunks. A single matrix multiply of the whole catalogue against
5,000 profiles would need several gigabytes; chunking keeps it to a couple of hundred
megabytes without changing a single number.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from foodcom.data.splits import StageSplit
from foodcom.evaluation.methods import (
    MethodOutput,
    run_ai_topk,
    run_lp_method,
    run_random,
)
from foodcom.evaluation.metrics import (
    UserResult,
    band_usage,
    bands_represented,
    cap_violations,
    ndcg_at_k,
    recall_at_k,
    reduction_ratio,
)
from foodcom.features.embed import EmbeddingStore
from foodcom.features.profiles import ProfileStore
from foodcom.optimisation.lpp import DEFAULT_TOL, ShortlistProblem
from foodcom.utils import logging as flog
from foodcom.utils.config import Configs

log = flog.get_logger(__name__)


@dataclass
class EvalContext:
    """Everything the harness needs, assembled once per stage."""

    cfg: Configs
    split: StageSplit
    store: EmbeddingStore
    profiles: ProfileStore
    popularity: np.ndarray  # aligned to catalogue order
    catalogue_ids: np.ndarray
    band_index: np.ndarray  # aligned to catalogue order
    band_labels: tuple[str, ...]
    tfidf_store: EmbeddingStore | None = None
    tfidf_profiles: ProfileStore | None = None

    def __post_init__(self) -> None:
        self._cat_pos = {int(r): i for i, r in enumerate(self.catalogue_ids)}
        self.band_of_id = {
            int(r): self.band_labels[int(self.band_index[i])]
            for i, r in enumerate(self.catalogue_ids)
        }

    def candidate_mask(self, user_id: int) -> np.ndarray:
        """Boolean mask over the catalogue: eligible and not already seen."""
        mask = np.ones(len(self.catalogue_ids), dtype=bool)
        for rid in self.split.seen.get(int(user_id), ()):
            pos = self._cat_pos.get(int(rid))
            if pos is not None:
                mask[pos] = False
        return mask


def build_context(
    cfg: Configs,
    split: StageSplit,
    store: EmbeddingStore,
    profiles: ProfileStore,
    popularity: pd.Series,
) -> EvalContext:
    from foodcom.models.bands import assign_bands

    catalogue_ids = split.catalogue["id"].to_numpy(dtype="int64")
    labels = tuple(cfg.research.protocol.band_labels)
    bands = assign_bands(split.catalogue["minutes"], cfg.research.protocol)
    band_index = np.asarray([labels.index(b) for b in bands], dtype="int64")
    pop = popularity.reindex(catalogue_ids, fill_value=0).to_numpy(dtype="float64")

    # The store must cover the catalogue in the catalogue's own order.
    ordered = store.subset(catalogue_ids)
    return EvalContext(
        cfg=cfg,
        split=split,
        store=ordered,
        profiles=profiles,
        popularity=pop,
        catalogue_ids=catalogue_ids,
        band_index=band_index,
        band_labels=labels,
    )


def _result_from_output(
    *,
    user_id: int,
    method: str,
    stage: str,
    k: int,
    cap: int,
    out: MethodOutput,
    n_candidates: int,
    relevant: set[int],
    ctx: EvalContext,
    scoring_seconds: float,
    total_seconds: float,
) -> UserResult:
    ranked = [int(i) for i in out.ranked_ids]
    caps_map = dict.fromkeys(ctx.band_labels, cap)
    usage = band_usage(ranked, ctx.band_of_id, ctx.band_labels)

    if relevant and out.feasible:
        # A method that failed on a feasible input scores zero rather than disappearing:
        # dropping difficult users would flatter whichever method fails most.
        rec = recall_at_k(ranked, relevant, k) if ranked else 0.0
        nd = ndcg_at_k(ranked, relevant, k) if ranked else 0.0
    else:
        rec = float("nan")
        nd = float("nan")

    return UserResult(
        user_id=int(user_id),
        method=method,
        stage=stage,
        k=k,
        cap=cap,
        ranked_ids=ranked,
        n_candidates=int(n_candidates),
        n_relevant=len(relevant),
        recall=rec,
        ndcg=nd,
        bands_represented=bands_represented(ranked, ctx.band_of_id),
        band_usage=usage,
        cap_violations=cap_violations(usage, caps_map),
        exact_size_ok=len(ranked) == k,
        feasible=bool(out.feasible),
        solver_status=out.solver_status,
        failed=bool(out.failed),
        failure_reason=out.failure_reason,
        reduction_ratio=reduction_ratio(k, int(n_candidates)),
        scoring_seconds=scoring_seconds,
        solve_seconds=out.solve_seconds,
        total_seconds=total_seconds,
    )


def evaluate_user(
    user_id: int,
    ai_scores: np.ndarray,
    mask: np.ndarray,
    ctx: EvalContext,
    *,
    k: int,
    cap: int,
    methods: list[str],
    scoring_seconds: float,
    tol: float = DEFAULT_TOL,
    random_repeats: int = 20,
    random_seed: int = 42,
) -> list[dict[str, Any]]:
    """Run every requested method for one user. `ai_scores` is already masked-aligned."""
    stage = ctx.split.stage
    candidate_ids = ctx.catalogue_ids[mask]
    bands = ctx.band_index[mask]
    relevant = ctx.split.label_positives.get(int(user_id), set())
    caps = np.full(len(ctx.band_labels), int(cap), dtype="int64")

    rows: list[dict[str, Any]] = []

    def problem_with(scores: np.ndarray) -> ShortlistProblem:
        return ShortlistProblem(
            candidate_ids=candidate_ids,
            scores=np.asarray(scores, dtype="float64"),
            band_of=bands,
            k=k,
            caps=caps,
            band_labels=ctx.band_labels,
            user_id=int(user_id),
        )

    ai_problem = problem_with(ai_scores)

    for method in methods:
        t0 = time.perf_counter()
        if method == "AI_LP":
            out = run_lp_method(ai_problem, tol=tol)
            rows.append(
                _result_from_output(
                    user_id=user_id, method=method, stage=stage, k=k, cap=cap, out=out,
                    n_candidates=len(candidate_ids), relevant=relevant, ctx=ctx,
                    scoring_seconds=scoring_seconds,
                    total_seconds=scoring_seconds + (time.perf_counter() - t0),
                ).as_row()
            )
        elif method == "AI_TOPK":
            out = run_ai_topk(ai_problem)
            rows.append(
                _result_from_output(
                    user_id=user_id, method=method, stage=stage, k=k, cap=cap, out=out,
                    n_candidates=len(candidate_ids), relevant=relevant, ctx=ctx,
                    scoring_seconds=scoring_seconds,
                    total_seconds=scoring_seconds + (time.perf_counter() - t0),
                ).as_row()
            )
        elif method == "POPULARITY_LP":
            pop_problem = problem_with(ctx.popularity[mask])
            out = run_lp_method(pop_problem, tol=tol)
            rows.append(
                _result_from_output(
                    user_id=user_id, method=method, stage=stage, k=k, cap=cap, out=out,
                    n_candidates=len(candidate_ids), relevant=relevant, ctx=ctx,
                    scoring_seconds=0.0,
                    total_seconds=time.perf_counter() - t0,
                ).as_row()
            )
        elif method == "RANDOM":
            for repeat in range(random_repeats):
                t1 = time.perf_counter()
                # Seed derived from (base seed, user, repeat) so the whole sweep is
                # reproducible and no two users share a permutation.
                seed = np.random.SeedSequence(
                    [random_seed, int(user_id), repeat]
                ).generate_state(1)[0]
                out = run_random(ai_problem, seed=int(seed))
                row = _result_from_output(
                    user_id=user_id, method=method, stage=stage, k=k, cap=cap, out=out,
                    n_candidates=len(candidate_ids), relevant=relevant, ctx=ctx,
                    scoring_seconds=0.0,
                    total_seconds=time.perf_counter() - t1,
                ).as_row()
                row["repeat"] = repeat
                rows.append(row)
        elif method == "TFIDF_LP":
            if ctx.tfidf_store is None or ctx.tfidf_profiles is None:
                continue
            from foodcom.models.scoring import score_candidates

            tf_scores = score_candidates(
                int(user_id), candidate_ids, ctx.tfidf_profiles, ctx.tfidf_store
            )
            out = run_lp_method(problem_with(tf_scores), tol=tol)
            rows.append(
                _result_from_output(
                    user_id=user_id, method=method, stage=stage, k=k, cap=cap, out=out,
                    n_candidates=len(candidate_ids), relevant=relevant, ctx=ctx,
                    scoring_seconds=0.0,
                    total_seconds=time.perf_counter() - t0,
                ).as_row()
            )
        else:
            raise ValueError(f"unknown method {method!r}")

    return rows


def evaluate_stage(
    ctx: EvalContext,
    *,
    k: int | None = None,
    cap: int | None = None,
    methods: list[str] | None = None,
    users: list[int] | None = None,
    chunk_size: int = 256,
    run: Any | None = None,
    allow_non_research_encoder: bool = False,
) -> pd.DataFrame:
    """Evaluate one stage and return the per-user, per-method result table."""
    protocol = ctx.cfg.research.protocol
    k = k or protocol.shortlist_size_k
    cap = cap or protocol.band_cap_b
    methods = methods or list(protocol.methods)
    target = users if users is not None else ctx.split.ranking_users
    tol = ctx.cfg.model.solver.tolerance

    if not allow_non_research_encoder and not ctx.store.provenance.get("is_research_grade", False):
        raise RuntimeError(
            "the embedding store was produced by a non-research encoder "
            f"({ctx.store.provenance.get('model_id')!r}). Refusing to produce research "
            "numbers from it. Pass allow_non_research_encoder=True only inside tests."
        )

    warm = [u for u in target if ctx.profiles.has(int(u)) and int(u) not in
            set(ctx.profiles.cold_users)]
    n_cold_skipped = len(target) - len(warm)
    if n_cold_skipped:
        log.warning("skipping %d cold users: they have no AI profile", n_cold_skipped)
        if run is not None:
            run.record_failure(
                "cold_users_skipped",
                f"{n_cold_skipped} users in the target population had no usable profile",
            )

    all_rows: list[dict[str, Any]] = []
    n_chunks = max(1, (len(warm) + chunk_size - 1) // chunk_size)
    for c in range(n_chunks):
        chunk = warm[c * chunk_size : (c + 1) * chunk_size]
        if not chunk:
            continue
        t0 = time.perf_counter()
        profile_matrix = np.vstack([ctx.profiles.vector(int(u)) for u in chunk])
        # (n_catalogue, chunk) - one BLAS call per chunk instead of one per user.
        score_matrix = (ctx.store.vectors @ profile_matrix.T + 1.0) / 2.0
        np.clip(score_matrix, 0.0, 1.0, out=score_matrix)
        chunk_scoring_seconds = time.perf_counter() - t0
        per_user_scoring = chunk_scoring_seconds / len(chunk)

        for j, user_id in enumerate(chunk):
            mask = ctx.candidate_mask(int(user_id))
            all_rows.extend(
                evaluate_user(
                    int(user_id),
                    score_matrix[mask, j].astype("float64"),
                    mask,
                    ctx,
                    k=k,
                    cap=cap,
                    methods=methods,
                    scoring_seconds=per_user_scoring,
                    tol=tol,
                    random_repeats=protocol.random_repeats,
                    random_seed=protocol.random_seed,
                )
            )
        log.info("stage %s: chunk %d/%d done (%d users)", ctx.split.stage, c + 1, n_chunks,
                 len(chunk))

    frame = pd.DataFrame(all_rows)
    if run is not None:
        run.note(
            f"evaluation_{ctx.split.stage}_k{k}_b{cap}",
            {
                "n_target_users": len(target),
                "n_warm_users_evaluated": len(warm),
                "n_cold_users_skipped": n_cold_skipped,
                "methods": methods,
                "k": k,
                "cap": cap,
                "catalogue_size": len(ctx.catalogue_ids),
            },
        )
    return frame


def feasibility_coverage(ctx: EvalContext, k: int, cap: int, users: list[int]) -> pd.DataFrame:
    """Structural feasibility over a broader cohort, without running any method.

    Reported separately from the ranking metrics: a structurally infeasible profile is not
    a failed recommendation, it is a user for whom no k-item shortlist satisfying the caps
    exists at all.
    """
    from foodcom.optimisation.lpp import check_feasibility

    caps = np.full(len(ctx.band_labels), int(cap), dtype="int64")
    rows = []
    for user_id in users:
        mask = ctx.candidate_mask(int(user_id))
        problem = ShortlistProblem(
            candidate_ids=ctx.catalogue_ids[mask],
            scores=np.zeros(int(mask.sum())),
            band_of=ctx.band_index[mask],
            k=k,
            caps=caps,
            band_labels=ctx.band_labels,
            user_id=int(user_id),
        )
        report = check_feasibility(problem)
        rows.append(
            {
                "user_id": int(user_id),
                "stage": ctx.split.stage,
                "k": k,
                "cap": cap,
                "n_candidates": int(mask.sum()),
                "feasible": report.feasible,
                "reachable_capacity": report.capacity,
                **{f"band_size_{lab}": n for lab, n in zip(ctx.band_labels, report.band_sizes,
                                                           strict=True)},
            }
        )
    return pd.DataFrame(rows)
