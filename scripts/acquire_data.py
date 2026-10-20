#!/usr/bin/env python
"""Data gate: record provenance, hash the raw files, probe the schema.

Downloads nothing. Kaggle needs the user's own authenticated session, and an unofficial
mirror is not a substitute for the selected release.
"""

from __future__ import annotations

import sys

from foodcom.data.acquire import AcquisitionError
from foodcom.pipeline import run_acquire
from foodcom.utils import logging as flog


def main() -> int:
    flog.configure()
    try:
        result = run_acquire()
    except AcquisitionError as exc:
        print(f"\nDATA GATE NOT PASSED\n\n{exc}\n", file=sys.stderr)
        return 1
    print(f"\nData gate passed. Manifest: {result['source_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
