#!/usr/bin/env python
"""Validation-stage evaluation.

History = everything before 2017-01-01, labels = calendar 2017.

This is the stage where the protocol may still be tuned. Anything learned here must be
frozen before the final test set is touched.
"""

from __future__ import annotations

import argparse

from foodcom.pipeline import run_evaluation
from foodcom.utils import logging as flog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-users",
        type=int,
        default=None,
        help="evaluate at most this many users (a development convenience, not a protocol "
        "change; the run manifest records that a cap was applied)",
    )
    parser.add_argument(
        "--no-sensitivity", action="store_true", help="skip the predeclared sweeps"
    )
    args = parser.parse_args()

    flog.configure()
    run_id = run_evaluation(
        stage="validation",
        with_sensitivity=not args.no_sensitivity,
        max_users=args.max_users,
    )
    print(f"\nValidation complete: run {run_id}")
    print(f"Tables and figures: runs/{run_id}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
