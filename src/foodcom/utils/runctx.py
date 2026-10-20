"""Run contexts.

Every research run gets its own directory under `runs/`, and everything needed to
reproduce or challenge a number in the Results Pack lives inside it: the exact config, the
hashes of the data it read, the code revision, package versions, the model revision, the
seeds, when it started and finished, its logs, its metrics, its figures and any failures.

Khushi should be able to take a run id from a table caption and find the number's origin
without reading a line of Python.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from foodcom.utils import logging as flog
from foodcom.utils.config import Configs
from foodcom.utils.hashing import sha256_file, sha256_obj

log = flog.get_logger(__name__)

_TRACKED_PACKAGES = [
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "scikit-learn",
    "pydantic",
    "PyYAML",
    "matplotlib",
    "torch",
    "sentence-transformers",
    "transformers",
    "huggingface-hub",
    "streamlit",
    "plotly",
]


def _package_versions() -> dict[str, str]:
    import importlib.metadata as md

    out: dict[str, str] = {}
    for name in _TRACKED_PACKAGES:
        try:
            out[name] = md.version(name)
        except Exception:
            out[name] = "not-installed"
    return out


def _git_info(root: Path) -> dict[str, Any]:
    def _run(*args: str) -> str | None:
        try:
            res = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return res.stdout.strip() if res.returncode == 0 else None
        except Exception:
            return None

    revision = _run("rev-parse", "HEAD")
    status = _run("status", "--porcelain")
    return {
        "revision": revision,
        "branch": _run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(status) if status is not None else None,
        "dirty_files": status.splitlines() if status else [],
    }


def new_run_id(stage: str) -> str:
    """A sortable, unique run id: `<stage>-<utc timestamp>-<8 hex>`."""
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stage}-{stamp}-{uuid.uuid4().hex[:8]}"


class RunContext:
    """An open research run.

    Use it as a context manager so the manifest is always completed, including when the
    run fails:

        with RunContext.open(cfg, stage="validation") as run:
            run.write_json("metrics/per_user.json", metrics)
    """

    def __init__(self, cfg: Configs, stage: str, run_id: str, root: Path) -> None:
        self.cfg = cfg
        self.stage = stage
        self.run_id = run_id
        self.dir = root
        self._t0 = time.perf_counter()
        self._started = dt.datetime.now(dt.UTC)
        self._manifest: dict[str, Any] = {}
        self._failures: list[dict[str, Any]] = []
        self._timings: dict[str, float] = {}

    # ---------------------------------------------------------------- lifecycle

    @classmethod
    def open(
        cls,
        cfg: Configs,
        stage: str,
        *,
        extra: dict[str, Any] | None = None,
        data_files: list[Path] | None = None,
    ) -> RunContext:
        run_id = new_run_id(stage)
        root = cfg.path("runs_dir") / run_id
        for sub in ("logs", "metrics", "figures", "tables", "config"):
            (root / sub).mkdir(parents=True, exist_ok=True)

        flog.configure(logfile=root / "logs" / "run.log")
        run = cls(cfg, stage, run_id, root)

        snapshot = cfg.as_snapshot()
        run._manifest = {
            "run_id": run_id,
            "stage": stage,
            "protocol_version": cfg.research.protocol_version,
            "started_utc": run._started.isoformat(),
            "completed_utc": None,
            "status": "running",
            "config_sha256": sha256_obj(snapshot),
            "config": snapshot,
            "dataset_files": run._hash_data_files(data_files or []),
            "code": _git_info(cfg.root),
            "packages": _package_versions(),
            "python": platform.python_version(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            "seeds": {
                "cohort_seed": cfg.research.protocol.cohort_seed,
                "random_method_seed": cfg.research.protocol.random_seed,
                "bootstrap_seed": cfg.research.protocol.bootstrap_seed,
            },
            "model_revision": cfg.model.encoder.model_revision,
            "env": {
                "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED"),
            },
            "extra": extra or {},
        }
        (root / "config" / "config_snapshot.json").write_text(
            json.dumps(snapshot, indent=2, default=str), encoding="utf-8"
        )
        run._flush_manifest()
        log.info("run %s opened at %s", run_id, root)
        return run

    def __enter__(self) -> RunContext:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            self.record_failure("run_aborted", f"{exc_type.__name__}: {exc}")
            self.close(status="failed")
        else:
            self.close(status="completed")
        return False

    def close(self, status: str = "completed") -> None:
        self._manifest["completed_utc"] = dt.datetime.now(dt.UTC).isoformat()
        self._manifest["elapsed_seconds"] = round(time.perf_counter() - self._t0, 3)
        self._manifest["status"] = status
        self._manifest["timings_seconds"] = dict(self._timings)
        self._manifest["failures"] = self._failures
        self._flush_manifest()
        if self._failures:
            self.write_json("failures.json", self._failures)
        log.info("run %s %s in %.2fs", self.run_id, status, self._manifest["elapsed_seconds"])

    # ---------------------------------------------------------------- recording

    def _hash_data_files(self, files: list[Path]) -> list[dict[str, Any]]:
        out = []
        for f in files:
            p = Path(f)
            if p.exists():
                out.append(
                    {
                        "path": str(p.relative_to(self.cfg.root))
                        if p.is_absolute() and p.is_relative_to(self.cfg.root)
                        else str(p),
                        "bytes": p.stat().st_size,
                        "sha256": sha256_file(p),
                    }
                )
            else:
                out.append({"path": str(p), "bytes": None, "sha256": None, "missing": True})
        return out

    def add_data_files(self, files: list[Path]) -> None:
        self._manifest["dataset_files"].extend(self._hash_data_files(files))
        self._flush_manifest()

    def set_model_revision(self, revision: str | None) -> None:
        self._manifest["model_revision"] = revision
        self._flush_manifest()

    def note(self, key: str, value: Any) -> None:
        """Attach an arbitrary fact to the manifest's `extra` block."""
        self._manifest["extra"][key] = value
        self._flush_manifest()

    def record_timing(self, key: str, seconds: float) -> None:
        self._timings[key] = round(float(seconds), 6)

    def record_failure(self, kind: str, detail: str, **fields: Any) -> None:
        entry = {
            "kind": kind,
            "detail": detail,
            "at_utc": dt.datetime.now(dt.UTC).isoformat(),
            **fields,
        }
        self._failures.append(entry)
        log.warning("run failure recorded: %s - %s", kind, detail)

    @property
    def failures(self) -> list[dict[str, Any]]:
        return list(self._failures)

    # ---------------------------------------------------------------- outputs

    def _flush_manifest(self) -> None:
        (self.dir / "manifest.json").write_text(
            json.dumps(self._manifest, indent=2, default=str), encoding="utf-8"
        )

    @property
    def manifest(self) -> dict[str, Any]:
        return dict(self._manifest)

    def path(self, relative: str) -> Path:
        p = self.dir / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write_json(self, relative: str, payload: Any) -> Path:
        p = self.path(relative)
        p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return p

    def write_table(self, relative: str, frame: Any) -> Path:
        """Write a pandas DataFrame as CSV. Every figure's underlying data goes here."""
        p = self.path(relative)
        frame.to_csv(p, index=False, encoding="utf-8")
        return p


class Timer:
    """Small helper for `run.record_timing`."""

    def __init__(self, run: RunContext | None, key: str) -> None:
        self.run = run
        self.key = key
        self.seconds = 0.0

    def __enter__(self) -> Timer:
        self._t = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> bool:
        self.seconds = time.perf_counter() - self._t
        if self.run is not None:
            self.run.record_timing(self.key, self.seconds)
        return False
