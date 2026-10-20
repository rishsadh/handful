"""End-to-end pipeline on the synthetic fixture, plus demo import and behaviour checks.

SYNTHETIC throughout. Nothing here is a research result.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from foodcom import pipeline
from foodcom.data.acquire import AcquisitionError, gate_status
from foodcom.evaluation import harness, sensitivity
from foodcom.evaluation.metrics import aggregate_per_method, average_random_repeats

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def allow_test_encoder(monkeypatch):
    """The harness refuses a non-research encoder unless a test says otherwise."""
    original_stage = harness.evaluate_stage
    original_sweeps = sensitivity.run_all_sweeps

    def patched_stage(ctx, **kwargs):
        kwargs["allow_non_research_encoder"] = True
        return original_stage(ctx, **kwargs)

    def patched_sweeps(ctx, cfg_, **kwargs):
        kwargs["allow_non_research_encoder"] = True
        return original_sweeps(ctx, cfg_, **kwargs)

    monkeypatch.setattr(harness, "evaluate_stage", patched_stage)
    monkeypatch.setattr(sensitivity, "run_all_sweeps", patched_sweeps)
    monkeypatch.setattr(pipeline.harness, "evaluate_stage", patched_stage)
    monkeypatch.setattr(pipeline.sensitivity, "run_all_sweeps", patched_sweeps)


@pytest.fixture
def pipeline_run(cfg, allow_test_encoder):
    """Run acquire -> audit -> clean -> splits -> embeddings -> validation."""
    pipeline.run_acquire(cfg)
    pipeline.run_audit(cfg)
    pipeline.run_clean(cfg)
    pipeline.run_splits(cfg)
    pipeline.run_embeddings(cfg)
    run_id = pipeline.run_evaluation(cfg, stage="validation", with_sensitivity=True)
    return cfg, run_id


# ------------------------------------------------------------------ the harness guard


def test_harness_refuses_a_non_research_encoder(cfg):
    """Without the explicit test opt-in, test-encoder numbers must not be produced."""
    pipeline.run_acquire(cfg)
    pipeline.run_clean(cfg)
    pipeline.run_embeddings(cfg)
    ctx, _ = pipeline._prepare_context(cfg, "validation")
    with pytest.raises(RuntimeError, match="non-research encoder"):
        harness.evaluate_stage(ctx, users=ctx.split.ranking_users[:2])


# ------------------------------------------------------------------ the gate


def test_gate_blocks_when_raw_files_are_missing(cfg):
    for f in (cfg.path("raw_dir")).glob("RAW_*.csv"):
        f.unlink()
    status = gate_status(cfg)
    assert not status["passed"]
    assert status["missing_files"]
    assert "kaggle.com" in status["instructions"]
    with pytest.raises(AcquisitionError, match="data gate not passed"):
        pipeline.run_acquire(cfg)


def test_gate_blocks_on_unrecorded_provenance(cfg, workspace):
    import yaml

    path = workspace / "config" / "research.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["dataset"]["licence_text"] = "UNRECORDED"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    from foodcom.utils.config import load_configs

    reloaded = load_configs(config_dir=workspace / "config", root=workspace)
    with pytest.raises(AcquisitionError, match="UNRECORDED"):
        pipeline.run_acquire(reloaded)


def test_redistribution_is_denied_when_unknown(cfg, workspace):
    import yaml

    from foodcom.data.acquire import redistribution_allowed
    from foodcom.utils.config import load_configs

    path = workspace / "config" / "research.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["dataset"]["licence_permits_redistribution"] = None
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    reloaded = load_configs(config_dir=workspace / "config", root=workspace)
    assert redistribution_allowed(reloaded) is False


# ------------------------------------------------------------------ the pipeline


@pytest.mark.slow
def test_full_pipeline_runs_and_records_everything(pipeline_run):
    cfg, run_id = pipeline_run
    run_dir = cfg.path("runs_dir") / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "completed"
    for key in ("config_sha256", "packages", "code", "seeds", "python", "started_utc",
                "completed_utc", "timings_seconds"):
        assert key in manifest, f"run manifest is missing {key}"

    for name in (
        "t04_method_comparison",
        "t05_paired_differences",
        "t08_feasibility_and_failures",
        "t09_worked_lpp_example",
        "t10_primal_dual_verification",
        "t06_sensitivity_length",
        "t07_sensitivity_cap",
        "denominators",
        "per_user_results",
    ):
        assert (run_dir / "tables" / f"{name}.csv").exists(), f"missing table {name}"

    figures = list((run_dir / "figures").glob("*.png"))
    assert len(figures) >= 7, f"expected the required figures, found {len(figures)}"
    index = json.loads((run_dir / "figures" / "index.json").read_text(encoding="utf-8"))
    for fig in index:
        assert fig["caption"] and fig["units"] and fig["run_id"] == run_id
        assert Path(fig["underlying_csv"]).exists()


@pytest.mark.slow
def test_all_four_methods_produce_results(pipeline_run):
    cfg, run_id = pipeline_run
    frame = pd.read_csv(cfg.path("runs_dir") / run_id / "tables" / "t04_method_comparison.csv")
    assert set(frame["method"]) == {"RANDOM", "POPULARITY_LP", "AI_TOPK", "AI_LP"}


@pytest.mark.slow
def test_lp_methods_never_violate_their_caps(pipeline_run):
    cfg, run_id = pipeline_run
    per_user = pd.read_csv(cfg.path("runs_dir") / run_id / "tables" / "per_user_results.csv")
    for method in ("AI_LP", "POPULARITY_LP", "RANDOM"):
        rows = per_user[(per_user["method"] == method) & per_user["feasible"]]
        assert (rows["cap_violations"] == 0).all(), f"{method} violated a cap"


@pytest.mark.slow
def test_exact_shortlist_size_on_feasible_users(pipeline_run):
    cfg, run_id = pipeline_run
    per_user = pd.read_csv(cfg.path("runs_dir") / run_id / "tables" / "per_user_results.csv")
    feasible = per_user[per_user["feasible"] & ~per_user["failed"].astype(bool)]
    assert feasible["exact_size_ok"].all()


@pytest.mark.slow
def test_duality_verification_passes_on_real_pipeline_output(pipeline_run):
    cfg, run_id = pipeline_run
    worked = json.loads(
        (cfg.path("runs_dir") / run_id / "metrics" / "worked_example.json").read_text(
            encoding="utf-8"
        )
    )
    assert worked["duality"]["strong_duality_holds"]
    assert worked["duality"]["complementary_slackness_holds"]
    assert worked["solution"]["verification"]["checks_passed"]
    assert worked["oracle_checks"]["greedy_matches_lp"]
    assert worked["oracle_checks"]["cap_free_matches_topk"]


@pytest.mark.slow
def test_graphical_slice_is_exported(pipeline_run):
    cfg, run_id = pipeline_run
    path = cfg.path("runs_dir") / run_id / "metrics" / "graphical_slice.json"
    if not path.exists():
        pytest.skip("this fixture's worked example could not yield a two-variable slice")
    slice_dict = json.loads(path.read_text(encoding="utf-8"))
    assert "slice" in slice_dict["caption"].lower()
    assert len(slice_dict["feasible_segment"]) == 2
    assert (cfg.path("runs_dir") / run_id / "tables" / "graphical_slice.csv").exists()


@pytest.mark.slow
def test_results_pack_is_generated_with_run_traceability(pipeline_run):
    cfg, run_id = pipeline_run
    path = pipeline.run_results_pack(cfg, run_id=run_id)
    text = path.read_text(encoding="utf-8")
    assert run_id in text
    for heading in (
        "Dataset identity", "Audit and cleaning", "Temporal split", "AI scoring layer",
        "linear programme", "Duality", "comparison methods", "Results",
        "Sensitivity analysis", "worked real example", "Figures", "Limitations",
        "must not make", "Interpretation prompts", "reproduce",
    ):
        assert heading in text, f"Results Pack is missing the section: {heading}"
    for forbidden in ("reduced choice overload", "faster decisions", "allergy-safe"):
        assert f"proves {forbidden}" not in text.lower()


@pytest.mark.slow
def test_same_seed_and_config_reproduce_the_same_numbers(pipeline_run, allow_test_encoder):
    cfg, run_id = pipeline_run
    first = pd.read_csv(cfg.path("runs_dir") / run_id / "tables" / "t04_method_comparison.csv")
    second_id = pipeline.run_evaluation(cfg, stage="validation", with_sensitivity=False)
    second = pd.read_csv(cfg.path("runs_dir") / second_id / "tables" /
                         "t04_method_comparison.csv")
    key = ["method", "mean_recall_at_k", "mean_ndcg_at_k"]
    pd.testing.assert_frame_equal(
        first[key].sort_values("method").reset_index(drop=True),
        second[key].sort_values("method").reset_index(drop=True),
    )


@pytest.mark.slow
def test_a_scenario_never_overwrites_benchmark_results(pipeline_run):
    """Scenario solving happens in memory. The run's tables must be untouched by it."""
    cfg, run_id = pipeline_run
    table = cfg.path("runs_dir") / run_id / "tables" / "t04_method_comparison.csv"
    before = table.read_bytes()

    ctx, split = pipeline._prepare_context(cfg, "validation")
    user_id = split.ranking_users[0]
    from foodcom.models.scoring import score_candidates
    from foodcom.optimisation.lpp import ShortlistProblem, solve_primal

    mask = ctx.candidate_mask(user_id)
    ids = ctx.catalogue_ids[mask]
    scores = score_candidates(user_id, ids, ctx.profiles, ctx.store)
    # A deliberately different scenario configuration.
    problem = ShortlistProblem(
        candidate_ids=ids,
        scores=scores,
        band_of=ctx.band_index[mask],
        k=4,
        caps=np.full(len(ctx.band_labels), 2, dtype="int64"),
        band_labels=ctx.band_labels,
        user_id=user_id,
    )
    solution = solve_primal(problem)
    assert solution.ok
    assert table.read_bytes() == before


