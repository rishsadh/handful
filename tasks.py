#!/usr/bin/env python
"""Cross-platform task runner.

`make` is not installed on the machine this was built on, so the Makefile delegates here
and this is the entry point that actually works everywhere:

    python tasks.py setup        install the core stack into .venv
    python tasks.py setup-ai     add torch + sentence-transformers (~2.5 GB)
    python tasks.py acquire      record provenance and hash the raw files (data gate)
    python tasks.py audit        full raw-data audit -> docs/DATA_AUDIT.md
    python tasks.py clean        cleaning, quarantine and the exclusion ledger
    python tasks.py splits       temporal splits, cohorts and leakage checks
    python tasks.py embeddings   render recipe text and encode it
    python tasks.py validate     validation-stage evaluation (2017 labels)
    python tasks.py final        FINAL evaluation (2018 labels) - run once, frozen
    python tasks.py results-pack build docs/RESULTS_PACK.md
    python tasks.py test         run the test suite
    python tasks.py lint         ruff
    python tasks.py smoke        end-to-end run on the SYNTHETIC fixture
    python tasks.py demo         launch the Streamlit demo
    python tasks.py all          audit -> clean -> splits -> embeddings -> validate -> pack

`all` deliberately stops before `final`. The final test set is used exactly once, after
the configuration is frozen; chaining it into a convenience target is how a test set gets
spent by accident.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def _python() -> str:
    venv = ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / (
        "python.exe" if sys.platform == "win32" else "python"
    )
    return str(venv) if venv.exists() else sys.executable


def _run(args: list[str], env_extra: dict[str, str] | None = None) -> int:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    print(f"$ {' '.join(args)}", flush=True)
    return subprocess.run(args, cwd=ROOT, env=env, check=False).returncode


def _py(*args: str) -> int:
    return _run([_python(), *args])


# --------------------------------------------------------------------------- targets


def setup() -> int:
    venv = ROOT / ".venv"
    if not venv.exists():
        print("creating .venv ...")
        rc = subprocess.run([sys.executable, "-m", "venv", str(venv)], check=False).returncode
        if rc:
            return rc
    rc = _py("-m", "pip", "install", "--upgrade", "pip", "-q")
    if rc:
        return rc
    return _py("-m", "pip", "install", "-e", ".[app,dev]")


def setup_ai() -> int:
    print("installing torch + sentence-transformers (large download) ...")
    return _py("-m", "pip", "install", "-e", ".[ai]")


def acquire() -> int:
    return _py("scripts/acquire_data.py")


def audit() -> int:
    return _py("scripts/audit_data.py")


def clean() -> int:
    return _py("scripts/clean_data.py")


def splits() -> int:
    return _py("scripts/build_splits.py")


def embeddings() -> int:
    return _py("scripts/build_embeddings.py")


def validate() -> int:
    return _py("scripts/run_validation.py")


def final() -> int:
    return _py("scripts/run_final_evaluation.py")


def results_pack() -> int:
    return _py("scripts/build_results_pack.py")


def test() -> int:
    return _py("-m", "pytest", "-v")


def lint() -> int:
    return _py("-m", "ruff", "check", "src", "scripts", "tests", "app", "tasks.py")


def smoke() -> int:
    return _py("scripts/run_synthetic_smoke.py")


def demo() -> int:
    return _py("scripts/launch_demo.py")


def all_() -> int:
    for step in (audit, clean, splits, embeddings, validate, results_pack):
        rc = step()
        if rc:
            print(f"\nstopped: `{step.__name__}` exited with {rc}")
            return rc
    print(
        "\n`all` finished. It stopped before `final` on purpose: the final test set is "
        "used once, after the configuration is frozen."
    )
    return 0


TARGETS = {
    "setup": setup,
    "setup-ai": setup_ai,
    "acquire": acquire,
    "audit": audit,
    "clean": clean,
    "splits": splits,
    "embeddings": embeddings,
    "validate": validate,
    "final": final,
    "results-pack": results_pack,
    "test": test,
    "lint": lint,
    "smoke": smoke,
    "demo": demo,
    "all": all_,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    for name in argv:
        target = TARGETS.get(name)
        if target is None:
            print(f"unknown target {name!r}. Targets: {', '.join(TARGETS)}")
            return 2
        rc = target()
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
