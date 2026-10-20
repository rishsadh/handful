"""Expected schema of the two raw Food.com files, and safe parsing of their list columns.

The column lists here are the *expected* schema declared by the specification. They are
validated against the downloaded bytes; they are not an assertion that any bytes have
been inspected.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

RECIPE_COLUMNS: list[str] = [
    "name",
    "id",
    "minutes",
    "contributor_id",
    "submitted",
    "tags",
    "nutrition",
    "n_steps",
    "steps",
    "description",
    "ingredients",
    "n_ingredients",
]

INTERACTION_COLUMNS: list[str] = [
    "user_id",
    "recipe_id",
    "date",
    "rating",
    "review",
]

RECIPE_LIST_COLUMNS: list[str] = ["tags", "ingredients", "steps", "nutrition"]

# Reading `id` as a float loses precision on large ids and, worse, does it silently.
RECIPE_DTYPES: dict[str, str] = {
    "id": "Int64",
    "minutes": "Int64",
    "contributor_id": "Int64",
    "n_steps": "Int64",
    "n_ingredients": "Int64",
}

INTERACTION_DTYPES: dict[str, str] = {
    "user_id": "Int64",
    "recipe_id": "Int64",
    "rating": "Int64",
}

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class SchemaReport:
    """Outcome of validating a frame against an expected column list."""

    name: str
    observed_columns: list[str]
    expected_columns: list[str]
    missing: list[str]
    unexpected: list[str]
    dtypes: dict[str, str]
    row_count: int

    @property
    def ok(self) -> bool:
        return not self.missing

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "observed_columns": self.observed_columns,
            "expected_columns": self.expected_columns,
            "missing_columns": self.missing,
            "unexpected_columns": self.unexpected,
            "dtypes": self.dtypes,
            "schema_ok": self.ok,
        }


def validate_schema(frame: pd.DataFrame, expected: list[str], name: str) -> SchemaReport:
    observed = list(frame.columns)
    return SchemaReport(
        name=name,
        observed_columns=observed,
        expected_columns=list(expected),
        missing=[c for c in expected if c not in observed],
        unexpected=[c for c in observed if c not in expected],
        dtypes={c: str(frame[c].dtype) for c in observed},
        row_count=len(frame),
    )


# ------------------------------------------------------------------ safe list parsing


class ParseStatus:
    OK = "ok"
    EMPTY = "empty"
    NOT_A_LIST = "not_a_list"
    MALFORMED = "malformed"
    MISSING = "missing"


def parse_list_field(raw: Any) -> tuple[list[Any] | None, str]:
    """Parse a serialised Python list with `ast.literal_eval`.

    `literal_eval` evaluates literals only - no names, no calls, no attribute access - so
    a hostile cell cannot execute anything. Plain `eval` on 230k rows of third-party text
    would be a remote code execution surface, and is never used here.

    Returns `(value, status)`. A malformed cell yields `(None, status)` and is counted,
    never guessed at.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, ParseStatus.MISSING
    if isinstance(raw, (list, tuple)):
        value = list(raw)
        return (value, ParseStatus.OK if value else ParseStatus.EMPTY)
    if not isinstance(raw, str):
        return None, ParseStatus.NOT_A_LIST

    text = raw.strip()
    if not text:
        return None, ParseStatus.MISSING
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None, ParseStatus.MALFORMED
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return None, ParseStatus.NOT_A_LIST
    return (value, ParseStatus.OK if value else ParseStatus.EMPTY)


def normalise_whitespace(text: Any) -> str:
    """Collapse runs of whitespace and strip. Missing becomes an empty string."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return _WS.sub(" ", str(text)).strip()


def read_raw_recipes(path: str, nrows: int | None = None) -> pd.DataFrame:
    return pd.read_csv(path, dtype=RECIPE_DTYPES, nrows=nrows, keep_default_na=True)


def read_raw_interactions(path: str, nrows: int | None = None) -> pd.DataFrame:
    return pd.read_csv(path, dtype=INTERACTION_DTYPES, nrows=nrows, keep_default_na=True)
