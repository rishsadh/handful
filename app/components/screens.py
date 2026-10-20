"""The demo's seven screens."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from app.components import dataload as dl
from app.components import theme as th
from foodcom.evaluation.methods import METHOD_DESCRIPTIONS, run_ai_topk, run_lp_method, run_random
from foodcom.models.bands import band_bounds_text
from foodcom.models.scoring import SCORE_MEANING, score_candidates
from foodcom.optimisation.dual import BETA_MEANING, check_duality
from foodcom.optimisation.integrality import HONEST_CLAIM
from foodcom.optimisation.lpp import ShortlistProblem, check_feasibility, solve_primal

SCENARIO_BANNER = (
    "<strong>Hypothetical scenario.</strong> Time limits and ingredient exclusions are "
    "what-if filters you have set here. Food.com does not record them as this user's real "
    "preferences, and nothing on this screen is a research result. Ingredient matching "
    "looks for a text term in the recipe's ingredient list — it is not an allergy or "
    "food-safety check."
)


# --------------------------------------------------------------------------- overview


def overview(state: dl.DemoState) -> None:
    st.markdown("# Personalised recipe shortlisting using linear programming")
    th.lede(
        "Given what a Food.com user rated highly in the past, can a shortlist of six "
        "recipes be chosen to maximise estimated relevance while keeping the shortlist "
        "spread across preparation-time bands — and does that constraint cost anything "
        "in retrieval of the recipes they went on to rate highly?"
    )

    manifest = dl.source_manifest()
    c1, c2, c3 = st.columns(3)
    with c1:
        th.stat("Dataset", "Food.com", "Recipes and Interactions, Shuyang Li (Kaggle)")
    with c2:
        th.stat(
            "Version",
            str(manifest["kaggle_version"]) if manifest else "not recorded",
            "recorded at acquisition, with SHA-256 file hashes",
        )
    with c3:
        th.stat("Study type", "Offline", "secondary data · no participants · no surveys")

    th.rule()

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("### What this is")
        st.markdown(
            """
Two components, in order.

**1 — A frozen sentence encoder** turns each recipe's text (name, ingredients,
whitelisted descriptive tags, short description) into a vector. A user's profile is the
normalised mean of the vectors of recipes they rated 4 or 5 *before* the cutoff date. The
relevance score is the shifted cosine between the two, mapped onto 0–1.

**2 — A linear programme** picks exactly six recipes to maximise the total relevance
score, subject to a cap of three per preparation-time band. Four disjoint bands:
0–15, 15–30, 30–60 and over 60 reported minutes.

The variables are continuous, not binary. Because the bands partition the candidates, the
problem has the structure of a min-cost flow with integer capacities, so a basic optimal
solution comes back whole. Every solve verifies that rather than assuming it.
            """
        )
        st.markdown("### What it is not")
        st.markdown(
            """
- Not a satisfaction predictor. The score estimates semantic relevance, nothing more.
- Not a measurement of choice overload. Choice overload motivates the idea of shortlisting;
  this study measures retrieval, ranking, variety and feasibility.
- Not a live system. The encoder postdates the review period, so this is retrospective
  benchmarking, not a system that could have run in 2016.
