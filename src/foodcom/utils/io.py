"""Reading and writing project tables.

Processed tables are Parquet: it preserves int64 recipe ids and datetimes without the
round-trip through text that turns `id` into a float and silently corrupts the primary
key. CSV is used only for human-readable exports.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_parquet(frame: pd.DataFrame, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(p, index=False)
    return p


def read_parquet(path: Path | str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing. Run the pipeline stage that produces it "
            f"(see `python tasks.py --help`)."
        )
    return pd.read_parquet(p)


def write_csv(frame: pd.DataFrame, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(p, index=False, encoding="utf-8")
    return p


def exists(path: Path | str) -> bool:
    return Path(path).exists()
