"""Loading real processed data for the demo.

Two rules shape this module.

* The demo shows real Food.com data or it shows nothing. If the processed tables are not
  there, every screen says so plainly. Nothing is simulated to fill the space.
* Scenario controls never write. They build a fresh problem in memory; the benchmark
  tables on disk are read-only from here.

User identity: the demo maps each pseudonymous Food.com user id to a stable label like
`profile-0007`. The mapping is deterministic per run so a demonstration is repeatable, and
raw ids are not printed on any screen by default.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from foodcom.data import acquire, splits
from foodcom.evaluation.harness import EvalContext, build_context
from foodcom.features.embed import EmbeddingStore
from foodcom.features.profiles import build_profiles
from foodcom.pipeline import INTERACTIONS_CLEAN, RECIPES_CLEAN
from foodcom.testing import SYNTHETIC_MARKER
from foodcom.utils.config import Configs, load_configs


def project_config() -> Configs:
    """Load the project config, honouring a data-root override.

    `FOODCOM_PROJECT_ROOT` points the demo at a different project directory - used to
    exercise the interface against the synthetic fixture before the real data exists.
    Any config whose dataset provenance carries the synthetic marker makes the demo
    display a permanent warning banner, so a fixture can never be mistaken for the
    real study.
    """
    override = os.environ.get("FOODCOM_PROJECT_ROOT")
    if override:
        root = Path(override)
        return load_configs(config_dir=root / "config", root=root)
    return load_configs()


@dataclass
class DemoState:
    cfg: Configs
    available: bool
    reason: str | None
    ctx: EvalContext | None = None
    split: Any | None = None
    recipes: pd.DataFrame | None = None
    label_to_user: dict[str, int] | None = None
    user_to_label: dict[int, str] | None = None
    gate: dict[str, Any] | None = None
    is_synthetic: bool = False

    def labels(self) -> list[str]:
        return sorted(self.label_to_user or {})


@st.cache_resource(show_spinner="loading processed Food.com data ...")
def load_demo_state(stage: str = "validation") -> DemoState:
    cfg = project_config()
    gate = acquire.gate_status(cfg)
    synthetic = SYNTHETIC_MARKER in " ".join(
        [cfg.research.dataset.kaggle_version, cfg.research.dataset.name,
         cfg.research.dataset.licence_text]
    )
    processed = cfg.path("processed_dir")

    missing = [
        str(p)
        for p in (processed / RECIPES_CLEAN, processed / INTERACTIONS_CLEAN)
        if not p.exists()
    ]
    cache_dir = cfg.root / cfg.model.embedding_cache.dir
    if not EmbeddingStore.exists(cache_dir):
        missing.append(str(cache_dir))
    if missing:
        return DemoState(
            cfg=cfg,
            available=False,
            reason=(
                "The processed data this demo needs has not been built yet. Missing:\n\n"
                + "\n".join(f"- `{m}`" for m in missing)
                + "\n\nRun the pipeline first: `python tasks.py all`."
            ),
            gate=gate,
            is_synthetic=synthetic,
        )

    recipes = pd.read_parquet(processed / RECIPES_CLEAN)
    interactions = pd.read_parquet(processed / INTERACTIONS_CLEAN)
    split = splits.build_stage_split(stage, interactions, recipes, cfg)
    store = EmbeddingStore.load(cache_dir)

    catalogue_ids = split.catalogue["id"].to_numpy(dtype="int64")
    if any(not store.has(int(r)) for r in catalogue_ids[:200]):
        return DemoState(
            cfg=cfg,
            available=False,
            reason=(
                "The embedding store does not cover the current catalogue. Re-run "
                "`python tasks.py embeddings` after any change to the tag rules or the "
                "cleaning configuration."
            ),
            gate=gate,
            is_synthetic=synthetic,
        )

    users = split.ranking_users or split.cohort_users
    profiles = build_profiles(split.positives, store, users=users)
    ctx = build_context(cfg, split, store, profiles, splits.popularity_scores(split))

    warm = [u for u in users if u not in set(profiles.cold_users)]
    user_to_label = {int(u): f"profile-{i:04d}" for i, u in enumerate(sorted(warm))}
    label_to_user = {v: k for k, v in user_to_label.items()}

    return DemoState(
        cfg=cfg,
        available=True,
        reason=None,
        ctx=ctx,
        split=split,
        recipes=recipes.set_index("id", drop=False),
        label_to_user=label_to_user,
        user_to_label=user_to_label,
        gate=gate,
        is_synthetic=synthetic,
    )


@st.cache_data(show_spinner=False)
def latest_run(stage_prefix: str = "final") -> dict[str, Any] | None:
    """The most recent completed run of a stage, for the evidence panel."""
    cfg = project_config()
    runs = cfg.path("runs_dir")
    if not runs.exists():
        return None
    candidates = sorted(
        (p for p in runs.glob(f"{stage_prefix}-*") if (p / "manifest.json").exists()),
        reverse=True,
    )
    if not candidates and stage_prefix == "final":
        return latest_run("validation")
    if not candidates:
        return None
    run_dir = candidates[0]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    tables = {
        p.stem: pd.read_csv(p) for p in sorted((run_dir / "tables").glob("*.csv"))
    }
    figures = sorted((run_dir / "figures").glob("*.png"))
    metrics = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((run_dir / "metrics").glob("*.json"))
    }
    return {
        "run_dir": run_dir,
        "run_id": manifest.get("run_id", run_dir.name),
        "manifest": manifest,
        "tables": tables,
        "figures": figures,
        "metrics": metrics,
    }


def source_manifest() -> dict[str, Any] | None:
    cfg = project_config()
    path = cfg.path("processed_dir") / "source_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def recipe_row(state: DemoState, recipe_id: int) -> pd.Series:
    return state.recipes.loc[int(recipe_id)]


def ingredient_set(state: DemoState, recipe_id: int) -> set[str]:
    from foodcom.features.text import as_list

    return {
        str(i).strip().lower()
        for i in as_list(recipe_row(state, recipe_id).get("ingredients"))
        if isinstance(i, str)
    }


def shared_ingredients(state: DemoState, recipe_id: int, history_ids: list[int]) -> list[str]:
    """Ingredients this candidate shares with the user's positively rated history.

    Used for the factual explanation on a recipe card. It is a description of overlap in
    the source metadata, not a causal account of why the model scored the recipe.
    """
    target = ingredient_set(state, recipe_id)
    counts: dict[str, int] = {}
    for rid in history_ids:
        for ing in ingredient_set(state, rid) & target:
            counts[ing] = counts.get(ing, 0) + 1
    return [ing for ing, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def history_frame(state: DemoState, user_id: int, limit: int = 12) -> pd.DataFrame:
    """The user's pre-cutoff positively rated recipes."""
    positives = sorted(state.split.positives.get(int(user_id), set()))
    rows = []
    hist = state.split.history
    dated = hist[(hist["user_id"] == int(user_id)) & (hist["is_positive"])]
    date_by_recipe = dict(zip(dated["recipe_id"], dated["date"], strict=True))
    for rid in positives:
        row = recipe_row(state, rid)
        rows.append(
            {
                "recipe_id": int(rid),
                "name": row["name"],
                "reported_minutes": int(row["minutes"]),
                "band": str(row["band"]),
                "rated_on": str(pd.Timestamp(date_by_recipe.get(rid)).date())
                if rid in date_by_recipe
                else "",
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("rated_on", ascending=False).head(limit) if len(frame) else frame


def scenario_mask(
    state: DemoState,
    user_id: int,
    *,
    max_minutes: int | None,
    excluded_terms: list[str],
) -> tuple[np.ndarray, dict[str, int]]:
    """Apply the hypothetical scenario filters on top of the real eligibility mask.

    Returns the mask and how many candidates each filter removed, so the UI can explain an
    infeasible scenario instead of just failing.
    """
    ctx = state.ctx
    mask = ctx.candidate_mask(int(user_id))
    removed = {"already_seen": int((~mask).sum()), "max_minutes": 0, "ingredient_terms": 0}

    if max_minutes is not None:
        minutes = state.split.catalogue["minutes"].to_numpy()
        over = mask & (minutes > max_minutes)
        removed["max_minutes"] = int(over.sum())
        mask = mask & ~over

    terms = [t.strip().lower() for t in excluded_terms if t.strip()]
    if terms:
        from foodcom.features.text import as_list

        ing_lists = state.split.catalogue["ingredients"].to_numpy()
        hit = np.zeros(len(mask), dtype=bool)
        for i, raw in enumerate(ing_lists):
            if not mask[i]:
                continue
            blob = " ".join(str(x).lower() for x in as_list(raw))
            if any(term in blob for term in terms):
                hit[i] = True
        removed["ingredient_terms"] = int(hit.sum())
        mask = mask & ~hit

    return mask, removed