- Not a nutrition or allergy tool. No health or safety claim is made anywhere.
            """
        )
    with right:
        st.markdown("### Evidence boundaries")
        th.notice(
            "This demo can show: retrieval of later positive ratings, ranking quality, "
            "preparation-time band representation, constraint compliance, feasibility, "
            "machine runtime, and sensitivity to the shortlist length and cap.",
            "info",
        )
        th.notice(
            "It cannot show: reduced choice overload, reduced stress, faster human "
            "decisions, greater confidence, better meal satisfaction, better nutrition, "
            "or allergy safety. None of those were measured.",
            "block",
        )
        st.markdown("### The honest claim about the solver")
        th.muted(HONEST_CLAIM)
        st.markdown("### No data is collected")
        th.muted(
            "This demo collects nothing: no names, no emails, no surveys, no confidence "
            "ratings, no decision timers and no record of what you click. Review text is "
            "never displayed."
        )


# --------------------------------------------------------------------------- profile


def profile(state: dl.DemoState, label: str) -> None:
    user_id = state.label_to_user[label]
    split = state.split

    st.markdown(f"# {label}")
    th.lede(
        f"Everything below happened strictly before "
        f"{split.window.history_end_exclusive}. This is the only information the model is "
        f"allowed to use. The real Food.com user id is not shown."
    )

    positives = split.positives.get(user_id, set())
    seen = split.seen.get(user_id, set())
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        th.stat("Positively rated", f"{len(positives)}", "distinct recipes rated 4 or 5")
    with c2:
        th.stat("Recipes seen", f"{len(seen)}", "any earlier interaction, excluded as candidates")
    with c3:
        th.stat("History cutoff", str(split.window.history_end_exclusive), "strictly before")
    with c4:
        candidates = int(state.ctx.candidate_mask(user_id).sum())
        th.stat("Eligible candidates", f"{candidates:,}", "unseen, submitted before the cutoff")

    th.rule()
    st.markdown("### Recipes this profile rated 4 or 5")
    frame = dl.history_frame(state, user_id, limit=12)
    if frame.empty:
        th.notice("No positive history in the window. This profile is cold.", "block")
    else:
        st.dataframe(frame, hide_index=True, width="stretch")

    bands = frame["band"].value_counts() if not frame.empty else pd.Series(dtype=int)
    if len(bands):
        st.markdown("### Preparation-time bands in this history")
        th.muted(
            "Shown because it is the axis the constraint acts on. A history concentrated "
            "in one band tells you what an unconstrained top-k would likely return."
        )
        st.bar_chart(bands, height=200)


# --------------------------------------------------------------------- recommendations


def _solve_for(
    state: dl.DemoState,
    user_id: int,
    mask: np.ndarray,
    k: int,
    cap: int,
) -> tuple[ShortlistProblem, Any]:
    ctx = state.ctx
    candidate_ids = ctx.catalogue_ids[mask]
    scores = score_candidates(user_id, candidate_ids, ctx.profiles, ctx.store)
    problem = ShortlistProblem(
        candidate_ids=candidate_ids,
        scores=scores,
        band_of=ctx.band_index[mask],
        k=k,
        caps=np.full(len(ctx.band_labels), cap, dtype="int64"),
        band_labels=ctx.band_labels,
        user_id=user_id,
    )
    return problem, solve_primal(problem, tol=state.cfg.model.solver.tolerance)


def _recipe_card(
    state: dl.DemoState, rank: int, recipe_id: int, score: float, history_ids: list[int],
    method: str,
) -> None:
    row = dl.recipe_row(state, recipe_id)
    shared = dl.shared_ingredients(state, recipe_id, history_ids)[:4]
    why = (
        "Shares "
        + ", ".join(f"<em>{s}</em>" for s in shared)
        + " with recipes this profile rated 4 or 5 before the cutoff."
        if shared
        else (
            "No ingredient overlap with the profile's rated history; the relevance score "
            "comes from the wider recipe text."
        )
    )
    st.markdown(
        f"""<div class="card card-accent"><div class="recipe">
        <div class="recipe-rank">{rank}</div>
        <div style="flex:1">
          <div class="recipe-name">{row['name']}</div>
          <div class="recipe-meta">
            <span class="pill">{int(row['minutes'])} min</span>
            <span class="pill">{row['band']}</span>
            <span class="pill pill-accent">{method}</span>
            <span class="score">relevance {score:.4f}</span>
          </div>
          <div class="recipe-why">{why}</div>
        </div></div></div>""",
        unsafe_allow_html=True,
    )


def recommendations(state: dl.DemoState, label: str, k: int, cap: int) -> None:
    user_id = state.label_to_user[label]
    st.markdown("# The shortlist")
    th.lede(
        "Six recipes chosen to maximise total estimated relevance, with at most three "
        "from any one preparation-time band. Every one is a real Food.com recipe the "
        "profile had not interacted with before the cutoff."
    )
    th.notice(f"<strong>What the score means.</strong> {SCORE_MEANING}", "info")

    mask = state.ctx.candidate_mask(user_id)
    problem, solution = _solve_for(state, user_id, mask, k, cap)

    if not solution.feasibility.feasible:
        th.notice(
            f"<strong>No feasible shortlist.</strong> {solution.feasibility.reason}", "block"
        )
        return
    if not solution.ok:
        th.notice(
            "<strong>The solution failed its structural checks.</strong> "
            + "; ".join(solution.verification.problems),
            "block",
        )
        return

    pos = {int(r): i for i, r in enumerate(problem.candidate_ids)}
    history_ids = sorted(state.split.positives.get(user_id, set()))
    for rank, rid in enumerate(solution.ranked_ids, start=1):
        _recipe_card(
            state, rank, int(rid), float(problem.scores[pos[int(rid)]]), history_ids, "AI_LP"
        )

    th.rule()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        th.stat("Objective", f"{solution.objective:.4f}", "sum of relevance scores")
    with c2:
        th.stat("Bands covered", f"{len([v for v in solution.band_usage().values() if v])}/4",
                "distinct preparation-time bands")
    with c3:
        th.stat("Candidates", f"{problem.n:,}", "eligible unseen recipes ranked")
    with c4:
        th.stat("Solve time", f"{solution.solve_seconds * 1000:.1f} ms",
                "machine runtime, not a human decision time")


# ------------------------------------------------------------------ method comparison


def method_comparison(state: dl.DemoState, label: str, k: int, cap: int) -> None:
    user_id = state.label_to_user[label]
    st.markdown("# Four methods, one profile")
    th.lede(
        "All four see the same profile, the same eligible catalogue and the same "
        "shortlist length. Only the score they optimise and whether the band caps apply "
        "differ. AI_TOPK deliberately ignores the caps: it is the ablation that separates "
        "'the score helped' from 'the constraint helped'."
    )

    mask = state.ctx.candidate_mask(user_id)
    problem, _ = _solve_for(state, user_id, mask, k, cap)
    pop_problem = ShortlistProblem(
        candidate_ids=problem.candidate_ids,
        scores=state.ctx.popularity[mask],
        band_of=problem.band_of,
        k=k,
        caps=problem.caps,
        band_labels=problem.band_labels,
        user_id=user_id,
    )

    outputs = {
        "AI_LP": run_lp_method(problem, tol=state.cfg.model.solver.tolerance),
        "AI_TOPK": run_ai_topk(problem),
        "POPULARITY_LP": run_lp_method(pop_problem, tol=state.cfg.model.solver.tolerance),
        "RANDOM": run_random(problem, seed=state.cfg.research.protocol.random_seed),
    }

    pos = {int(r): i for i, r in enumerate(problem.candidate_ids)}
    rows = []
    for name in ("AI_LP", "AI_TOPK", "POPULARITY_LP", "RANDOM"):
        out = outputs[name]
        ids = [int(i) for i in out.ranked_ids]
        band_counts: dict[str, int] = {}
        for rid in ids:
            lab = problem.band_labels[int(problem.band_of[pos[rid]])]
            band_counts[lab] = band_counts.get(lab, 0) + 1
        rows.append(
            {
                "method": name,
                "items": len(ids),
                "bands covered": len(band_counts),
                "max per band": max(band_counts.values()) if band_counts else 0,
                "cap respected": (max(band_counts.values()) <= cap) if band_counts else True,
                "total relevance": float(sum(problem.scores[pos[r]] for r in ids)),
                "solver": out.solver_status,
                "runtime (ms)": round(out.solve_seconds * 1000, 2),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    th.notice(
        "AI_TOPK's total relevance is at least AI_LP's by construction — it optimises the "
        "same objective over a larger feasible set. Any difference in <em>retrieval</em> "
        "is about which items the caps forced in or out, and that is an empirical "
        "question answered on the Evidence screen, not here.",
        "info",
    )

    th.rule()
    st.markdown("### The shortlists side by side")
    cols = st.columns(4)
    for col, name in zip(cols, ("AI_LP", "AI_TOPK", "POPULARITY_LP", "RANDOM"), strict=True):
        with col:
            st.markdown(f"**{name}**")
            th.muted(METHOD_DESCRIPTIONS[name])
            for rid in outputs[name].ranked_ids:
                row = dl.recipe_row(state, int(rid))
                st.markdown(
                    f'<div class="card" style="padding:.7rem .8rem">'
                    f'<div style="font-size:.85rem;font-weight:600">{row["name"][:52]}</div>'
                    f'<div class="recipe-meta" style="margin:.3rem 0 0">'
                    f'{int(row["minutes"])} min · {row["band"]}</div></div>',
                    unsafe_allow_html=True,
                )


# --------------------------------------------------------------------- OR inspector


def or_inspector(state: dl.DemoState, label: str, k: int, cap: int) -> None:
    user_id = state.label_to_user[label]
    st.markdown("# Inside the linear programme")

    mask = state.ctx.candidate_mask(user_id)
    problem, solution = _solve_for(state, user_id, mask, k, cap)

    st.markdown("### The model")
    st.code(
        f"""maximise    Σ s_ui · x_i                    over {problem.n:,} eligible unseen recipes

