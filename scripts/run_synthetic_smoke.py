#!/usr/bin/env python
"""End-to-end pipeline run on the SYNTHETIC fixture.

SYNTHETIC. NOT RESEARCH DATA. Nothing this produces may appear in the paper.

Its purpose is to prove that every stage - acquire, audit, clean, splits, embeddings,
evaluation, sensitivity, duality, figures, Results Pack - actually executes and agrees with
itself, before the real Food.com files are available. It runs in a scratch directory and
never touches `data/` or `runs/` in the repository.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

from foodcom import pipeline
from foodcom.testing import SYNTHETIC_MARKER
from foodcom.testing.synthetic import synthetic_config_overrides, write_synthetic_raw
from foodcom.utils import logging as flog
from foodcom.utils.config import load_configs

ROOT = Path(__file__).resolve().parents[1]


def prepare_workspace(workspace: Path, *, n_recipes: int, n_users: int) -> Path:
    """Build a self-contained scratch project: config copy + synthetic raw files."""
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    for name in ("cleaning.yaml", "model.yaml", "tag_rules.yaml"):
        shutil.copy(ROOT / "config" / name, workspace / "config" / name)

    research = yaml.safe_load((ROOT / "config" / "research.yaml").read_text(encoding="utf-8"))
    research["dataset"].update(synthetic_config_overrides())
    research["dataset"]["name"] = f"{SYNTHETIC_MARKER} (shaped like Food.com)"
    research["dataset"]["licence_permits_redistribution"] = False
    # A small fixture cannot support a 5,000-user cap or 2,000 bootstrap resamples
    # meaningfully; both are reduced so the smoke run stays fast. The real protocol in
    # config/research.yaml is untouched.
    research["protocol"]["max_users"] = 40
    research["protocol"]["bootstrap_resamples"] = 200
    # The deterministic test encoder is low-dimensional; keep everything else identical.
    (workspace / "config" / "research.yaml").write_text(
        yaml.safe_dump(research, sort_keys=False), encoding="utf-8"
    )

    model = yaml.safe_load((workspace / "config" / "model.yaml").read_text(encoding="utf-8"))
    model["encoder"]["backend"] = "deterministic_test"
    (workspace / "config" / "model.yaml").write_text(
        yaml.safe_dump(model, sort_keys=False), encoding="utf-8"
    )

    write_synthetic_raw(workspace / "data" / "raw", n_recipes=n_recipes, n_users=n_users)
    for sub in ("data/interim", "data/processed", "runs", "figures", "reports", "docs"):
        (workspace / sub).mkdir(parents=True, exist_ok=True)
    return workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep the scratch workspace")
    parser.add_argument("--workspace", default=None, help="use this directory instead of a temp one")
    parser.add_argument("--recipes", type=int, default=400)
    parser.add_argument("--users", type=int, default=60)
    args = parser.parse_args()

    flog.configure()
    tmp = Path(args.workspace) if args.workspace else Path(
        tempfile.mkdtemp(prefix="foodcom-smoke-")
    )
    print(f"SYNTHETIC SMOKE RUN — workspace: {tmp}")
    print("Nothing produced here is research data.\n")

    try:
        prepare_workspace(tmp, n_recipes=args.recipes, n_users=args.users)
        cfg = load_configs(config_dir=tmp / "config", root=tmp)

        print("[1/7] acquire")
        pipeline.run_acquire(cfg)
        print("[2/7] audit")
        pipeline.run_audit(cfg)
        print("[3/7] clean")
        pipeline.run_clean(cfg)
        print("[4/7] splits")
        pipeline.run_splits(cfg)
        print("[5/7] embeddings (deterministic test encoder)")
        pipeline.run_embeddings(cfg)
        print("[6/7] validation evaluation + sensitivity")
        run_id = _evaluate(cfg)
        print("[7/7] results pack")
        pack = pipeline.run_results_pack(cfg, run_id=run_id)

        manifest = json.loads((cfg.path("runs_dir") / run_id / "manifest.json").read_text())
        print("\n--- SYNTHETIC SMOKE SUMMARY ---")
        print(f"run id          : {run_id}")
        print(f"status          : {manifest['status']}")
        print(f"failures logged : {len(manifest.get('failures', []))}")
        for f in manifest.get("failures", []):
            print(f"   - {f['kind']}: {f['detail'][:140]}")
        summary = cfg.path("runs_dir") / run_id / "tables" / "t04_method_comparison.csv"
        if summary.exists():
            import pandas as pd

            print("\nmethod comparison (SYNTHETIC — not a research result):")
            print(
                pd.read_csv(summary)[
                    ["method", "n_users_with_positives", "mean_recall_at_k",
                     "mean_ndcg_at_k", "mean_bands_represented", "mean_cap_violations"]
                ].to_string(index=False)
            )
        figures = list((cfg.path("runs_dir") / run_id / "figures").glob("*.png"))
        print(f"\nfigures written : {len(figures)}")
        print(f"results pack    : {pack}")
        print("\nSMOKE RUN PASSED")
        return 0
    except Exception as exc:
        print(f"\nSMOKE RUN FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
    finally:
        if not args.keep and args.workspace is None:
            print(f"\n(removing scratch workspace {tmp}; pass --keep to inspect it)")
            shutil.rmtree(tmp, ignore_errors=True)


def _evaluate(cfg) -> str:
    # allow_non_research_encoder is threaded through here and nowhere else: the harness
    # refuses to produce numbers from the deterministic test encoder by default.
    import foodcom.evaluation.harness as harness_mod
    import foodcom.evaluation.sensitivity as sens_mod

    original_stage = harness_mod.evaluate_stage
    original_sweeps = sens_mod.run_all_sweeps

    def patched_stage(ctx, **kwargs):
        kwargs["allow_non_research_encoder"] = True
        return original_stage(ctx, **kwargs)

    def patched_sweeps(ctx, cfg_, **kwargs):
        kwargs["allow_non_research_encoder"] = True
        return original_sweeps(ctx, cfg_, **kwargs)

    harness_mod.evaluate_stage = patched_stage
    sens_mod.run_all_sweeps = patched_sweeps
    pipeline.harness.evaluate_stage = patched_stage
    pipeline.sensitivity.run_all_sweeps = patched_sweeps
    try:
        return pipeline.run_evaluation(cfg, stage="validation", with_sensitivity=True)
    finally:
        harness_mod.evaluate_stage = original_stage
        sens_mod.run_all_sweeps = original_sweeps
        pipeline.harness.evaluate_stage = original_stage
        pipeline.sensitivity.run_all_sweeps = original_sweeps


if __name__ == "__main__":
    raise SystemExit(main())
