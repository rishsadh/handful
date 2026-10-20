"""Shared fixtures.

Every fixture here is SYNTHETIC. Synthetic data is permitted for software unit tests and
for nothing else: it is never research data and never appears in the paper.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from foodcom.testing.synthetic import (
    make_synthetic_raw,
    synthetic_config_overrides,
    write_synthetic_raw,
)
from foodcom.utils.config import load_configs

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def real_config():
    """The project's actual configuration, unmodified. Used for protocol assertions."""
    return load_configs()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A scratch project: a copy of config/ plus synthetic raw files."""
    (tmp_path / "config").mkdir(parents=True)
    for name in ("cleaning.yaml", "model.yaml", "tag_rules.yaml"):
        shutil.copy(REPO / "config" / name, tmp_path / "config" / name)

    research = yaml.safe_load((REPO / "config" / "research.yaml").read_text(encoding="utf-8"))
    research["dataset"].update(synthetic_config_overrides())
    research["dataset"]["licence_permits_redistribution"] = False
    research["protocol"]["max_users"] = 40
    research["protocol"]["bootstrap_resamples"] = 100
    (tmp_path / "config" / "research.yaml").write_text(
        yaml.safe_dump(research, sort_keys=False), encoding="utf-8"
    )

    model = yaml.safe_load((tmp_path / "config" / "model.yaml").read_text(encoding="utf-8"))
    model["encoder"]["backend"] = "deterministic_test"
    (tmp_path / "config" / "model.yaml").write_text(
        yaml.safe_dump(model, sort_keys=False), encoding="utf-8"
    )

    write_synthetic_raw(tmp_path / "data" / "raw", n_recipes=200, n_users=40)
    for sub in ("data/interim", "data/processed", "runs", "figures", "reports", "docs"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def cfg(workspace: Path):
    return load_configs(config_dir=workspace / "config", root=workspace)


@pytest.fixture
def raw_frames():
    return make_synthetic_raw(seed=7, n_recipes=200, n_users=40)


@pytest.fixture
def cleaned(cfg, raw_frames):
    from foodcom.data.clean import clean_interactions, clean_recipes

    recipes_raw, interactions_raw = raw_frames
    rec = clean_recipes(recipes_raw, cfg)
    inter = clean_interactions(interactions_raw, rec.frame, cfg)
    return rec, inter


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(1234)