subject to  Σ x_i = {k}                            exactly {k} recipes
            Σ_{{i ∈ G_g}} x_i ≤ {cap}   for each of the {problem.n_bands} bands
            0 ≤ x_i ≤ 1                       continuous, not binary

solver      scipy.optimize.linprog(method="{state.cfg.model.solver.method}")
objective   c = −s   (SciPy minimises; we maximise relevance)""",
        language="text",
    )

    feas = check_feasibility(problem)
    st.markdown("### Feasibility")
    sizes = ", ".join(
        f"{lab}: {n:,}" for lab, n in zip(problem.band_labels, feas.band_sizes, strict=True)
    )
    st.markdown(
        f"`Σ_g min(b_g, |G_g ∩ C_u|)` = **{feas.capacity}**, needs ≥ **{k}** → "
        f"**{'feasible' if feas.feasible else 'INFEASIBLE'}**"
    )
    th.muted(f"Band sizes among eligible candidates — {sizes}")

    if not solution.feasibility.feasible:
        th.notice(f"<strong>Infeasible.</strong> {solution.feasibility.reason}", "block")
        return

    st.markdown("### Solution and verification")
    v = solution.verification
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        th.stat("Objective", f"{solution.objective:.6f}", "maximised relevance")
    with c2:
        th.stat("Equality residual", f"{v.equality_residual:.2e}",
                f"tolerance {v.tolerance:g}")
    with c3:
        th.stat("Distance to integer", f"{v.max_distance_to_integer:.2e}",
                "0 or 1 within tolerance")
    with c4:
        th.stat("Checks", "passed" if v.ok else "FAILED", v.message[:48])

    selected = pd.DataFrame(
        [
            {
                "recipe_id": int(rid),
                "name": dl.recipe_row(state, int(rid))["name"],
                "band": problem.band_labels[
                    int(problem.band_of[list(problem.candidate_ids).index(int(rid))])
                ],
                "score s_ui": float(
                    problem.scores[list(problem.candidate_ids).index(int(rid))]
                ),
                "x_i": 1.0,
            }
            for rid in solution.ranked_ids
        ]
    )
    st.dataframe(selected, hide_index=True, width="stretch")

    usage = solution.band_usage()
    st.markdown("### Band capacity usage")
    st.dataframe(
        pd.DataFrame(
            [
                {"band": lab, "definition": defn, "used": usage.get(lab, 0), "cap": cap,
                 "binding": usage.get(lab, 0) == cap}
                for lab, defn in band_bounds_text(state.cfg.research.protocol).items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    th.rule()
    st.markdown("### Duality")
    th.muted(
        "Computed on a pruned problem for speed on this screen would be misleading, so the "
        "dual below is solved on the full unpruned problem — the same way the Results Pack "
        "certificate is produced."
    )
    with st.spinner("solving the dual on the full problem ..."):
        _, dual, report = check_duality(problem, tol=state.cfg.model.solver.tolerance)

    c1, c2, c3 = st.columns(3)
    with c1:
        th.stat("Primal objective", f"{report.primal_objective:.6f}", "maximise")
    with c2:
        th.stat("Dual objective", f"{report.dual_objective:.6f}", "minimise")
    with c3:
        th.stat("Duality gap", f"{report.duality_gap:.2e}",
                "strong duality holds" if report.strong_duality_holds else "CHECK FAILED")

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "band": lab,
                    "cap b_g": cap,
                    "used": usage.get(lab, 0),
                    "shadow value β_g": float(beta),
                    "binding": usage.get(lab, 0) == cap,
                }
                for lab, beta in zip(problem.band_labels, dual.beta, strict=True)
            ]
            + [{"band": "α (exact-size constraint)", "cap b_g": None, "used": None,
                "shadow value β_g": dual.alpha, "binding": None}]
        ),
        hide_index=True,
        width="stretch",
    )
    th.notice(f"<strong>How to read β.</strong> {BETA_MEANING}", "info")
    th.muted(
        "Complementary slackness residuals — "
        + ", ".join(f"{k2}: {v2:.2e}" for k2, v2 in report.complementary_slackness.items())
        + f" (tolerance {report.tolerance:g})."
    )


# --------------------------------------------------------------------- scenario


def scenario(state: dl.DemoState, label: str) -> None:
    user_id = state.label_to_user[label]
    st.markdown("# Scenario controls")
    th.notice(SCENARIO_BANNER, "scenario")

    c1, c2 = st.columns(2)
    with c1:
        k = st.slider("Shortlist length k", 2, 12, state.cfg.research.protocol.shortlist_size_k)
        cap = st.slider("Per-band cap b", 1, 12, state.cfg.research.protocol.band_cap_b)
    with c2:
        use_max = st.checkbox("Apply a maximum reported preparation time")
        max_minutes = st.slider("Maximum reported minutes", 5, 240, 45) if use_max else None
        terms_raw = st.text_input(
            "Exclude recipes whose ingredient list mentions (comma separated)",
            placeholder="e.g. peanut, shellfish",
        )
    terms = [t for t in (terms_raw or "").split(",") if t.strip()]

    mask, removed = dl.scenario_mask(
        state, user_id, max_minutes=max_minutes, excluded_terms=terms
    )
    n_candidates = int(mask.sum())

    st.markdown("### What the filters removed")
    st.dataframe(
        pd.DataFrame(
            [
                {"filter": "already interacted with before the cutoff (not a scenario "
                           "control — a protocol rule)", "recipes removed": removed["already_seen"]},
                {"filter": f"reported minutes above {max_minutes}" if max_minutes
                           else "maximum preparation time (not applied)",
                 "recipes removed": removed["max_minutes"]},
                {"filter": f"ingredient term match: {', '.join(terms)}" if terms
                           else "ingredient exclusions (not applied)",
                 "recipes removed": removed["ingredient_terms"]},
                {"filter": "remaining eligible candidates", "recipes removed": n_candidates},
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    if n_candidates == 0:
        th.notice(
            "<strong>Nothing left to choose from.</strong> Every eligible recipe was "
            "removed by your filters. Widen the time limit or remove an ingredient term. "
            "The ingredient exclusion will never be relaxed automatically.",
            "block",
        )
        return

    problem, solution = _solve_for(state, user_id, mask, k, cap)
    if not solution.feasibility.feasible:
        sizes = ", ".join(
            f"{lab}: {n}"
            for lab, n in zip(problem.band_labels, solution.feasibility.band_sizes, strict=True)
        )
        th.notice(
            f"<strong>This scenario has no feasible shortlist.</strong><br>"
            f"With a cap of {cap} per band and band sizes ({sizes}), at most "
            f"<strong>{solution.feasibility.capacity}</strong> recipes can be chosen, but you "
            f"asked for <strong>{k}</strong>.<br><br>"
            f"Raise the per-band cap, lower k, or widen the time limit. The ingredient "
            f"exclusion stays exactly as you set it — it is never relaxed automatically, "
            f"because silently reintroducing an excluded ingredient would be the worst "
            f"possible failure mode for a control like this.",
            "block",
        )
        return
    if not solution.ok:
        th.notice("Solution failed verification: " + "; ".join(solution.verification.problems),
                  "block")
        return

    th.rule()
    st.markdown(f"### Scenario shortlist — {len(solution.ranked_ids)} recipes")
    pos = {int(r): i for i, r in enumerate(problem.candidate_ids)}
    history_ids = sorted(state.split.positives.get(user_id, set()))
    for rank, rid in enumerate(solution.ranked_ids, start=1):
        _recipe_card(
            state, rank, int(rid), float(problem.scores[pos[int(rid)]]), history_ids,
            "scenario",
        )
    th.notice(SCENARIO_BANNER, "scenario")


# --------------------------------------------------------------------- evidence


def evidence(state: dl.DemoState) -> None:
    st.markdown("# Benchmark results")
    th.lede(
        "Everything here was precomputed by a recorded pipeline run. Nothing on this "
        "screen is generated live, and nothing you did on the scenario screen changed it."
    )

    run = dl.latest_run("final")
    if run is None:
        th.notice(
            "<strong>No completed evaluation run found.</strong> Run "
            "<code>python tasks.py validate</code> (or <code>final</code>) first. No "
            "placeholder numbers are shown in the meantime.",
            "block",
        )
        return

    manifest = run["manifest"]
    stage = manifest.get("stage", "unknown")
    c1, c2, c3 = st.columns(3)
    with c1:
        th.stat("Run id", run["run_id"][:28], f"stage: {stage}")
    with c2:
        th.stat("Status", manifest.get("status", "?"), str(manifest.get("completed_utc", ""))[:19])
    with c3:
        th.stat("Code revision", str(manifest.get("code", {}).get("revision"))[:12] or "—",
                f"protocol {manifest.get('protocol_version')}")

    if stage != "final":
        th.notice(
            "These are <strong>validation-stage</strong> results. The final test set has "
            "not been used yet.",
            "info",
        )

    tables = run["tables"]
    th.rule()
    st.markdown("### Method comparison")
    if "t04_method_comparison" in tables:
        st.dataframe(tables["t04_method_comparison"], hide_index=True, width="stretch")
    st.markdown("### Paired differences with 95% bootstrap intervals")
    if "t05_paired_differences" in tables:
        st.dataframe(
            tables["t05_paired_differences"], hide_index=True, width="stretch"
        )
        th.notice(
            "An interval that contains zero is <strong>not</strong> evidence that two "
            "methods are equivalent. Claiming preserved quality would require a "
            "non-inferiority margin declared in advance, which this protocol does not have.",
            "info",
        )

    st.markdown("### Metric definitions")
    st.code(
        """Recall@k = |L_u ∩ R_u| / |R_u|
