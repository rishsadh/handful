"""Deterministic recipe text.

The encoder sees exactly one string per recipe, built in a fixed field order from a fixed
set of source fields:

    name | ingredients | whitelisted descriptive tags | short description

Nothing else. In particular: no review text, no user id, no rating, no popularity, no
review count, no timestamp, no contributor id, no administrative tag. Those are either
label-derived (which would leak the outcome) or identity-derived (which has no place in a
content representation). `assert_no_forbidden_fields` enforces this and a unit test calls
it, so the rule cannot quietly rot.

The rendered string is hashed. The hash is what keys the embedding cache and what proves,
after the fact, that a given vector came from a given text.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from foodcom.data.schema import normalise_whitespace
from foodcom.utils.config import ModelCfg, TagRules
from foodcom.utils.hashing import sha256_text


def as_list(value: Any) -> list[Any]:
    """Coerce a parsed list column to a plain list.

    A Parquet round-trip hands lists back as numpy arrays, and `if array or []` raises
    rather than being falsy. Normalising here keeps every caller from having to know that.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, float) and pd.isna(value):
        return []
    if hasattr(value, "tolist"):
        return list(value.tolist())
    if isinstance(value, tuple):
        return list(value)
    return []


def select_tags(tags: Any, rules: TagRules) -> list[str]:
    """Apply the fixed whitelist, preserving source order, capped at `max_tags_per_recipe`."""
    tags = as_list(tags)
    out: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        t = tag.strip().lower()
        if not t or t in seen:
            continue
        if rules.allowed(t):
            out.append(t)
            seen.add(t)
        if len(out) >= rules.max_tags_per_recipe:
            break
    return out


def render_recipe_text(row: Any, model: ModelCfg, rules: TagRules) -> str:
    """Build the encoder input for a single recipe row (a dict or a pandas Series)."""
    get = row.get if hasattr(row, "get") else (lambda k, d=None: getattr(row, k, d))
    tr = model.text_render

    parts: list[str] = []
    for field in tr.field_order:
        if field in tr.forbidden_fields:  # pragma: no cover - config validator blocks this
            raise ValueError(f"field {field!r} is forbidden in rendered recipe text")
        if field == "name":
            parts.append(normalise_whitespace(get("name", "")))
        elif field == "ingredients":
            items = as_list(get("ingredients", []))
            parts.append(", ".join(normalise_whitespace(i) for i in items if isinstance(i, str)))
        elif field == "tags":
            parts.append(", ".join(select_tags(get("tags", []), rules)))
        elif field == "description":
            desc = normalise_whitespace(get("description", ""))
            if tr.description_max_chars and len(desc) > tr.description_max_chars:
                desc = desc[: tr.description_max_chars].rstrip()
            parts.append(desc)
        else:
            raise ValueError(f"no renderer for text field {field!r}")

    text = tr.separator.join(p for p in parts if p)
    return text.lower() if tr.lowercase else text


def render_catalogue(recipes: pd.DataFrame, model: ModelCfg, rules: TagRules) -> pd.DataFrame:
    """Render every recipe and hash it. Returns `recipe_id, text, text_sha256, n_chars`."""
    texts = [render_recipe_text(row, model, rules) for row in recipes.to_dict("records")]
    return pd.DataFrame(
        {
            "recipe_id": recipes["id"].astype("int64").to_numpy(),
            "text": texts,
            "text_sha256": [sha256_text(t) for t in texts],
            "n_chars": [len(t) for t in texts],
        }
    )


def assert_no_forbidden_fields(model: ModelCfg) -> None:
    """Fail loudly if the render configuration would admit a forbidden field."""
    overlap = set(model.text_render.field_order) & set(model.text_render.forbidden_fields)
    if overlap:
        raise AssertionError(f"rendered recipe text would include forbidden fields: {overlap}")


def truncation_report(
    rendered: pd.DataFrame, tokeniser: Any | None, max_seq_length: int
) -> dict[str, Any]:
    """Fraction of rendered texts that exceed the encoder's input limit.

    Without a tokeniser this reports `None` rather than guessing: a wordpiece count is not
    a character count, and a fabricated truncation rate is worse than an absent one.
    """
    if tokeniser is None:
        return {
            "max_seq_length": max_seq_length,
            "measured": False,
            "note": "tokeniser unavailable; truncation fraction not measured",
        }
    lengths = [len(tokeniser.tokenize(t)) for t in rendered["text"].tolist()]
    over = sum(1 for n in lengths if n + 2 > max_seq_length)  # +2 for [CLS]/[SEP]
    return {
        "max_seq_length": max_seq_length,
        "measured": True,
        "n_texts": len(lengths),
        "n_truncated": over,
        "fraction_truncated": round(over / max(len(lengths), 1), 6),
        "mean_wordpieces": round(sum(lengths) / max(len(lengths), 1), 3),
        "max_wordpieces": max(lengths) if lengths else 0,
    }
