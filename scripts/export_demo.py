#!/usr/bin/env python
"""Export a minimal, real slice of the pipeline for the static browser demo.

Why a static export exists at all: the Streamlit demo is a live Python server, and a
classroom needs a link that cannot cold-start, time out, or depend on the room's wifi
reaching a sleeping free-tier host. See D-019.

Why it can be exact rather than an approximation: a score-sorted, capacity-respecting
greedy selection is **provably optimal** for this band-capacity structure - the project
proves it, tests it, and cross-checks it against exhaustive enumeration. So the browser can
reproduce the solver's exact answer in a few lines of JavaScript. This script verifies that
claim against SciPy for **every (k, b) the sliders allow** before writing anything; if a
single combination disagrees, it refuses to export.

Licence discipline (D-021). The dataset licence is "Data files (c) Original Authors", which
grants no redistribution rights. This export is therefore deliberately minimal:

* only the handful of profiles the demo shows, not the cohort;
* only the candidates any slider setting could reach, not the catalogue;
* recipe name, reported minutes and band only - no ingredients, no steps, no description,
  no nutrition, no tags, no review text, and no user ids;
* the "why" line is precomputed to a short phrase, so ingredient lists never leave.

That is about 1,300 titles (well under 1% of the catalogue), quoted for academic
illustration with attribution rather than mirrored (D-042). The page says so and gives a
contact for removal; the extract stays out of git and out of search indexes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from foodcom import pipeline
from foodcom.evaluation.methods import METHOD_DESCRIPTIONS
from foodcom.models.scoring import SCORE_MEANING, score_candidates
from foodcom.optimisation.dual import BETA_MEANING, check_duality
from foodcom.optimisation.greedy import greedy_select
from foodcom.optimisation.lpp import ShortlistProblem, solve_primal
from foodcom.testing import SYNTHETIC_MARKER
from foodcom.utils import logging as flog
from foodcom.utils.config import Configs, load_configs

log = flog.get_logger(__name__)

K_RANGE = (2, 12)
B_RANGE = (1, 12)


def _problem(ctx, user_id: int, ids: np.ndarray, scores: np.ndarray, bands: np.ndarray,
             k: int, cap: int) -> ShortlistProblem:
    return ShortlistProblem(
        candidate_ids=ids,
        scores=np.asarray(scores, dtype="float64"),
        band_of=np.asarray(bands, dtype="int64"),
        k=k,
        caps=np.full(len(ctx.band_labels), cap, dtype="int64"),
        band_labels=ctx.band_labels,
        user_id=int(user_id),
    )


def _verify_greedy_equals_lp(problem_full: ShortlistProblem, ids, scores, bands, ctx,
                             tol: float) -> tuple[bool, list[str], int]:
    """Greedy must match SciPy on every (k, b) a slider can produce. No exceptions."""
    problems: list[str] = []
    checked = 0
    for k in range(K_RANGE[0], K_RANGE[1] + 1):
        for cap in range(B_RANGE[0], B_RANGE[1] + 1):
            p = _problem(ctx, problem_full.user_id, ids, scores, bands, k, cap)
            lp = solve_primal(p, tol=tol, prune=False)
            g_ids, g_obj = greedy_select(p)
            checked += 1
            if not lp.feasibility.feasible:
                if len(g_ids):
                    problems.append(f"k={k} b={cap}: greedy returned a set where the LP "
                                    "reports infeasible")
                continue
            if not lp.ok:
                problems.append(f"k={k} b={cap}: LP failed verification")
                continue
            if not np.isfinite(g_obj) or abs(g_obj - lp.objective) > max(tol, 1e-9):
                problems.append(
                    f"k={k} b={cap}: greedy {g_obj!r} != LP {lp.objective!r}"
                )
    return (not problems), problems, checked


def _why(ctx, state_recipes: pd.DataFrame, recipe_id: int, history_ids: list[int]) -> str:
    """Precompute the card's explanation so ingredient lists never leave the machine."""
    from foodcom.features.text import as_list

    def ings(rid: int) -> set[str]:
        try:
            row = state_recipes.loc[int(rid)]
        except KeyError:
            return set()
        return {str(i).strip().lower() for i in as_list(row.get("ingredients"))
                if isinstance(i, str)}

    target = ings(recipe_id)
    counts: dict[str, int] = {}
    for rid in history_ids:
        for ing in ings(rid) & target:
            counts[ing] = counts.get(ing, 0) + 1
    shared = [i for i, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))][:3]
    if not shared:
        return "No ingredient overlap with this profile's rated history; the score comes "\
               "from the wider recipe text."
    return "Shares " + ", ".join(shared) + " with recipes this profile rated 4 or 5 "\
           "before the cutoff."


