#!/usr/bin/env python
"""Cleaning, quarantine and the ordered exclusion ledger."""

from __future__ import annotations

import sys

from foodcom.data.acquire import AcquisitionError
from foodcom.pipeline import run_clean
from foodcom.utils import logging as flog


def main() -> int:
    flog.configure()
    try:
        run_id = run_clean()
    except AcquisitionError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1
    print(f"\nCleaning complete: run {run_id}")
    print("Ledger: data/processed/exclusion_ledger.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
