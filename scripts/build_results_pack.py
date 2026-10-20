#!/usr/bin/env python
"""Build docs/RESULTS_PACK.md from a run directory.

With no `--run-id`, the most recent final run is used; if there is none, the most recent
validation run. Sections whose artifacts do not exist are marked PENDING rather than filled
with a plausible number.
"""

from __future__ import annotations

import argparse

from foodcom.pipeline import run_results_pack
from foodcom.utils import logging as flog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None, help="run directory name under runs/")
    args = parser.parse_args()

    flog.configure()
    path = run_results_pack(run_id=args.run_id)
    print(f"\nResults Pack written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