@pytest.mark.slow
def test_random_repeats_collapse_before_the_bootstrap(pipeline_run):
    cfg, run_id = pipeline_run
    per_user = pd.read_csv(cfg.path("runs_dir") / run_id / "tables" / "per_user_results.csv")
    if "repeat" in per_user.columns:
        rnd = per_user[per_user["method"] == "RANDOM"]
        assert rnd.groupby("user_id").size().max() > 1
    collapsed = average_random_repeats(per_user)
    rnd = collapsed[collapsed["method"] == "RANDOM"]
    assert rnd.groupby("user_id").size().max() == 1
    assert not aggregate_per_method(collapsed).empty


# ------------------------------------------------------------------ the demo


def test_demo_module_imports_without_streamlit_running():
    """A syntax or import error in the demo must fail the suite, not the presentation."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path[:0]=[r'{}', r'{}']; "
            "import app.streamlit_app as a; "
            "assert callable(a.main); "
            "from app.components import screens, theme, dataload; "
            "assert screens.SCENARIO_BANNER and theme.CSS and dataload.load_demo_state".format(
                REPO, REPO / "src"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_demo_refuses_to_invent_data_when_nothing_is_processed(monkeypatch, tmp_path):
    """With no processed tables the demo must report the gate, not simulate a dataset."""
    import app.components.dataload as demo_dl

    from foodcom.utils.config import load_configs

    empty = tmp_path / "empty"
    (empty / "config").mkdir(parents=True)
    for name in ("research.yaml", "cleaning.yaml", "model.yaml", "tag_rules.yaml"):
        (empty / "config" / name).write_bytes((REPO / "config" / name).read_bytes())

    monkeypatch.setattr(
        demo_dl, "load_configs", lambda: load_configs(config_dir=empty / "config", root=empty)
    )
    state = demo_dl.load_demo_state.__wrapped__()
    assert not state.available
    assert "python tasks.py" in state.reason


def test_scenario_banner_declares_it_is_not_a_preference_or_a_safety_claim():
    from app.components.screens import SCENARIO_BANNER

    lowered = SCENARIO_BANNER.lower()
    assert "hypothetical" in lowered
    assert "not record" in lowered or "does not record" in lowered
    assert "allergy" in lowered


# ------------------------------------------------------------------ scenario controls


def _demo_state(cfg):
    """Build a DemoState directly, without Streamlit, from a prepared workspace."""
    import app.components.dataload as demo_dl

    ctx, split = pipeline._prepare_context(cfg, "validation")
    recipes = pd.read_parquet(cfg.path("processed_dir") / pipeline.RECIPES_CLEAN)
    warm = [u for u in split.ranking_users if u not in set(ctx.profiles.cold_users)]
    user_to_label = {int(u): f"profile-{i:04d}" for i, u in enumerate(sorted(warm))}
    return demo_dl.DemoState(
        cfg=cfg,
        available=True,
        reason=None,
        ctx=ctx,
        split=split,
        recipes=recipes.set_index("id", drop=False),
        label_to_user={v: k for k, v in user_to_label.items()},
        user_to_label=user_to_label,
        gate=gate_status(cfg),
        is_synthetic=True,
    )


@pytest.fixture
def demo_state(cfg):
    pipeline.run_acquire(cfg)
    pipeline.run_clean(cfg)
    pipeline.run_embeddings(cfg)
    return _demo_state(cfg)


@pytest.mark.slow
def test_scenario_filters_report_what_they_removed(demo_state):
    import app.components.dataload as demo_dl

    user_id = next(iter(demo_state.user_to_label))
    base, _ = demo_dl.scenario_mask(
        demo_state, user_id, max_minutes=None, excluded_terms=[]
    )
    limited, removed = demo_dl.scenario_mask(
        demo_state, user_id, max_minutes=20, excluded_terms=[]
    )
    assert limited.sum() < base.sum()
    assert removed["max_minutes"] == int(base.sum() - limited.sum())


@pytest.mark.slow
def test_ingredient_exclusion_actually_excludes_and_is_never_relaxed(demo_state):
    """An excluded term must not reappear in the shortlist under any circumstance."""
    import app.components.dataload as demo_dl
    from app.components.screens import _solve_for

    user_id = next(iter(demo_state.user_to_label))
    term = "garlic"
    mask, removed = demo_dl.scenario_mask(
        demo_state, user_id, max_minutes=None, excluded_terms=[term]
    )
    assert removed["ingredient_terms"] > 0, "the fixture should contain the excluded term"

    _, solution = _solve_for(demo_state, user_id, mask, k=6, cap=3)
    if not solution.feasibility.feasible:
        pytest.skip("this profile has no feasible shortlist under the exclusion")
    for rid in solution.ranked_ids:
        assert term not in " ".join(demo_dl.ingredient_set(demo_state, int(rid)))


@pytest.mark.slow
def test_infeasible_scenario_is_reported_with_a_reason_not_silently_relaxed(demo_state):
    from app.components.screens import _solve_for

    user_id = next(iter(demo_state.user_to_label))
    mask = demo_state.ctx.candidate_mask(user_id)
    # 4 bands x cap 1 = capacity 4, but 12 items are requested.
    problem, solution = _solve_for(demo_state, user_id, mask, k=12, cap=1)
    assert not solution.feasibility.feasible
    assert "reachable capacity" in solution.feasibility.reason
    assert len(solution.selected_ids) == 0
    # The caps were not quietly widened to make it work.
    assert problem.caps.tolist() == [1, 1, 1, 1]


@pytest.mark.slow
def test_demo_history_never_exposes_review_text_or_raw_ids(demo_state):
    import app.components.dataload as demo_dl

    user_id = next(iter(demo_state.user_to_label))
    frame = demo_dl.history_frame(demo_state, user_id)
    assert "review" not in frame.columns
    assert "user_id" not in frame.columns
    assert demo_state.user_to_label[user_id].startswith("profile-")
