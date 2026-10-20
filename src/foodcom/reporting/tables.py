"""Research-ready tables.

Ten tables are required by the specification. Most are produced directly by the pipeline
stages; this module assembles the ones that need composing, and renders any DataFrame as
GitHub-flavoured Markdown so the Results Pack reads without a spreadsheet.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

REQUIRED_TABLES = [
    ("t01_raw_dataset_audit", "Raw dataset audit"),
    ("t02_cleaning_exclusion_ledger", "Cleaning and exclusion ledger"),
    ("t03_split_and_eligibility", "Temporal split and user eligibility"),
    ("t04_method_comparison", "Final method comparison"),
    ("t05_paired_differences", "Paired differences and bootstrap intervals"),
    ("t06_sensitivity_length", "Shortlist-length sensitivity"),
    ("t07_sensitivity_cap", "Band-cap sensitivity"),
    ("t08_feasibility_and_failures", "Feasibility and failure summary"),
    ("t09_worked_lpp_example", "Worked LPP example"),
    ("t10_primal_dual_verification", "Primal-dual verification"),
]


def to_markdown(frame: pd.DataFrame, max_rows: int = 60, float_fmt: str = "{:.4f}") -> str:
    """Render a DataFrame as a Markdown table, truncating politely rather than silently."""
    if frame is None or frame.empty:
        return "_(no rows)_"

    def _cell(value: Any) -> str:
        # A pipe inside a value would silently split the Markdown row.
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        if isinstance(value, float):
            return float_fmt.format(value)
        return str(value).replace("|", "\\|").replace("\n", " ")

    shown = frame.head(max_rows)
    header = "| " + " | ".join(str(c) for c in shown.columns) + " |"
    sep = "| " + " | ".join("---" for _ in shown.columns) + " |"
    body = "\n".join(
        "| " + " | ".join(_cell(v) for v in row) + " |"
        for row in shown.itertuples(index=False, name=None)
    )
    out = "\n".join([header, sep, body])
    if len(frame) > max_rows:
        out += f"\n\n_({len(frame) - max_rows} further rows in the accompanying CSV.)_"
    return out


def audit_summary_table(summary: dict[str, Any]) -> pd.DataFrame:
    """Table 1: the headline facts about what was actually downloaded."""
    rec = summary.get("recipes", {})
    inter = summary.get("interactions", {})
    rows = [
        ("recipes: raw rows", rec.get("n_rows")),
        ("recipes: unique ids", rec.get("n_unique_recipe_ids")),
        ("recipes: exact duplicate rows", rec.get("n_exact_duplicate_rows")),
        ("recipes: conflicting ids", rec.get("n_conflicting_recipe_ids")),
        ("recipes: submitted date range",
         f"{rec.get('submitted', {}).get('min')} .. {rec.get('submitted', {}).get('max')}"),
        ("recipes: non-positive minutes", rec.get("minutes", {}).get("n_non_positive")),
        ("recipes: missing/blank description",
         rec.get("description", {}).get("pct_missing_or_blank")),
        ("interactions: raw rows", inter.get("n_rows")),
        ("interactions: unique users", inter.get("n_unique_users")),
        ("interactions: unique recipe ids", inter.get("n_unique_recipe_ids")),
        ("interactions: exact duplicate rows", inter.get("n_exact_duplicate_rows")),
        ("interactions: repeated user-recipe pairs",
         inter.get("n_repeated_user_recipe_pairs")),
        ("interactions: date range",
         f"{inter.get('date', {}).get('min')} .. {inter.get('date', {}).get('max')}"),
        ("interactions: rating 0 (unknown)", inter.get("rating", {}).get("n_zero")),
        ("interactions: positive (4-5)", inter.get("rating", {}).get("n_positive")),
        ("interactions: observed non-positive (1-3)",
         inter.get("rating", {}).get("n_observed_nonpositive")),
        ("interactions: orphan recipe joins", inter.get("join", {}).get("n_orphan_interactions")),
        ("interactions: dated before submission",
         inter.get("temporal_consistency", {}).get("n_interactions_before_submission")),
        ("recipe id is a unique key", inter.get("join", {}).get("recipe_id_is_unique_key")),
    ]
    return pd.DataFrame(rows, columns=["quantity", "value"])


def worked_example_table(
    solution_dict: dict[str, Any], catalogue: pd.DataFrame, scores: dict[int, float]
) -> pd.DataFrame:
    """Table 9: one real shortlist with the full score and constraint trace."""
    rows = []
    lookup = catalogue.set_index("id")
    for rank, rid in enumerate(solution_dict["ranked_recipe_ids"], start=1):
        row = lookup.loc[int(rid)]
        rows.append(
            {
                "rank": rank,
                "recipe_id": int(rid),
                "name": row["name"],
                "reported_minutes": int(row["minutes"]),
                "band": str(row["band"]),
                "ai_relevance_score": float(scores.get(int(rid), float("nan"))),
                "selection_variable_x": 1.0,
            }
        )
    return pd.DataFrame(rows)


def duality_table(duality: dict[str, Any], band_labels: list[str], dual: dict[str, Any]) -> (
    pd.DataFrame
):
    """Table 10: the primal-dual verification, in one readable block."""
    rows = [
        {"quantity": "primal objective (max total relevance score)",
         "value": duality["primal_objective"]},
        {"quantity": "dual objective (min k*alpha + sum b_g*beta_g + sum gamma_i)",
         "value": duality["dual_objective"]},
        {"quantity": "duality gap |primal - dual|", "value": duality["duality_gap"]},
        {"quantity": "strong duality holds within tolerance",
         "value": duality["strong_duality_holds"]},
        {"quantity": "max dual constraint violation",
         "value": duality["max_dual_constraint_violation"]},
        {"quantity": "alpha (shadow value of the exact-size constraint)", "value": dual["alpha"]},
    ]
    for label, beta in zip(band_labels, dual["beta"], strict=True):
        rows.append({"quantity": f"beta[{label}] (shadow value of the band cap)", "value": beta})
    rows.extend(
        [
            {"quantity": "gamma: number of binding upper bounds",
             "value": dual["gamma_nonzero_count"]},
            {"quantity": "complementary slackness: max beta x cap slack",
             "value": duality["complementary_slackness"]["max_beta_times_cap_slack"]},
            {"quantity": "complementary slackness: max gamma x (1 - x)",
             "value": duality["complementary_slackness"]["max_gamma_times_one_minus_x"]},
            {"quantity": "complementary slackness: max x x dual slack",
             "value": duality["complementary_slackness"][
                 "max_x_times_dual_constraint_slack"]},
            {"quantity": "tolerance", "value": duality["tolerance"]},
            {"quantity": "all checks passed", "value": duality["checks_passed"]},
        ]
    )
    return pd.DataFrame(rows)


def feasibility_table(results: pd.DataFrame) -> pd.DataFrame:
    """Table 8: feasibility, exact-size success and failure rate per method."""
    if results.empty:
        return pd.DataFrame()
    rows = []
    for (stage, method, k, cap), grp in results.groupby(
        ["stage", "method", "k", "cap"], dropna=False
    ):
        rows.append(
            {
                "stage": stage,
                "method": method,
                "k": int(k),
                "cap": int(cap),
                "n_users": len(grp),
                "n_feasible": int(grp["feasible"].astype(bool).sum()),
                "pct_feasible": float(100.0 * grp["feasible"].astype(bool).mean()),
                "n_exact_size_ok": int(grp["exact_size_ok"].astype(bool).sum()),
                "pct_exact_size_ok": float(100.0 * grp["exact_size_ok"].astype(bool).mean()),
                "n_failed_on_feasible_input": int(
                    ((grp["failed"].astype(float) > 0) & grp["feasible"].astype(bool)).sum()
                ),
                "failure_rate_pct": float(100.0 * (grp["failed"].astype(float) > 0).mean()),
                "mean_cap_violations": float(grp["cap_violations"].mean()),
                "note": (
                    "cap violations are expected for AI_TOPK by design"
                    if method == "AI_TOPK"
                    else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def split_table(denominators: dict[str, Any]) -> pd.DataFrame:
    """Table 3: split boundaries and every cohort denominator."""
    return pd.DataFrame(
        [{"quantity": k, "value": v} for k, v in denominators.items()]
    )


def format_ci(row: pd.Series) -> str:
    if not np.isfinite(row.get("ci_low", np.nan)):
        return "n/a"
    return f"{row['mean_absolute_difference']:+.4f} [{row['ci_low']:+.4f}, {row['ci_high']:+.4f}]"
