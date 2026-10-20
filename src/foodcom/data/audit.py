"""Raw data audit.

Everything here reads the raw frames and reports. Nothing is modified, dropped or
repaired: the audit's job is to establish what we actually downloaded, so that the
cleaning rules applied afterwards can be justified against evidence rather than habit.

Outputs: a machine-readable JSON blob, a set of CSV tables, and `docs/DATA_AUDIT.md`.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from foodcom.data.schema import (
    INTERACTION_COLUMNS,
    RECIPE_COLUMNS,
    RECIPE_LIST_COLUMNS,
    ParseStatus,
    parse_list_field,
    validate_schema,
)
from foodcom.models.bands import band_counts
from foodcom.utils import logging as flog
from foodcom.utils.config import Configs

log = flog.get_logger(__name__)

# Recipe fields whose disagreement across rows sharing one id makes the id "conflicting".
_IDENTITY_FIELDS = ["name", "minutes", "submitted", "ingredients", "steps"]


def _missingness(frame: pd.DataFrame) -> pd.DataFrame:
    n = len(frame)
    rows = []
    for col in frame.columns:
        n_missing = int(frame[col].isna().sum())
        blank = 0
        if frame[col].dtype == object:
            blank = int(
                frame[col].map(lambda v: isinstance(v, str) and v.strip() == "").sum()
            )
        rows.append(
            {
                "column": col,
                "dtype": str(frame[col].dtype),
                "n_missing": n_missing,
                "pct_missing": round(100.0 * n_missing / n, 4) if n else 0.0,
                "n_blank_string": blank,
            }
        )
    return pd.DataFrame(rows)


def _numeric_summary(series: pd.Series) -> dict[str, Any]:
    s = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if s.empty:
        return {"n": 0}
    q = s.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999]).to_dict()
    return {
        "n": int(s.size),
        "min": float(s.min()),
        "max": float(s.max()),
        "mean": float(s.mean()),
        "std": float(s.std(ddof=1)) if s.size > 1 else 0.0,
        "quantiles": {f"p{int(k * 1000) / 10:g}": float(v) for k, v in q.items()},
        "n_zero": int((s == 0).sum()),
        "n_negative": int((s < 0).sum()),
        "n_non_finite": int((~np.isfinite(s)).sum()),
    }


def _parse_dates(series: pd.Series) -> tuple[pd.Series, int]:
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    invalid = int(parsed.isna().sum() - series.isna().sum())
    return parsed, max(invalid, 0)


# --------------------------------------------------------------------------- recipes


def audit_recipes(recipes: pd.DataFrame, cfg: Configs) -> dict[str, Any]:
    protocol = cfg.research.protocol
    out: dict[str, Any] = {}
    tables: dict[str, pd.DataFrame] = {}

    schema = validate_schema(recipes, RECIPE_COLUMNS, "RAW_recipes.csv")
    out["schema"] = schema.as_dict()

    out["n_rows"] = len(recipes)
    out["n_exact_duplicate_rows"] = int(recipes.duplicated(keep="first").sum())

    if "id" in recipes:
        ids = recipes["id"]
        out["n_unique_recipe_ids"] = int(ids.nunique(dropna=True))
        out["n_missing_recipe_ids"] = int(ids.isna().sum())
        dup_ids = ids[ids.duplicated(keep=False) & ids.notna()]
        out["n_rows_with_duplicated_id"] = int(dup_ids.size)
        out["n_duplicated_ids"] = int(dup_ids.nunique())
        # Ids that appear more than once AND disagree on an identity field.
        conflicting = []
        if out["n_duplicated_ids"]:
            fields = [f for f in _IDENTITY_FIELDS if f in recipes.columns]
            sub = recipes[recipes["id"].isin(dup_ids.unique())][["id", *fields]]
            sub = sub.astype(dict.fromkeys(fields, "string"))
            for rid, grp in sub.groupby("id", dropna=True):
                if grp.drop(columns=["id"]).drop_duplicates().shape[0] > 1:
                    conflicting.append(int(rid))
        out["n_conflicting_recipe_ids"] = len(conflicting)
        out["conflicting_recipe_ids_sample"] = conflicting[:50]

    if "submitted" in recipes:
        submitted, n_invalid = _parse_dates(recipes["submitted"])
        out["submitted"] = {
            "n_invalid_dates": n_invalid,
            "min": str(submitted.min()) if submitted.notna().any() else None,
            "max": str(submitted.max()) if submitted.notna().any() else None,
        }
        by_year = submitted.dt.year.value_counts().sort_index()
        tables["recipes_by_submitted_year"] = by_year.rename_axis("year").reset_index(
            name="n_recipes"
        )

    if "minutes" in recipes:
        out["minutes"] = _numeric_summary(recipes["minutes"])
        m = pd.to_numeric(recipes["minutes"], errors="coerce")
        out["minutes"]["n_non_positive"] = int((m <= 0).sum())
        out["minutes"]["n_missing"] = int(m.isna().sum())
        flag_above = cfg.cleaning.recipes["minutes"].get("flag_above_minutes")
        if flag_above is not None:
            out["minutes"]["n_flagged_above_threshold"] = int((m > float(flag_above)).sum())
            out["minutes"]["flag_threshold"] = float(flag_above)
        tables["recipe_minutes_bands"] = band_counts(recipes["minutes"], protocol)
        # Boundary values matter: an off-by-one at 15/30/60 silently reshuffles the bands.
        out["minutes"]["boundary_counts"] = {
            str(edge): int((m == edge).sum()) for edge in protocol.band_edges
        }
        hist_bins = [0, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 360, 720, 1440, np.inf]
        hist = pd.cut(m.dropna().astype(float), bins=hist_bins, right=True)
        tables["recipe_minutes_histogram"] = (
            hist.value_counts().sort_index().rename_axis("minutes_bin").reset_index(
                name="n_recipes"
            ).astype({"minutes_bin": str})
        )

    # --- list fields ---
    parse_rows = []
    tag_counter: Counter[str] = Counter()
    nutrition_len_counter: Counter[int] = Counter()
    for col in RECIPE_LIST_COLUMNS:
        if col not in recipes:
            continue
        statuses: Counter[str] = Counter()
        lengths: list[int] = []
        for raw in recipes[col]:
            value, status = parse_list_field(raw)
            statuses[status] += 1
            if value is not None:
                lengths.append(len(value))
                if col == "tags":
                    for t in value:
                        if isinstance(t, str):
                            tag_counter[t.strip().lower()] += 1
                if col == "nutrition":
                    nutrition_len_counter[len(value)] += 1
        parse_rows.append(
            {
                "column": col,
                "n_ok": statuses[ParseStatus.OK],
                "n_empty": statuses[ParseStatus.EMPTY],
                "n_missing": statuses[ParseStatus.MISSING],
                "n_not_a_list": statuses[ParseStatus.NOT_A_LIST],
                "n_malformed": statuses[ParseStatus.MALFORMED],
                "mean_length": round(float(np.mean(lengths)), 4) if lengths else 0.0,
                "max_length": int(max(lengths)) if lengths else 0,
            }
        )
    tables["recipe_list_field_parsing"] = pd.DataFrame(parse_rows)
    out["list_field_parsing"] = parse_rows

    if tag_counter:
        tag_tbl = pd.DataFrame(
            sorted(tag_counter.items(), key=lambda kv: (-kv[1], kv[0])),
            columns=["tag", "n_recipes"],
        )
        tag_tbl["whitelisted"] = tag_tbl["tag"].map(cfg.tags.allowed)
        tables["tag_vocabulary"] = tag_tbl
        out["tags"] = {
            "n_distinct_tags": len(tag_counter),
            "n_whitelisted_tags": int(tag_tbl["whitelisted"].sum()),
            "pct_tag_occurrences_whitelisted": round(
                100.0
                * tag_tbl.loc[tag_tbl["whitelisted"], "n_recipes"].sum()
                / max(tag_tbl["n_recipes"].sum(), 1),
                3,
            ),
        }

    if nutrition_len_counter:
        expected = int(cfg.cleaning.recipes["nutrition"]["expected_length"])
        out["nutrition"] = {
            "expected_length": expected,
            "length_counts": {str(k): int(v) for k, v in sorted(nutrition_len_counter.items())},
            "n_unexpected_length": int(
                sum(v for k, v in nutrition_len_counter.items() if k != expected)
            ),
            "units_verified": bool(cfg.cleaning.recipes["nutrition"]["units_verified"]),
            "note": (
                "Commonly documented as calories plus six percentage-daily-value fields, "
                "not seven gram quantities. Units remain unverified against this release "
                "and nutrition is not used in the core LP."
            ),
        }

    # --- derived count agreement ---
    checks = []
    for spec in cfg.cleaning.recipes.get("derived_count_checks", []):
        src, parsed_col = spec["source"], spec["parsed"]
        if src not in recipes or parsed_col not in recipes:
            continue
        parsed_len = recipes[parsed_col].map(lambda r: (parse_list_field(r)[0] or []).__len__())
        src_vals = pd.to_numeric(recipes[src], errors="coerce")
        mismatch = int((src_vals != parsed_len).sum())
        checks.append(
            {
                "source_column": src,
                "parsed_column": parsed_col,
                "n_mismatch": mismatch,
                "pct_mismatch": round(100.0 * mismatch / max(len(recipes), 1), 4),
            }
        )
    out["derived_count_checks"] = checks
    if checks:
        tables["recipe_derived_count_checks"] = pd.DataFrame(checks)

    if "description" in recipes:
        desc = recipes["description"]
        out["description"] = {
            "n_missing": int(desc.isna().sum()),
            "n_blank": int(desc.map(lambda v: isinstance(v, str) and not v.strip()).sum()),
            "pct_missing_or_blank": round(
                100.0
                * (
                    desc.isna().sum()
                    + desc.map(lambda v: isinstance(v, str) and not v.strip()).sum()
                )
                / max(len(recipes), 1),
                4,
            ),
        }

    tables["recipes_missingness"] = _missingness(recipes)
    return {"summary": out, "tables": tables}


# ---------------------------------------------------------------------- interactions


def audit_interactions(
    interactions: pd.DataFrame, recipes: pd.DataFrame, cfg: Configs
) -> dict[str, Any]:
    protocol = cfg.research.protocol
    out: dict[str, Any] = {}
    tables: dict[str, pd.DataFrame] = {}

    schema = validate_schema(interactions, INTERACTION_COLUMNS, "RAW_interactions.csv")
    out["schema"] = schema.as_dict()

    out["n_rows"] = len(interactions)
    out["n_exact_duplicate_rows"] = int(interactions.duplicated(keep="first").sum())

    if "user_id" in interactions:
        out["n_unique_users"] = int(interactions["user_id"].nunique(dropna=True))
        out["n_missing_user_ids"] = int(interactions["user_id"].isna().sum())
    if "recipe_id" in interactions:
        out["n_unique_recipe_ids"] = int(interactions["recipe_id"].nunique(dropna=True))
        out["n_missing_recipe_ids"] = int(interactions["recipe_id"].isna().sum())

    # --- repeated user-recipe pairs ---
    if {"user_id", "recipe_id"} <= set(interactions.columns):
        pair_counts = interactions.groupby(["user_id", "recipe_id"], dropna=True).size()
        repeated = pair_counts[pair_counts > 1]
        out["n_user_recipe_pairs"] = int(pair_counts.size)
        out["n_repeated_user_recipe_pairs"] = int(repeated.size)
        out["n_rows_in_repeated_pairs"] = int(repeated.sum())
        tables["repeated_pair_multiplicity"] = (
            repeated.value_counts().sort_index().rename_axis("events_per_pair").reset_index(
                name="n_pairs"
            )
        )

    # --- dates ---
    if "date" in interactions:
        parsed, n_invalid = _parse_dates(interactions["date"])
        out["date"] = {
            "n_invalid_dates": n_invalid,
            "n_missing": int(interactions["date"].isna().sum()),
            "min": str(parsed.min()) if parsed.notna().any() else None,
            "max": str(parsed.max()) if parsed.notna().any() else None,
        }
        by_year = parsed.dt.year.value_counts().sort_index()
        tables["interactions_by_year"] = by_year.rename_axis("year").reset_index(
            name="n_interactions"
        )
        # Coverage of the locked windows is the reason this audit exists.
        windows = {}
        for stage, w in protocol.stages.items():
            hist_end = pd.Timestamp(w.history_end_exclusive)
            lab_start = pd.Timestamp(w.label_start)
            lab_end = (
                pd.Timestamp(w.label_end_inclusive)
                if w.label_end_inclusive is not None
                else parsed.max()
            )
            windows[stage] = {
                "history_end_exclusive": str(w.history_end_exclusive),
                "label_start": str(w.label_start),
                "label_end_inclusive": str(lab_end.date()) if pd.notna(lab_end) else None,
                "n_history_events": int((parsed < hist_end).sum()),
                "n_label_events": int(((parsed >= lab_start) & (parsed <= lab_end)).sum()),
            }
        out["window_coverage"] = windows

    # --- ratings ---
    if "rating" in interactions:
        r = pd.to_numeric(interactions["rating"], errors="coerce")
        dist = r.value_counts(dropna=False).sort_index()
        tables["rating_distribution"] = (
            dist.rename_axis("rating").reset_index(name="n_interactions").astype({"rating": str})
        )
        valid = set(cfg.cleaning.interactions["rating"]["valid_explicit"])
        unknown = cfg.cleaning.interactions["rating"]["unknown_value"]
        out["rating"] = {
            "distribution": {str(k): int(v) for k, v in dist.items()},
            "n_missing": int(r.isna().sum()),
            "n_zero": int((r == unknown).sum()),
            "n_positive": int(r.isin(protocol.positive_ratings).sum()),
            "n_observed_nonpositive": int(r.isin(protocol.observed_nonpositive_ratings).sum()),
            "n_out_of_range": int((~r.isin(valid | {unknown})).sum() - r.isna().sum()),
            "zero_meaning": (
                "unknown / unrated. Never treated as a zero-star dislike, and never "
                "inferred as positive from review text."
            ),
        }

    # --- join coverage ---
    if "recipe_id" in interactions and "id" in recipes:
        recipe_ids = set(recipes["id"].dropna().astype("int64").tolist())
        inter_ids = interactions["recipe_id"].dropna().astype("int64")
        known = inter_ids.isin(recipe_ids)
        out["join"] = {
            "n_interactions_with_known_recipe": int(known.sum()),
            "n_orphan_interactions": int((~known).sum()),
            "pct_orphan_interactions": round(
                100.0 * (~known).sum() / max(inter_ids.size, 1), 4
            ),
            "n_orphan_recipe_ids": int(inter_ids[~known].nunique()),
            "n_recipes_with_no_interaction": len(recipe_ids - set(inter_ids.unique().tolist())),
            "recipe_id_is_unique_key": bool(
                recipes["id"].dropna().is_unique
            ),
            "join_is_many_to_one": bool(recipes["id"].dropna().is_unique),
        }

    # --- interaction before recipe submission ---
    if {"recipe_id", "date"} <= set(interactions.columns) and {"id", "submitted"} <= set(
        recipes.columns
    ):
        sub = recipes[["id", "submitted"]].dropna(subset=["id"]).drop_duplicates("id")
        sub = sub.assign(submitted=pd.to_datetime(sub["submitted"], errors="coerce"))
        merged = interactions[["recipe_id", "date"]].merge(
            sub, left_on="recipe_id", right_on="id", how="left"
        )
        idate = pd.to_datetime(merged["date"], errors="coerce")
        before = (idate < merged["submitted"]) & idate.notna() & merged["submitted"].notna()
        out["temporal_consistency"] = {
            "n_interactions_before_submission": int(before.sum()),
            "pct_interactions_before_submission": round(
                100.0 * before.sum() / max(len(interactions), 1), 4
            ),
        }

    # --- usable positive history per user ---
    if {"user_id", "recipe_id", "rating"} <= set(interactions.columns):
        r = pd.to_numeric(interactions["rating"], errors="coerce")
        pos = interactions[r.isin(protocol.positive_ratings)]
        per_user = pos.groupby("user_id")["recipe_id"].nunique()
        tables["user_positive_history_sizes"] = (
            per_user.value_counts().sort_index().rename_axis("n_distinct_positive_recipes")
            .reset_index(name="n_users")
        )
        thresholds = sorted({1, 3, 5, 10, 20, protocol.min_distinct_positive_history})
        out["user_history"] = {
            "n_users_with_any_positive": int(per_user.size),
            "users_at_or_above_threshold": {
                str(t): int((per_user >= t).sum()) for t in thresholds
            },
            "protocol_threshold": protocol.min_distinct_positive_history,
            "note": (
                "Counted over ALL dates here. The eligible cohort is defined from history "
                "only, at each stage cutoff, in splits.py."
            ),
        }

    tables["interactions_missingness"] = _missingness(
        interactions.drop(columns=["review"], errors="ignore")
    )
    if "review" in interactions:
        rev = interactions["review"]
        out["review_text"] = {
            "n_missing": int(rev.isna().sum()),
            "handling": (
                "Retained locally where permitted. Never a feature, never rendered in the "
                "demo, never committed to git."
            ),
        }
    return {"summary": out, "tables": tables}


# --------------------------------------------------------------------------- combined


def run_audit(recipes: pd.DataFrame, interactions: pd.DataFrame, cfg: Configs) -> dict[str, Any]:
    log.info("auditing %d recipe rows and %d interaction rows", len(recipes), len(interactions))
    rec = audit_recipes(recipes, cfg)
    inter = audit_interactions(interactions, recipes, cfg)
    summary = {
        "audited_utc": dt.datetime.now(dt.UTC).isoformat(),
        "protocol_version": cfg.research.protocol_version,
        "recipes": rec["summary"],
        "interactions": inter["summary"],
    }
    tables = {f"recipes__{k}": v for k, v in rec["tables"].items()}
    tables.update({f"interactions__{k}": v for k, v in inter["tables"].items()})
    return {"summary": summary, "tables": tables}


def coverage_verdict(summary: dict[str, Any], cfg: Configs) -> dict[str, Any]:
    """Is the locked temporal protocol workable against these bytes?

    This produces a verdict, not a change. If coverage is insufficient the specification
    requires a diagnosed, recorded and approved replacement window - never a silent one.
    """
    windows = summary.get("interactions", {}).get("window_coverage", {})
    problems = []
    for stage, w in windows.items():
        if w["n_history_events"] == 0:
            problems.append(f"{stage}: no events before {w['history_end_exclusive']}")
        if w["n_label_events"] == 0:
            problems.append(
                f"{stage}: no events in {w['label_start']}..{w['label_end_inclusive']}"
            )
    return {
        "windows": windows,
        "problems": problems,
        "workable": not problems,
        "action_if_unworkable": (
            "Do not silently change the dates. Diagnose from this audit, propose a "
            "replacement window in docs/DECISION_LOG.md, obtain approval, then freeze it "
            "before any final-test run."
        ),
    }
