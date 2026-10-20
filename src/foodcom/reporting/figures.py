"""Figures.

Every figure carries a title, explicit units, a caption, the run id that produced it and
the CSV its bars were drawn from. A figure whose numbers cannot be traced back to a run is
not usable in a paper, and captions never assert causation - "AI_LP retrieved more later
positives" is a description; "AI_LP reduced choice overload" is not something this study
measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: figures are files, never windows
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "figure.figsize": (8.0, 5.0),
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "600",
    }
)

_INK = "#111418"
_ACCENT = "#2563eb"
_MUTED = "#94a3b8"

# One colour and dash per method, held constant across every figure. AI_LP and AI_TOPK are
# deliberately not both blue: they differ only in whether the caps apply, and a reader
# comparing two similar blue lines is the exact confusion these figures exist to avoid.
_METHOD_COLOUR = {
    "AI_LP": _ACCENT,
    "AI_TOPK": "#111418",
    "POPULARITY_LP": "#d97706",
    "RANDOM": "#94a3b8",
    "TFIDF_LP": "#7c3aed",
}
_METHOD_STYLE = {
    "AI_LP": "-",
    "AI_TOPK": "--",
    "POPULARITY_LP": "-.",
    "RANDOM": ":",
    "TFIDF_LP": "--",
}


@dataclass
class FigureArtifact:
    name: str
    png_path: Path
    csv_path: Path
    caption: str
    run_id: str
    units: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "png": str(self.png_path),
            "underlying_csv": str(self.csv_path),
            "caption": self.caption,
            "run_id": self.run_id,
            "units": self.units,
        }


def _finish(
    fig: plt.Figure,
    *,
    name: str,
    data: pd.DataFrame,
    caption: str,
    units: str,
    run_id: str,
    out_dir: Path,
) -> FigureArtifact:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{name}.png"
    csv = out_dir / f"{name}.csv"
    fig.text(
        0.01,
        0.01,
        f"run {run_id}  ·  data: {csv.name}",
        fontsize=6.5,
        color=_MUTED,
        va="bottom",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)
    data.to_csv(csv, index=False, encoding="utf-8")
    return FigureArtifact(
        name=name, png_path=png, csv_path=csv, caption=caption, run_id=run_id, units=units
    )


# ------------------------------------------------------------------ descriptive figures


def fig_rating_distribution(
    table: pd.DataFrame, out_dir: Path, run_id: str
) -> FigureArtifact:
    """`table`: columns `rating`, `n_interactions` (from the audit)."""
    fig, ax = plt.subplots()
    colours = [
        _MUTED if str(r) in ("0", "0.0", "nan") else _ACCENT for r in table["rating"]
    ]
    ax.bar(table["rating"].astype(str), table["n_interactions"], color=colours)
    ax.set_title("Distribution of ratings in the cleaned interaction table")
    ax.set_xlabel("rating (0 = unknown / unrated, shown in grey)")
    ax.set_ylabel("number of interactions (count)")
    return _finish(
        fig,
        name="fig01_rating_distribution",
        data=table,
        units="counts of interaction events",
        caption=(
            "Rating distribution after cleaning. Rating 0 denotes an unrated interaction, "
            "not a zero-star dislike, and is excluded from the positive definition "
            "(positive = 4 or 5). Counts are events, not users."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


def fig_minutes_distribution(table: pd.DataFrame, out_dir: Path, run_id: str) -> FigureArtifact:
    """`table`: columns `minutes_bin`, `n_recipes`."""
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(table["minutes_bin"].astype(str), table["n_recipes"], color=_ACCENT)
    ax.set_title("Distribution of reported preparation time")
    ax.set_xlabel("reported minutes (binned, upper-inclusive)")
    ax.set_ylabel("number of recipes (count)")
    ax.tick_params(axis="x", rotation=45)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
    return _finish(
        fig,
        name="fig02_minutes_distribution",
        data=table,
        units="counts of recipes; x axis in minutes",
        caption=(
            "Reported preparation time for recipes in the cleaned catalogue. These are the "
            "durations recorded by recipe contributors, not measured cooking times. Long "
            "durations are retained: marinating and slow cooking are legitimate."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


def fig_band_composition(table: pd.DataFrame, out_dir: Path, run_id: str) -> FigureArtifact:
    """`table`: columns `band`, `n_recipes`."""
    data = table[table["band"] != "unassigned_invalid_minutes"]
    fig, ax = plt.subplots()
    ax.bar(data["band"], data["n_recipes"], color=_ACCENT)
    total = float(data["n_recipes"].sum())
    for i, v in enumerate(data["n_recipes"]):
        ax.text(i, v, f"{100 * v / total:.1f}%", ha="center", va="bottom", fontsize=9)
    ax.set_title("Composition of the catalogue by preparation-time band")
    ax.set_xlabel("band (G1: 0-15, G2: 15-30, G3: 30-60, G4: >60 minutes; upper-inclusive)")
    ax.set_ylabel("number of recipes (count)")
    return _finish(
        fig,
        name="fig03_band_composition",
        data=table,
        units="counts of recipes; percentages of the banded catalogue",
        caption=(
            "How the cleaned catalogue divides across the four disjoint preparation-time "
            "bands. Band imbalance is what the capacity constraint acts against: an "
            "unconstrained top-k can concentrate entirely in whichever band dominates."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


def fig_history_sizes(table: pd.DataFrame, out_dir: Path, run_id: str) -> FigureArtifact:
    """`table`: columns `n_distinct_positive_recipes`, `n_users`."""
    fig, ax = plt.subplots()
    x = table["n_distinct_positive_recipes"].astype(float)
    ax.bar(x, table["n_users"], color=_ACCENT, width=0.9)
    ax.set_yscale("log")
    ax.set_xlim(0, min(60, float(x.max()) if len(x) else 60))
    ax.set_title("Distribution of user history size (distinct positively rated recipes)")
    ax.set_xlabel("distinct recipes rated 4 or 5 (count)")
    ax.set_ylabel("number of users (count, log scale)")
    return _finish(
        fig,
        name="fig04_user_history_sizes",
        data=table,
        units="counts of users; x axis counts of distinct recipes",
        caption=(
            "Distribution of how many distinct recipes each user rated 4 or 5. The warm-user "
            "eligibility threshold of five distinct positives is applied to history events "
            "only, before any label is examined. Log scale on the y axis."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


# ------------------------------------------------------------------- result figures


def _method_bar(
    summary: pd.DataFrame, metric_col: str, title: str, ylabel: str
) -> tuple[plt.Figure, pd.DataFrame]:
    data = summary.sort_values(metric_col, ascending=False)
    fig, ax = plt.subplots()
    colours = [_METHOD_COLOUR.get(m, _MUTED) for m in data["method"]]
    bars = ax.bar(data["method"], data[metric_col], color=colours)
    for bar, value in zip(bars, data[metric_col], strict=True):
        if np.isfinite(value):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.4f}",
                ha="center",
                va="bottom",
                fontsize=9,
                color=_INK,
            )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("method (AI_LP = proposed, highlighted)")
    return fig, data


def fig_method_comparison(
    summary: pd.DataFrame, metric: str, out_dir: Path, run_id: str, k: int
) -> FigureArtifact:
    col = "mean_recall_at_k" if metric == "recall" else "mean_ndcg_at_k"
    label = f"Recall@{k}" if metric == "recall" else f"NDCG@{k}"
    idx = "05" if metric == "recall" else "06"
    fig, data = _method_bar(
        summary,
        col,
        f"Mean {label} by method (macro-average over users)",
        f"mean {label} (unitless, 0-1)",
    )
    n = int(data["n_users_with_positives"].max()) if "n_users_with_positives" in data else 0
    return _finish(
        fig,
        name=f"fig{idx}_method_comparison_{metric}_at_{k}",
        data=data,
        units="unitless ratio in [0,1]; macro-averaged per user",
        caption=(
            f"Mean {label} by method, macro-averaged over the {n} evaluated users who had at "
            f"least one eligible novel positive in the label window. All methods used the "
            f"same users and the same full eligible catalogue. AI_TOPK does not apply the "
            f"band caps by design. This measures retrieval of later positive ratings, not "
            f"user satisfaction or decision effort."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


def fig_relevance_variety_tradeoff(
    summary: pd.DataFrame, out_dir: Path, run_id: str, k: int
) -> FigureArtifact:
    """Recall against band coverage - the trade-off the whole model is about."""
    fig, ax = plt.subplots()
    for _, row in summary.iterrows():
        is_proposed = row["method"] == "AI_LP"
        ax.scatter(
            row["mean_bands_represented"],
            row["mean_recall_at_k"],
            s=140 if is_proposed else 90,
            color=_METHOD_COLOUR.get(row["method"], _MUTED),
            zorder=3,
            edgecolor="white",
            linewidth=1.2,
        )
        ax.annotate(
            row["method"],
            (row["mean_bands_represented"], row["mean_recall_at_k"]),
            textcoords="offset points",
            xytext=(8, 4),
            fontsize=9,
            color=_INK,
        )
    ax.set_title(f"Relevance against preparation-time variety (k={k})")
    ax.set_xlabel("mean number of preparation-time bands represented in the shortlist (0-4)")
    ax.set_ylabel(f"mean Recall@{k} (unitless, 0-1)")
    return _finish(
        fig,
        name="fig07_relevance_variety_tradeoff",
        data=summary,
        units="x: count of bands (0-4); y: unitless ratio in [0,1]",
        caption=(
            "Each method plotted by the variety it produces and the later positives it "
            "retrieves. Movement up-and-left or down-and-right is the empirical trade-off "
            "this study reports. Band coverage is a property of the shortlist, not evidence "
            "that users wanted variety."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


def fig_sensitivity(
    summary: pd.DataFrame, out_dir: Path, run_id: str, metric_col: str = "mean_recall_at_k"
) -> FigureArtifact:
    """Both sweeps, one panel each.

    They share the (k=6, b=3) configuration, so they are drawn as separate panels rather
    than one axis - a single shared x axis would have to collapse or duplicate that point,
    and either choice misrepresents one of the two sweeps.
    """
    data = summary.copy()
    if "sweep" not in data.columns:
        data["sweep"] = "sweep"
    data["point"] = [f"k={int(k)}, b={int(c)}" for k, c in zip(data["k"], data["cap"],
                                                               strict=True)]

    sweeps = list(dict.fromkeys(data["sweep"]))
    fig, axes = plt.subplots(1, len(sweeps), figsize=(5.2 * len(sweeps), 5), sharey=True)
    axes = np.atleast_1d(axes)

    for ax, sweep in zip(axes, sweeps, strict=True):
        block = data[data["sweep"] == sweep]
        order = (
            block[["k", "cap", "point"]]
            .drop_duplicates()
            .sort_values(["k", "cap"])["point"]
            .tolist()
        )
        for method, grp in block.groupby("method"):
            grp = grp.drop_duplicates("point").set_index("point").reindex(order).reset_index()
            ax.plot(
                grp["point"],
                grp[metric_col],
                marker="o",
                linewidth=2.2 if method == "AI_LP" else 1.3,
                linestyle=_METHOD_STYLE.get(method, "-"),
                color=_METHOD_COLOUR.get(method),
                label=method,
            )
        ax.set_title(sweep.replace("_", " "))
        ax.set_xlabel("predeclared point (length k, per-band cap b)")
    axes[0].set_ylabel(f"{metric_col.replace('mean_', 'mean ').replace('_', ' ')} (unitless)")
    axes[-1].legend(frameon=False, fontsize=9)
    fig.suptitle("Sensitivity to shortlist length and band cap", fontsize=12,
                 fontweight="600")
    return _finish(
        fig,
        name="fig08_sensitivity",
        data=data,
        units="unitless ratio in [0,1]; x axis is a predeclared (k, b) configuration",
        caption=(
            "Predeclared sensitivity sweeps. Within each sweep the users, profiles, scores, "
            "dates and positive-rating definition are identical; only k and b change. "
            "b = k removes the effective band cap. Users made structurally infeasible by a "
            "tighter cap are reported in the infeasibility table, not dropped."
        ),
        run_id=run_id,
        out_dir=out_dir,
    )


def fig_graphical_slice(slice_dict: dict[str, Any], out_dir: Path, run_id: str) -> FigureArtifact:
    """The two-variable graphical-method illustration."""
    sa, sb = slice_dict["score_a"], slice_dict["score_b"]
    ra, rb = slice_dict["recipe_a"], slice_dict["recipe_b"]

    fig, ax = plt.subplots(figsize=(6.5, 6.0))
    ax.add_patch(
        plt.Rectangle((0, 0), 1, 1, facecolor="#f1f5f9", edgecolor=_MUTED, linewidth=1.0)
    )
    ax.plot([1, 0], [0, 1], color=_ACCENT, linewidth=3, zorder=3,
            label="feasible set: $x_a + x_b = 1$")

    for (xa, xb) in [(1.0, 0.0), (0.0, 1.0)]:
        optimal = [xa, xb] == list(slice_dict["optimal_vertex"])
        ax.scatter([xa], [xb], s=150 if optimal else 90, zorder=4,
                   color=_ACCENT if optimal else "white",
                   edgecolor=_ACCENT, linewidth=2)
        ax.annotate(
            f"({xa:g}, {xb:g})\nZ = {sa * xa + sb * xb:.4f}"
            + ("\noptimal" if optimal else ""),
            (xa, xb),
            textcoords="offset points",
            xytext=(12 if xa == 0 else -12, 12 if xb == 0 else -34),
            ha="left" if xa == 0 else "right",
            fontsize=9,
            color=_INK,
        )

    # Objective direction: the gradient (s_a, s_b), drawn from the centre of the segment.
    norm = float(np.hypot(sa, sb)) or 1.0
    ax.arrow(0.5, 0.5, 0.28 * sa / norm, 0.28 * sb / norm, width=0.008,
             color=_INK, length_includes_head=True, zorder=5)
    ax.annotate("increasing objective", (0.5 + 0.3 * sa / norm, 0.5 + 0.3 * sb / norm),
                fontsize=8.5, color=_INK)

    ax.set_xlim(-0.08, 1.15)
    ax.set_ylim(-0.08, 1.15)
    ax.set_aspect("equal")
    ax.set_title("Two-variable slice of the shortlist LP")
    ax.set_xlabel(f"$x_a$ — recipe {ra}, band {slice_dict['band_a']}, score {sa:.4f}")
    ax.set_ylabel(f"$x_b$ — recipe {rb}, band {slice_dict['band_b']}, score {sb:.4f}")
    ax.legend(frameon=False, fontsize=9, loc="upper right")

    data = pd.DataFrame(
        [
            {
                "vertex": f"({xa:g}, {xb:g})",
                "x_a": xa,
                "x_b": xb,
                "recipe_selected": ra if xa > 0.5 else rb,
                "slice_objective": sa * xa + sb * xb,
                "full_shortlist_objective": slice_dict["fixed_objective"] + sa * xa + sb * xb,
                "optimal": [xa, xb] == list(slice_dict["optimal_vertex"]),
            }
            for xa, xb in [(1.0, 0.0), (0.0, 1.0)]
        ]
    )
    return _finish(
        fig,
        name="fig09_graphical_method_slice",
        data=data,
        units="axes are selection variables in [0,1]; objective in AI relevance score units",
        caption=slice_dict["caption"],
        run_id=run_id,
        out_dir=out_dir,
    )