DCG@k    = Σ_{j=1..k} 1[item_j ∈ R_u] / log₂(j+1)
NDCG@k   = DCG@k / IDCG@k,  IDCG@k = Σ_{j=1..min(k,|R_u|)} 1 / log₂(j+1)

R_u = eligible novel recipes the user rated 4 or 5 in the label window
L_u = the ranked k-item output
Both macro-averaged per user. Reported only for users with |R_u| > 0.""",
        language="text",
    )

    for title, key in (
        ("Sensitivity — shortlist length", "t06_sensitivity_length"),
        ("Sensitivity — band cap", "t07_sensitivity_cap"),
        ("Feasibility and failures", "t08_feasibility_and_failures"),
        ("Denominators", "denominators"),
    ):
        if key in tables:
            st.markdown(f"### {title}")
            st.dataframe(tables[key], hide_index=True, width="stretch")

    if run["figures"]:
        th.rule()
        st.markdown("### Figures")
        cols = st.columns(2)
        for i, path in enumerate(run["figures"]):
            with cols[i % 2]:
                st.image(str(path), caption=path.stem, width="stretch")

    th.rule()
    st.markdown("### Download the aggregate tables")
    th.muted(
        "Aggregate results only. Raw review text and raw user ids are never exported here."
    )
    for name, frame in tables.items():
        if name == "per_user_results":
            continue
        st.download_button(
            f"{name}.csv",
            frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{run['run_id']}__{name}.csv",
            mime="text/csv",
            key=f"dl_{name}",
        )

    th.rule()
    st.markdown("### Limitations")
    st.markdown(
        """
- Observational data. Users chose what to cook and review; nothing here is randomised.
- Ratings are not a complete record of preference. An unreviewed recipe is not a dislike.
- Rating 0 means unrated, not zero stars.
- The encoder postdates the review period and may have seen Food.com text in pretraining.
- Preparation times are contributor-reported, not measured.
- Recipes are shared across users, so bootstrap intervals understate dependence.
- The band cap is a design choice. Nothing here shows that users want time variety.
        """
    )
