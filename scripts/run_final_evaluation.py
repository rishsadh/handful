#!/usr/bin/env python
"""Final-stage evaluation. History = everything before 2018-01-01, labels = 2018 onward.

This runs **once**, under a frozen configuration. Two gates protect that:

1. `config/FROZEN.lock` must exist and its recorded config fingerprint must match the
   current configuration. Create it with `--freeze` once, deliberately, after validation
   is finished and the researcher has approved the protocol.
2. The test suite must pass. A final result produced by code with failing tests is not a
   result.

If a genuine software bug is found after the final run, fix it transparently, record why a
rerun was necessary in `docs/DECISION_LOG.md`, and let the new run take a new run id. Do
not overwrite the old one - a superseded result is evidence about the project's history.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from foodcom.pipeline import run_evaluation
from foodcom.utils import logging as flog
from foodcom.utils.config import load_configs
from foodcom.utils.hashing import sha256_obj

LOCK = "config/FROZEN.lock"


def _git_revision(root: Path) -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
        )
        return res.stdout.strip() or None
    except Exception:
        return None


def _freeze(cfg, lock_path: Path) -> int:
    if lock_path.exists():
        print(
            f"{LOCK} already exists. The configuration is already frozen.\n"
            "Changing it is a methodological change: record it in docs/DECISION_LOG.md, "
            "get approval, then delete the lock deliberately.",
            file=sys.stderr,
        )
        return 1
    payload = {
        "frozen_utc": dt.datetime.now(dt.UTC).isoformat(),
        "protocol_version": cfg.research.protocol_version,
        "config_sha256": sha256_obj(cfg.as_snapshot()),
        "code_revision": _git_revision(cfg.root),
        "note": (
            "The final test set may be used once under this configuration. Any change to "
            "config/ invalidates this lock."
        ),
    }
    lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Configuration frozen. {LOCK} written:\n{json.dumps(payload, indent=2)}")
    return 0


def _check_lock(cfg, lock_path: Path) -> int:
    if not lock_path.exists():
        print(
            f"Refusing to run the final evaluation: {LOCK} does not exist.\n\n"
            "The final test set is used once, under a frozen configuration. Finish "
            "validation, get the protocol approved, then run:\n\n"
            "    python scripts/run_final_evaluation.py --freeze\n",
            file=sys.stderr,
        )
        return 1
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    current = sha256_obj(cfg.as_snapshot())
    if lock["config_sha256"] != current:
        print(
            "Refusing to run the final evaluation: the configuration has changed since it "
            f"was frozen.\n  frozen:  {lock['config_sha256']}\n  current: {current}\n\n"
            "Either restore the frozen configuration, or record the change in "
            "docs/DECISION_LOG.md, obtain approval and re-freeze deliberately.",
            file=sys.stderr,
        )
        return 1
    print(f"Frozen configuration confirmed ({lock['config_sha256'][:12]}, "
          f"frozen {lock['frozen_utc']}).")
    return 0


def _run_tests(root: Path) -> int:
    print("running the test suite before the final evaluation ...")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=root, check=False
    )
    if res.returncode:
        print(
            "\nRefusing to run the final evaluation: tests are failing. Fix them first.",
            file=sys.stderr,
        )
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="write config/FROZEN.lock and exit")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip the pre-run test suite (record the reason in docs/DECISION_LOG.md)",
    )
    parser.add_argument("--no-sensitivity", action="store_true")
    args = parser.parse_args()

    flog.configure()
    cfg = load_configs()
    lock_path = cfg.root / LOCK

    if args.freeze:
        return _freeze(cfg, lock_path)
    rc = _check_lock(cfg, lock_path)
    if rc:
        return rc
    if not args.skip_tests:
        rc = _run_tests(cfg.root)
        if rc:
            return rc

    run_id = run_evaluation(stage="final", with_sensitivity=not args.no_sensitivity)
    print(f"\nFINAL evaluation complete: run {run_id}")
    print(f"Tables and figures: runs/{run_id}/")
    print("Next: python tasks.py results-pack")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
