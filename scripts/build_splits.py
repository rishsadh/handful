#!/usr/bin/env python
"""Temporal splits, cohort definitions and structural leakage checks."""

from __future__ import annotations

from foodcom.pipeline import run_splits
from foodcom.utils import logging as flog


def main() -> int:
    flog.configure()
    run_id = run_splits()
    print(f"\nSplits built: run {run_id}")
    print("Denominators: reports/split_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
