#!/usr/bin/env python
"""Full audit of the raw files. Reports; never modifies."""

from __future__ import annotations

import sys

from foodcom.data.acquire import AcquisitionError
from foodcom.pipeline import run_audit
from foodcom.utils import logging as flog


def main() -> int:
    flog.configure()
    try:
        run_id = run_audit()
    except AcquisitionError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1
    print(f"\nAudit complete: run {run_id}")
    print("Read docs/DATA_AUDIT.md, then confirm the temporal windows are workable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
