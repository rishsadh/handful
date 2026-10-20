"""Pipeline stages.

Each function is one step of the documented order of work:

    source and licence -> immutable raw files -> audit -> data/split freeze ->
    baselines -> AI and LPP -> validation -> protocol freeze -> one final test ->
    demo and research handoff

The scripts in `scripts/` are thin command-line wrappers around these.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from foodcom.data import acquire, schema, splits
from foodcom.data import audit as audit_mod
from foodcom.data import clean as clean_mod
from foodcom.evaluation import harness, sensitivity, stats
from foodcom.evaluation.metrics import aggregate_per_method, average_random_repeats
from foodcom.features import embed
from foodcom.features import profiles as profiles_mod
from foodcom.features import text as text_mod
from foodcom.features.encoders import build_encoder
from foodcom.optimisation import dual as dual_mod
from foodcom.optimisation import graphical, integrality
from foodcom.reporting import figures as fig_mod
from foodcom.reporting import tables as tbl_mod
from foodcom.utils import logging as flog
from foodcom.utils.config import Configs, load_configs
from foodcom.utils.io import read_parquet, write_csv, write_parquet
from foodcom.utils.runctx import RunContext, Timer

log = flog.get_logger(__name__)

RECIPES_CLEAN = "recipes_clean.parquet"
INTERACTIONS_CLEAN = "interactions_clean.parquet"
RENDERED_TEXT = "rendered_text.parquet"
LEDGER = "exclusion_ledger.csv"


# --------------------------------------------------------------------------- gate 1


def run_acquire(cfg: Configs | None = None) -> dict[str, Any]:
    """Record provenance and hash the raw files. Fails loudly if the gate is not passed."""
    cfg = cfg or load_configs()
    status = acquire.gate_status(cfg)
    if not status["passed"]:
        log.error("DATA GATE NOT PASSED")
        print(json.dumps(status, indent=2))
        print(acquire.DOWNLOAD_INSTRUCTIONS)
        reasons = []
        if status["missing_files"]:
            reasons.append("missing raw files: " + ", ".join(status["missing_files"]))
        if status["missing_provenance_fields"]:
            reasons.append(
                "provenance still UNRECORDED for: "
                + ", ".join(status["missing_provenance_fields"])
            )
        raise acquire.AcquisitionError(
            "data gate not passed (" + "; ".join(reasons) + "). "
            "See the instructions above. Nothing was fabricated."
        )
    path = acquire.write_source_manifest(cfg)

    # A schema probe on the first rows, so a wrong file is caught before a full read.
    raw_dir = cfg.path("raw_dir")
    probe = {}
    for filename, expected, reader in (
        ("RAW_recipes.csv", schema.RECIPE_COLUMNS, schema.read_raw_recipes),
        ("RAW_interactions.csv", schema.INTERACTION_COLUMNS, schema.read_raw_interactions),
    ):
        head = reader(str(raw_dir / filename), nrows=200)
        probe[filename] = schema.validate_schema(head, expected, filename).as_dict()
        if probe[filename]["missing_columns"]:
            raise acquire.AcquisitionError(
                f"{filename} is missing expected columns "
                f"{probe[filename]['missing_columns']}. This is not the expected release."
            )
    (cfg.path("processed_dir") / "schema_probe.json").write_text(
        json.dumps(probe, indent=2), encoding="utf-8"
    )
    log.info("data gate passed; manifest at %s", path)
    return {"source_manifest": str(path), "schema_probe": probe, "gate": status}


def run_audit(cfg: Configs | None = None) -> str:
    """Full audit of the raw files. Writes JSON, CSV tables and docs/DATA_AUDIT.md."""
    cfg = cfg or load_configs()
    raw_dir = cfg.path("raw_dir")
    missing = acquire.missing_files(cfg)
    if missing:
        raise acquire.AcquisitionError(
            f"cannot audit: missing {missing}\n\n{acquire.DOWNLOAD_INSTRUCTIONS}"
        )

    with RunContext.open(
        cfg,
        stage="audit",
        data_files=[raw_dir / f for f in cfg.research.dataset.required_files],
    ) as run:
        with Timer(run, "read_raw"):
            recipes = schema.read_raw_recipes(str(raw_dir / "RAW_recipes.csv"))
            interactions = schema.read_raw_interactions(str(raw_dir / "RAW_interactions.csv"))
        with Timer(run, "audit"):
            result = audit_mod.run_audit(recipes, interactions, cfg)

        run.write_json("metrics/audit_summary.json", result["summary"])
        out_dir = cfg.path("reports_dir") / "audit"
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in result["tables"].items():
            write_csv(frame, out_dir / f"{name}.csv")
            run.write_table(f"tables/{name}.csv", frame)

        verdict = audit_mod.coverage_verdict(result["summary"], cfg)
        run.write_json("metrics/coverage_verdict.json", verdict)
        if not verdict["workable"]:
            run.record_failure(
                "temporal_coverage",
                "the locked windows are not workable against this download: "
                + "; ".join(verdict["problems"]),
            )

        run.write_table(
            "tables/t01_raw_dataset_audit.csv", tbl_mod.audit_summary_table(result["summary"])
        )
        _write_audit_markdown(cfg, result, verdict, run.run_id)
        return run.run_id


def _write_audit_markdown(
    cfg: Configs, result: dict[str, Any], verdict: dict[str, Any], run_id: str
) -> Path:
    summary = result["summary"]
    out = cfg.path("docs_dir") / "DATA_AUDIT.md"
    parts = [
        f"# Data audit\n\nRun `{run_id}` · protocol {summary['protocol_version']} · "
        f"audited {summary['audited_utc']}\n",
        "This audit reports what the downloaded bytes actually contain. It modifies "
        "nothing. Every cleaning decision made afterwards is justified against the "
        "evidence here.\n",
        "## Headline counts\n",
        tbl_mod.to_markdown(tbl_mod.audit_summary_table(summary), max_rows=40),
        "\n## Temporal coverage of the locked windows\n",
        f"Workable: **{verdict['workable']}**\n",
    ]
    if verdict["problems"]:
        parts.append("Problems found:\n")
        parts.extend(f"- {p}\n" for p in verdict["problems"])
        parts.append(f"\n{verdict['action_if_unworkable']}\n")
    parts.append(
        tbl_mod.to_markdown(
            pd.DataFrame(
                [{"stage": s, **w} for s, w in verdict["windows"].items()]
            )
        )
    )
    for name, frame in result["tables"].items():
        parts.append(f"\n## {name.replace('__', ' — ').replace('_', ' ')}\n")
        parts.append(tbl_mod.to_markdown(frame, max_rows=30))
    parts.append(
        "\n## What this audit does not establish\n\n"
        "It does not establish that the dataset is fit for any particular claim, that "
        "nutrition units are what they appear to be, or that the licence permits "
        "redistribution. Those are recorded separately and remain open until confirmed.\n"
    )
    out.write_text("\n".join(parts), encoding="utf-8")
    log.info("audit markdown written to %s", out)
    return out


# --------------------------------------------------------------------------- cleaning


def run_clean(cfg: Configs | None = None) -> str:
    cfg = cfg or load_configs()
    raw_dir = cfg.path("raw_dir")
    missing = acquire.missing_files(cfg)
    if missing:
        raise acquire.AcquisitionError(f"cannot clean: missing {missing}")

    with RunContext.open(
        cfg,
        stage="clean",
        data_files=[raw_dir / f for f in cfg.research.dataset.required_files],
    ) as run:
        with Timer(run, "read_raw"):
            recipes_raw = schema.read_raw_recipes(str(raw_dir / "RAW_recipes.csv"))
            interactions_raw = schema.read_raw_interactions(
                str(raw_dir / "RAW_interactions.csv")
            )

        with Timer(run, "clean_recipes"):
            rec = clean_mod.clean_recipes(recipes_raw, cfg)
        with Timer(run, "clean_interactions"):
            inter = clean_mod.clean_interactions(interactions_raw, rec.frame, cfg)

        processed = cfg.path("processed_dir")
        write_parquet(rec.frame, processed / RECIPES_CLEAN)
        write_parquet(
            inter.frame.drop(columns=["recipe_submitted"], errors="ignore"),
            processed / INTERACTIONS_CLEAN,
        )

        quarantine_dir = cfg.path("quarantine_dir")
        rec.write_quarantine(quarantine_dir)
        inter.write_quarantine(quarantine_dir)
        review = inter.quarantine.get("_review_text_private")
        if review is not None and not review.empty:
            write_parquet(review, cfg.path("interim_dir") / "review_text.parquet")

        ledger = clean_mod.combined_ledger(rec, inter)
        write_csv(ledger, processed / LEDGER)
        run.write_table("tables/t02_cleaning_exclusion_ledger.csv", ledger)
        run.write_json("metrics/cleaning_notes.json", {"recipes": rec.notes,
                                                       "interactions": inter.notes})
        run.note("n_recipes_clean", len(rec.frame))
        run.note("n_interactions_clean", len(inter.frame))
        return run.run_id


def load_clean(cfg: Configs) -> tuple[pd.DataFrame, pd.DataFrame]:
    processed = cfg.path("processed_dir")
    return (
        read_parquet(processed / RECIPES_CLEAN),
        read_parquet(processed / INTERACTIONS_CLEAN),
    )


# --------------------------------------------------------------------------- splits


def run_splits(cfg: Configs | None = None) -> str:
    cfg = cfg or load_configs()
    recipes, interactions = load_clean(cfg)
    with RunContext.open(cfg, stage="splits") as run:
        all_splits = splits.build_all_splits(interactions, recipes, cfg)
        rows = []
        for stage, split in all_splits.items():
            leak = splits.assert_no_leakage(split)
            run.write_json(f"metrics/leakage_{stage}.json", leak)
            rows.append({"stage": stage, **split.denominators})
            # Cohort ids stay inside the run directory: they are pseudonymous keys, not
            # something to publish alongside results.
            run.write_json(
                f"metrics/cohort_{stage}.json",
                {
                    "history_eligible_users": split.history_eligible_users,
                    "cohort_users": split.cohort_users,
                    "ranking_users": split.ranking_users,
                },
            )
        frame = pd.DataFrame(rows)
        run.write_table("tables/t03_split_and_eligibility.csv", frame)
        write_csv(frame, cfg.path("reports_dir") / "split_summary.csv")
        return run.run_id


# --------------------------------------------------------------------------- embeddings


def run_embeddings(cfg: Configs | None = None, *, backend: str | None = None) -> str:
    cfg = cfg or load_configs()
    recipes, _ = load_clean(cfg)
    text_mod.assert_no_forbidden_fields(cfg.model)

    with RunContext.open(cfg, stage="embeddings") as run:
        with Timer(run, "render_text"):
            rendered = text_mod.render_catalogue(recipes, cfg.model, cfg.tags)
        write_parquet(rendered, cfg.path("processed_dir") / RENDERED_TEXT)

        encoder = build_encoder(cfg.model, backend=backend)
        provenance = encoder.provenance()
        run.set_model_revision(provenance.get("model_revision"))
        run.write_json("metrics/encoder_provenance.json", provenance)

        tokeniser = getattr(encoder, "tokeniser", None)
        run.write_json(
            "metrics/truncation.json",
            text_mod.truncation_report(rendered, tokeniser, cfg.model.encoder.max_seq_length),
        )

        cache_dir = cfg.root / cfg.model.embedding_cache.dir
        with Timer(run, "encode"):
            store = embed.build_embeddings(
                rendered,
                encoder,
                cache_dir=cache_dir if cfg.model.embedding_cache.enabled else None,
            )
        run.note("n_vectors", len(store.recipe_ids))
        run.note("embedding_dimension", store.dimension)
        return run.run_id


# --------------------------------------------------------------------------- evaluation


def _prepare_context(cfg: Configs, stage: str) -> tuple[Any, Any]:
    recipes, interactions = load_clean(cfg)
    split = splits.build_stage_split(stage, interactions, recipes, cfg)
    splits.assert_no_leakage(split)

    store = embed.EmbeddingStore.load(cfg.root / cfg.model.embedding_cache.dir)
    catalogue_ids = split.catalogue["id"].to_numpy(dtype="int64")
    missing = [int(r) for r in catalogue_ids if not store.has(int(r))]
    if missing:
        raise RuntimeError(
            f"{len(missing)} catalogue recipes have no embedding (e.g. {missing[:5]}). "
            "Re-run `python tasks.py embeddings` after any change to the tag rules or the "
            "cleaning configuration."
        )

    prof = profiles_mod.build_profiles(split.positives, store, users=split.cohort_users)
    pop = splits.popularity_scores(split)
    ctx = harness.build_context(cfg, split, store, prof, pop)
    return ctx, split


def run_evaluation(
    cfg: Configs | None = None,
    *,
    stage: str = "validation",
    with_sensitivity: bool = True,
    max_users: int | None = None,
) -> str:
    """Run one evaluation stage end to end and emit every table and figure."""
    cfg = cfg or load_configs()
    if stage == "final":
        acquire.assert_unrecorded_placeholders_absent(cfg)

    with RunContext.open(cfg, stage=stage) as run:
        ctx, split = _prepare_context(cfg, stage)
        run.write_json("metrics/split_denominators.json", split.denominators)
        run.write_json("metrics/encoder_provenance.json", ctx.store.provenance)
        run.write_json("metrics/profile_notes.json", ctx.profiles.notes)

        users = split.ranking_users[:max_users] if max_users else split.ranking_users
        if not users:
            run.record_failure(
                "empty_ranking_cohort",
                f"stage {stage} has no user with an eligible novel positive in the label "
                "window; no ranking metric can be computed",
            )
            return run.run_id

        k, b = cfg.research.protocol.shortlist_size_k, cfg.research.protocol.band_cap_b
        with Timer(run, "evaluate"):
            results = harness.evaluate_stage(ctx, users=users, run=run)
        run.write_table("tables/per_user_results.csv", results)

        collapsed = average_random_repeats(results)
        summary = aggregate_per_method(collapsed)
        run.write_table("tables/t04_method_comparison.csv", summary)

        paired, details = stats.run_preplanned_comparisons(results, cfg)
        run.write_table("tables/t05_paired_differences.csv", paired)
        run.write_json("metrics/paired_comparisons.json", details)

        run.write_table(
            "tables/t08_feasibility_and_failures.csv", tbl_mod.feasibility_table(collapsed)
        )
        run.write_table(
            "tables/denominators.csv", stats.denominator_table(results, split.denominators)
        )
        common = stats.common_success_subset(results, list(cfg.research.protocol.methods))
        run.write_table("tables/common_success_comparison.csv", aggregate_per_method(common))

        # Broader-cohort feasibility coverage, reported separately from ranking metrics.
        cohort_sample = split.cohort_users[:5000]
        run.write_table(
            "tables/feasibility_coverage.csv",
            harness.feasibility_coverage(ctx, k, b, cohort_sample),
        )

        worked = _worked_example(cfg, ctx, users[0], run)
        run.write_json("metrics/worked_example.json", worked)

        if with_sensitivity:
            with Timer(run, "sensitivity"):
                sweeps = sensitivity.run_all_sweeps(ctx, cfg, users=users, run=run)
            run.write_table("tables/t06_sensitivity_length.csv", sweeps["length_sweep_summary"])
            run.write_table("tables/t07_sensitivity_cap.csv", sweeps["cap_sweep_summary"])
            run.write_table("tables/sensitivity_infeasibility.csv", sweeps["infeasibility"])

        _emit_figures(cfg, run, summary, worked)
        return run.run_id


def _worked_example(cfg: Configs, ctx: Any, user_id: int, run: RunContext) -> dict[str, Any]:
    """One real user, solved unpruned, with the dual certificate and the graphical slice."""
    from foodcom.models.scoring import score_candidates
    from foodcom.optimisation.lpp import ShortlistProblem, solve_primal

    protocol = cfg.research.protocol
    mask = ctx.candidate_mask(int(user_id))
    candidate_ids = ctx.catalogue_ids[mask]
    scores = score_candidates(int(user_id), candidate_ids, ctx.profiles, ctx.store)
    problem = ShortlistProblem(
        candidate_ids=candidate_ids,
        scores=scores,
        band_of=ctx.band_index[mask],
        k=protocol.shortlist_size_k,
        caps=np.full(len(ctx.band_labels), protocol.band_cap_b, dtype="int64"),
        band_labels=ctx.band_labels,
        user_id=int(user_id),
    )

    # Band pruning is exact for this structure, and the unpruned simplex is not viable at
    # catalogue scale - 229k columns against 5 rows runs for minutes and returns
    # success=False, on our data and on a synthetic problem of the same shape. Optimality
    # on the FULL problem is instead established by exhibiting a matching dual certificate:
    # a primal-feasible x*, a dual-feasible (alpha, beta, gamma) covering every one of the
    # n constraints, and equal objectives. By weak duality that proves x* optimal, which is
    # a stronger statement than a solver run converging.
    solution = solve_primal(problem, tol=cfg.model.solver.tolerance, prune=True)
    _, dual_sol, duality = dual_mod.check_duality(
        problem, solution, tol=cfg.model.solver.tolerance
    )
    oracle = integrality.verify_against_oracles(
        problem, tol=cfg.model.solver.tolerance, enumerate_if_small=False
    )
    perturbations = [
        dual_mod.perturb_band_cap(
            problem, g, +1, tol=cfg.model.solver.tolerance, beta=dual_sol.beta
        )
        for g in range(problem.n_bands)
    ]

    run.write_table(
        "tables/t10_primal_dual_verification.csv",
        tbl_mod.duality_table(duality.as_dict(), list(ctx.band_labels), dual_sol.as_dict()),
    )
    score_map = {int(r): float(s) for r, s in zip(candidate_ids, scores, strict=True)}
    run.write_table(
        "tables/t09_worked_lpp_example.csv",
        tbl_mod.worked_example_table(solution.as_dict(), ctx.split.catalogue, score_map),
    )

    slice_dict = None
    try:
        slice_obj = graphical.build_slice(problem, solution)
        slice_dict = slice_obj.as_dict()
        run.write_table("tables/graphical_slice.csv", slice_obj.to_frame())
        run.write_json("metrics/graphical_slice.json", slice_dict)
    except graphical.SliceNotAvailable as exc:
        run.record_failure("graphical_slice", str(exc))

    return {
        "user_label": f"demo-user-{abs(hash(int(user_id))) % 10000:04d}",
        "solution": solution.as_dict(),
        "dual": dual_sol.as_dict(),
        "duality": duality.as_dict(),
        "oracle_checks": oracle,
        "cap_perturbations": perturbations,
        "flow_network": integrality.flow_network_description(problem),
        "graphical_slice": slice_dict,
    }


def _emit_figures(
    cfg: Configs, run: RunContext, summary: pd.DataFrame, worked: dict[str, Any]
) -> None:
    out_dir = run.dir / "figures"
    audit_dir = cfg.path("reports_dir") / "audit"
    k = cfg.research.protocol.shortlist_size_k
    artifacts = []

    def _try(fn, *args, **kwargs) -> None:
        try:
            artifacts.append(fn(*args, **kwargs).as_dict())
        except Exception as exc:
            run.record_failure("figure", f"{fn.__name__}: {exc}")

    for csv_name, fn in (
        ("interactions__rating_distribution.csv", fig_mod.fig_rating_distribution),
        ("recipes__recipe_minutes_histogram.csv", fig_mod.fig_minutes_distribution),
        ("recipes__recipe_minutes_bands.csv", fig_mod.fig_band_composition),
        ("interactions__user_positive_history_sizes.csv", fig_mod.fig_history_sizes),
    ):
        path = audit_dir / csv_name
        if path.exists():
            _try(fn, pd.read_csv(path), out_dir, run.run_id)
        else:
            run.record_failure("figure", f"missing audit table {csv_name}")

    if not summary.empty:
        _try(fig_mod.fig_method_comparison, summary, "recall", out_dir, run.run_id, k)
        _try(fig_mod.fig_method_comparison, summary, "ndcg", out_dir, run.run_id, k)
        _try(fig_mod.fig_relevance_variety_tradeoff, summary, out_dir, run.run_id, k)

    sweep_path = run.dir / "tables" / "t06_sensitivity_length.csv"
    cap_path = run.dir / "tables" / "t07_sensitivity_cap.csv"
    if sweep_path.exists() and cap_path.exists():
        both = pd.concat([pd.read_csv(sweep_path), pd.read_csv(cap_path)], ignore_index=True)
        _try(fig_mod.fig_sensitivity, both, out_dir, run.run_id)

    if worked.get("graphical_slice"):
        _try(fig_mod.fig_graphical_slice, worked["graphical_slice"], out_dir, run.run_id)

    run.write_json("figures/index.json", artifacts)
    # Copy into the shared figures/ directory for convenience; the run copy stays canonical.
    shared = cfg.path("figures_dir")
    shared.mkdir(parents=True, exist_ok=True)
    for art in artifacts:
        for key in ("png", "underlying_csv"):
            src = Path(art[key])
            if src.exists():
                (shared / src.name).write_bytes(src.read_bytes())


# --------------------------------------------------------------------------- pack


def run_results_pack(cfg: Configs | None = None, run_id: str | None = None) -> Path:
    from foodcom.reporting.results_pack import build_results_pack

    cfg = cfg or load_configs()
    runs_dir = cfg.path("runs_dir")
    if run_id is None:
        candidates = sorted(
            (p for p in runs_dir.glob("final-*") if (p / "manifest.json").exists()),
            reverse=True,
        ) or sorted(
            (p for p in runs_dir.glob("validation-*") if (p / "manifest.json").exists()),
            reverse=True,
        )
        if not candidates:
            log.warning("no evaluation run found; the pack will be mostly PENDING")
            run_dir = runs_dir / "none"
        else:
            run_dir = candidates[0]
    else:
        run_dir = runs_dir / run_id

    return build_results_pack(cfg, run_dir, gate_status=acquire.gate_status(cfg))