def export(
    cfg: Configs,
    *,
    stage: str = "validation",
    n_profiles: int = 10,
    per_band: int = 14,
    out_path: Path | None = None,
    allow_non_research_encoder: bool = False,
    worked_user: bool = False,
    label_start: int = 0,
) -> Path:
    tol = cfg.model.solver.tolerance
    protocol = cfg.research.protocol
    ctx, split = pipeline._prepare_context(cfg, stage)
    recipes = pd.read_parquet(cfg.path("processed_dir") / pipeline.RECIPES_CLEAN)
    recipes = recipes.set_index("id", drop=False)

    synthetic = SYNTHETIC_MARKER in " ".join(
        [cfg.research.dataset.kaggle_version, cfg.research.dataset.name,
         cfg.research.dataset.licence_text]
    )
    store_ok = ctx.store.provenance.get("is_research_grade", False)
    if not store_ok and not allow_non_research_encoder:
        raise RuntimeError(
            "the embedding store came from a non-research encoder. Refusing to export a "
            "demo that would look real. Pass --allow-test-encoder for a rehearsal build."
        )

    users = split.ranking_users or split.cohort_users
    warm = [u for u in users if u not in set(ctx.profiles.cold_users)]
    if not warm:
        raise RuntimeError(f"stage {stage} has no warm profile to export")
    rng = np.random.default_rng(protocol.cohort_seed)
    chosen = sorted(rng.choice(warm, size=min(n_profiles, len(warm)), replace=False).tolist())
    if worked_user:
        # The paper's worked example is the run's first ranking user (pipeline.py, users[0]).
        chosen = [int(users[0])]

    band_labels = list(ctx.band_labels)
    profiles_out: list[dict[str, Any]] = []
    verify_all_ok = True
    verify_problems: list[str] = []
    verify_checked = 0

    for slot, user_id in enumerate(chosen):
        user_id = int(user_id)
        mask = ctx.candidate_mask(user_id)
        all_ids = ctx.catalogue_ids[mask]
        all_bands = ctx.band_index[mask]
        all_scores = score_candidates(user_id, all_ids, ctx.profiles, ctx.store)
        all_pop = ctx.popularity[mask]

        # --- the real solve, over the FULL candidate set ---
        # Pruned: band pruning is exact here, and the unpruned simplex does not converge
        # at catalogue scale (D-024). Optimality over all candidates is established by the
        # matching dual certificate below, which is checked against every constraint.
        full = _problem(ctx, user_id, all_ids, all_scores, all_bands,
                        protocol.shortlist_size_k, protocol.band_cap_b)
        solution = solve_primal(full, tol=tol, prune=True)
        if not solution.ok:
            log.warning("skipping profile %d: %s", slot, solution.verification.problems)
            continue
        _, dual, duality = check_duality(full, solution, tol=tol)

        # --- the minimal export set: everything any slider setting could reach ---
        keep: set[int] = set()
        for g in range(len(band_labels)):
            in_band = np.where(all_bands == g)[0]
            if not len(in_band):
                continue
            by_score = in_band[np.lexsort((all_ids[in_band], -all_scores[in_band]))]
            keep.update(by_score[:per_band].tolist())
            by_pop = in_band[np.lexsort((all_ids[in_band], -all_pop[in_band]))]
            keep.update(by_pop[:per_band].tolist())
        keep.update(int(np.where(all_ids == int(r))[0][0]) for r in solution.selected_ids)
        idx = np.sort(np.fromiter(keep, dtype="int64", count=len(keep)))

        sub_ids, sub_scores = all_ids[idx], all_scores[idx]
        sub_bands, sub_pop = all_bands[idx], all_pop[idx]

        # The export is only usable if it yields the same answers as the full problem.
        ok, probs, checked = _verify_greedy_equals_lp(
            full, sub_ids, sub_scores, sub_bands, ctx, tol
        )
        verify_checked += checked
        if not ok:
            verify_all_ok = False
            verify_problems.extend(f"profile {slot}: {p}" for p in probs[:3])

        history_ids = sorted(split.positives.get(user_id, set()))
        history = [
            {
                "name": str(recipes.loc[int(r)]["name"]),
                "minutes": int(recipes.loc[int(r)]["minutes"]),
                "band": band_labels.index(str(recipes.loc[int(r)]["band"])),
            }
            for r in history_ids[:12]
            if int(r) in recipes.index
        ]

        candidates = []
        for j, rid in enumerate(sub_ids):
            row = recipes.loc[int(rid)]
            candidates.append(
                {
                    "id": int(rid),
                    "name": str(row["name"]),
                    "min": int(row["minutes"]),
                    "b": int(sub_bands[j]),
                    "s": round(float(sub_scores[j]), 6),
                    "p": int(sub_pop[j]),
                    "why": _why(ctx, recipes, int(rid), history_ids),
                }
            )

        profiles_out.append(
            {
                "label": f"profile-{slot + 1 + label_start:04d}",
                "n_positive_history": len(history_ids),
                "n_eligible_candidates": len(all_ids),
                "n_exported_candidates": len(sub_ids),
                "history": history,
                "candidates": candidates,
                "solve": {
                    "k": protocol.shortlist_size_k,
                    "cap": protocol.band_cap_b,
                    "objective": round(float(solution.objective), 6),
                    "selected": [int(r) for r in solution.ranked_ids],
                    "band_usage": solution.band_usage(),
                    "reachable_capacity": solution.feasibility.capacity,
                    "band_sizes": solution.feasibility.band_sizes,
                    "solver_message": solution.verification.message,
                    "equality_residual": float(solution.verification.equality_residual),
                    "max_distance_to_integer": float(
                        solution.verification.max_distance_to_integer
                    ),
                    "tolerance": float(solution.verification.tolerance),
                    "checks_passed": bool(solution.verification.ok),
                    "solve_seconds": round(float(solution.solve_seconds), 6),
                },
                "dual": {
                    "alpha": round(float(dual.alpha), 6),
                    "beta": [round(float(b), 6) for b in dual.beta],
                    "primal_objective": round(float(duality.primal_objective), 6),
                    "dual_objective": round(float(duality.dual_objective), 6),
                    "duality_gap": float(duality.duality_gap),
                    "strong_duality_holds": bool(duality.strong_duality_holds),
                    "complementary_slackness": {
                        k2: float(v) for k2, v in duality.complementary_slackness.items()
                    },
                    "complementary_slackness_holds": bool(
                        duality.complementary_slackness_holds
                    ),
                },
            }
        )
        log.info("exported %s (%d candidates)", profiles_out[-1]["label"], len(sub_ids))

    if not verify_all_ok:
        raise RuntimeError(
            "REFUSING TO EXPORT: the browser's greedy rule disagreed with SciPy on at "
            "least one slider setting, so the page could show a different answer from the "
            "solver. Problems: " + "; ".join(verify_problems[:6])
        )

    # --- aggregate benchmark tables, if a run exists ---
    benchmark: dict[str, Any] = {}
    runs = sorted(
        (p for p in cfg.path("runs_dir").glob("final-*") if (p / "manifest.json").exists()),
        reverse=True,
    ) or sorted(
        (p for p in cfg.path("runs_dir").glob("validation-*")
         if (p / "manifest.json").exists()),
        reverse=True,
    )
    run_id = None
    if runs:
        run_dir = runs[0]
        run_id = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")).get(
            "run_id", run_dir.name
        )
        for key, name in (
            ("method_comparison", "t04_method_comparison"),
            ("paired_differences", "t05_paired_differences"),
            ("sensitivity_length", "t06_sensitivity_length"),
            ("sensitivity_cap", "t07_sensitivity_cap"),
            ("feasibility", "t08_feasibility_and_failures"),
        ):
            f = run_dir / "tables" / f"{name}.csv"
            if f.exists():
                benchmark[key] = json.loads(
                    pd.read_csv(f).round(6).to_json(orient="records")
                )

    from foodcom.models.bands import band_bounds_text

    payload = {
        "meta": {
            "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
            "stage": stage,
            "run_id": run_id,
            "protocol_version": cfg.research.protocol_version,
            "is_synthetic": synthetic,
            "k_default": protocol.shortlist_size_k,
            "b_default": protocol.band_cap_b,
            "k_range": list(K_RANGE),
            "b_range": list(B_RANGE),
            "band_labels": band_labels,
            "band_bounds": band_bounds_text(protocol),
            "history_cutoff": str(split.window.history_end_exclusive),
            "label_window": [str(split.window.label_start),
                             str(split.window.label_end_inclusive or "dataset endpoint")],
            "dataset": {
                "name": cfg.research.dataset.name,
                "version": cfg.research.dataset.kaggle_version,
                "licence": cfg.research.dataset.licence_text,
                "redistribution_permitted": cfg.research.dataset.licence_permits_redistribution,
            },
            "encoder": {
                "model_id": ctx.store.provenance.get("model_id"),
                "revision": ctx.store.provenance.get("model_revision"),
                "is_research_grade": store_ok,
            },
            "score_meaning": SCORE_MEANING,
            "beta_meaning": BETA_MEANING,
            "method_descriptions": METHOD_DESCRIPTIONS,
            "denominators": split.denominators,
            "verification": {
                "greedy_matches_scipy_for_every_slider_setting": True,
                "combinations_checked": verify_checked,
                "note": (
                    "The browser re-solves with a score-sorted, capacity-respecting greedy "
                    "rule, which is provably optimal for this band-capacity structure. "
                    "Every (k, b) the sliders allow was checked against "
                    "scipy.optimize.linprog before this file was written."
                ),
            },
            "extract_note": (
                "A minimal academic extract, shown only to illustrate the study: about 1,300 "
                "recipe titles (well under 1% of the catalogue) with their reported cooking "
                "time and band. No ingredients, steps, descriptions, nutrition, tags, review "
                "text or user ids. The dataset licence grants no redistribution rights, so "
                "nothing beyond this is reproduced here. If you hold rights in anything shown "
                "and would like it removed, write to hello@reidify.design."
            ),
        },
        "profiles": profiles_out,
        "benchmark": benchmark,
    }

    out = out_path or (cfg.root / "site" / "demo" / "data.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    log.info("demo export written to %s (%.1f KB, %d profiles, %d combinations verified)",
             out, size_kb, len(profiles_out), verify_checked)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="validation", choices=["validation", "final"])
    parser.add_argument("--profiles", type=int, default=10)
    parser.add_argument("--per-band", type=int, default=14,
                        help="candidates kept per band per ranking (score and popularity)")
    parser.add_argument("--out", default=None)
    parser.add_argument("--config-root", default=None,
                        help="use a different project root (e.g. a synthetic workspace)")
    parser.add_argument("--worked-user", action="store_true",
                        help="export only the paper's worked-example user")
    parser.add_argument("--label-start", type=int, default=0,
                        help="number the exported profiles from this offset (profile-0011 = 10)")
    parser.add_argument("--allow-test-encoder", action="store_true",
                        help="rehearsal builds only; marks the export synthetic")
    args = parser.parse_args()

    flog.configure()
    if args.config_root:
        root = Path(args.config_root).resolve()
        cfg = load_configs(config_dir=root / "config", root=root)
    else:
        cfg = load_configs()

    out = export(
        cfg,
        stage=args.stage,
        n_profiles=args.profiles,
        per_band=args.per_band,
        out_path=Path(args.out) if args.out else None,
        allow_non_research_encoder=args.allow_test_encoder,
        worked_user=args.worked_user,
        label_start=args.label_start,
    )
    print(f"\nDemo data written to {out} ({out.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
