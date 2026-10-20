"""The Results Pack.

Assembles `docs/RESULTS_PACK.md` from the artifacts of a finished run. Written for
someone who will not read the Python: every number carries the run id that produced it, and
every section says plainly what the number does and does not support.

When an artifact is missing - because a gate is still blocked - the section says so
explicitly. It never fills a gap with a plausible number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from foodcom.evaluation.methods import METHOD_DESCRIPTIONS
from foodcom.evaluation.metrics import REDUCTION_MEANING, RUNTIME_MEANING
from foodcom.evaluation.stats import interval_meaning
from foodcom.models.scoring import SCORE_MEANING
from foodcom.optimisation.dual import BETA_MEANING
from foodcom.optimisation.integrality import ARGUMENT_SUMMARY, HONEST_CLAIM
from foodcom.reporting.tables import to_markdown
from foodcom.utils import logging as flog
from foodcom.utils.config import Configs

log = flog.get_logger(__name__)

PENDING = (
    "> **PENDING.** This artifact does not exist yet because the pipeline has not run to "
    "this point. Nothing has been substituted for it."
)

STATEMENTS_TO_AVOID = """\
These statements are **not** supported by anything this project computed. They must not
appear in the paper, the viva, or a figure caption:

- that the system reduced choice overload, stress, regret or decision difficulty;
- that it increased user confidence, satisfaction or enjoyment;
- that it made anyone decide faster - every runtime reported here is machine runtime;
- that it improved nutrition, diet quality or any health outcome;
- that shortlists are allergy-safe, or safe for any dietary requirement;
- that the findings generalise to consumers in general, to other platforms, or to a live
  deployment;
- that a non-significant difference proves two methods are equivalent;
- that the linear programme was computationally necessary - a greedy selection solves this
  restricted case too.

Choice overload is the **theoretical motivation** for shortlisting. It is not an outcome
this study observed. Every empirical claim must be limited to: retrieval of later positive
ratings, ranking quality, preparation-time band representation, constraint compliance,
feasibility, runtime, and sensitivity to k and b.
"""


def _read_csv(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path) if path.exists() else None
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)
        return None


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)
        return None


def _section(title: str, body: str) -> str:
    return f"\n## {title}\n\n{body}\n"


def _latest_stage_run(cfg: Configs, stage: str, before_utc: str | None) -> Path | None:
    """The most recently completed run of `stage`, no later than `before_utc`.

    Tables 1-3 (raw audit, cleaning ledger, split and eligibility) are produced by the
    audit, clean and splits stages - each its own timestamped run directory, never inside
    the validation/final run that consumes them. Without this lookup, `build_results_pack`
    only ever finds t04 onward next to the run it was given, and Tables 1-3 render as
    PENDING even when the upstream stages completed - the pack cannot tell "not run yet"
    apart from "run somewhere else." `before_utc` (the consuming run's own start time)
    keeps the lookup honest: a stage run that finished after this run started could not
    have been what this run actually used.
    """
    candidates: list[tuple[str, Path]] = []
    for p in cfg.path("runs_dir").glob(f"{stage}-*"):
        manifest = _read_json(p / "manifest.json")
        if not manifest or manifest.get("status") != "completed":
            continue
        completed = manifest.get("completed_utc") or ""
        if before_utc and completed and completed > before_utc:
            continue
        candidates.append((completed, p))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]


def build_results_pack(
    cfg: Configs,
    run_dir: Path,
    *,
    out_path: Path | None = None,
    gate_status: dict[str, Any] | None = None,
) -> Path:
    """Compose the Results Pack from one run directory."""
    manifest = _read_json(run_dir / "manifest.json") or {}
    run_id = manifest.get("run_id", run_dir.name)
    protocol = cfg.research.protocol
    k = protocol.shortlist_size_k
    b = protocol.band_cap_b

    tables = run_dir / "tables"
    metrics = run_dir / "metrics"

    parts: list[str] = ["# Results Pack — Food.com recipe shortlisting\n"]
    if not manifest:
        parts.append(
            f"""**For:** Khushi (research writing, interpretation, submission)
**Protocol version:** {cfg.research.protocol_version}

> **NO EVALUATION RUN EXISTS YET.** Every results section below is marked PENDING. Nothing
> has been substituted for a missing number, and no figure or table in this file is a
> research result. The method sections describe what *will* be computed; they are a
> specification, not evidence.

Run `python tasks.py validate` (or `final`) and regenerate this pack with
`python tasks.py results-pack`.
"""
        )
    else:
        parts.append(
            f"""**For:** Khushi (research writing, interpretation, submission)
**Prepared by:** the technical pipeline in `handful`, run `{run_id}`
**Protocol version:** {cfg.research.protocol_version}
**Run status:** {manifest.get('status', 'unknown')}
**Started / completed (UTC):** {manifest.get('started_utc')} → {manifest.get('completed_utc')}

Every number below can be traced to run `{run_id}`. The run directory holds the exact
configuration, the dataset hashes, the code revision, the package versions and the logs
that produced it. If a number here disagrees with the run directory, the run directory is
right.

This pack does not contain interpretation, discussion or conclusions. Those are yours to
write. What it contains is what the code computed and what those quantities mean.
"""
        )

    # ---------------------------------------------------------------- 1. dataset
    source = _read_json(cfg.path("processed_dir") / "source_manifest.json")
    if source:
        files_md = "\n".join(
            f"- `{f['filename']}` — {f['bytes']:,} bytes — SHA-256 `{f['sha256']}`"
            if f.get("present")
            else f"- `{f['filename']}` — **absent**"
            for f in source.get("files", [])
        )
        body = f"""**Dataset:** {source['dataset_name']}
**Uploader:** {source['uploader']}
**Source:** <{source['source_url']}>
**Kaggle version:** {source['kaggle_version']}
**Download date:** {source['download_date']}
**Licence, as stated by the source:**

> {source['licence_text']}

**Redistribution permitted:** {source['licence_permits_redistribution']}
(`null` means unknown, and unknown is treated as "no". Permission to redistribute raw data
or review text has to be established from the licence itself, not inferred from a code
licence in the same repository.)

**Files, hashed at acquisition:**

{files_md}

Raw bytes are immutable. Every transformation writes to `data/interim` or `data/processed`.

**A note on counts.** The source paper's widely quoted 180K+/700K+ figures describe *its
filtered task corpus*; it reports collecting 230K+ recipes and 1M+ reviews before
filtering. Neither number is ours. Every count in this pack was computed from the
downloaded files listed above under our own documented rules."""
    else:
        gate = gate_status or {}
        body = f"""{PENDING}

The data gate has not been passed.

- Files present: `{gate.get('files_present')}`
- Missing files: `{gate.get('missing_files')}`
- Provenance complete: `{gate.get('provenance_complete')}`
- Missing provenance fields: `{gate.get('missing_provenance_fields')}`

No dataset counts, licence wording or hashes can be reported until the two official files
are in `{gate.get('raw_dir', 'data/raw')}` and `config/research.yaml` records the version,
download date and licence text."""
    parts.append(_section("1. Dataset identity, licence and provenance", body))

    # ---------------------------------------------------------------- 2. audit
    # t01/t02 belong to the audit and clean stages, each its own run directory - look them
    # up there rather than assuming they sit beside this run's own t04 onward.
    started = manifest.get("started_utc")
    audit_run = _latest_stage_run(cfg, "audit", started)
    clean_run = _latest_stage_run(cfg, "clean", started)
    audit_tbl = _read_csv(tables / "t01_raw_dataset_audit.csv")
    audit_src = run_id
    if audit_tbl is None and audit_run is not None:
        audit_tbl = _read_csv(audit_run / "tables" / "t01_raw_dataset_audit.csv")
        audit_src = audit_run.name
    ledger = _read_csv(tables / "t02_cleaning_exclusion_ledger.csv")
    clean_src = run_id
    if ledger is None and clean_run is not None:
        ledger = _read_csv(clean_run / "tables" / "t02_cleaning_exclusion_ledger.csv")
        clean_src = clean_run.name
    body = "### Table 1 — Raw dataset audit\n\n"
    if audit_tbl is not None:
        if audit_src != run_id:
            body += f"_From run `{audit_src}`, the audit stage this evaluation consumed._\n\n"
        body += to_markdown(audit_tbl)
    else:
        body += PENDING
    body += "\n\n### Table 2 — Cleaning and exclusion ledger\n\n"
    body += (
        "Read this top to bottom. Each row is one ordered stage; `n_removed` is what that "
        "stage excluded and `reason` is why. The ledger reconciles the raw download to the "
        "final catalogue with no unexplained gap.\n\n"
    )
    if ledger is not None:
        if clean_src != run_id:
            body += f"_From run `{clean_src}`, the clean stage this evaluation consumed._\n\n"
        body += to_markdown(ledger, max_rows=40)
    else:
        body += PENDING
    parts.append(_section("2. Audit and cleaning", body))

    # ---------------------------------------------------------------- 3. split
    # t03 belongs to the splits stage, its own run directory - same lookup as above.
    #
    # The population an evaluation actually scored is the one recorded in that run's own
    # `metrics/split_denominators.json`, so that is what Table 3 shows. The standalone
    # splits stage is a separate, earlier run and may have used a different cohort scope:
    # the 2026-09-06 splits run applied the 5,000-user compute cap, which decision D-022
    # removed before the final evaluation (126 rankable users capped, 530 uncapped). Reading
    # Table 3 from that earlier run made it contradict Table 4. The splits-stage table is
    # now only a fallback for a run that recorded no denominators, and any disagreement
    # between the two is stated under the table rather than hidden.
    splits_run = _latest_stage_run(cfg, "splits", started)
    split_tbl = _read_csv(tables / "t03_split_and_eligibility.csv")
    split_src = run_id
    own_denoms = _read_json(metrics / "split_denominators.json")
    split_note = ""
    splits_tbl = (
        _read_csv(splits_run / "tables" / "t03_split_and_eligibility.csv")
        if splits_run is not None
        else None
    )
    if split_tbl is None and own_denoms:
        split_tbl = pd.DataFrame(
            [{"stage": manifest.get("stage", ""), **own_denoms}]
        )
        split_src = f"{run_id} (its own metrics/split_denominators.json)"
    elif split_tbl is None and splits_tbl is not None:
        split_tbl = splits_tbl
        split_src = splits_run.name
    if own_denoms and splits_tbl is not None and splits_run is not None:
        earlier = splits_tbl[splits_tbl["stage"] == manifest.get("stage")]
        if len(earlier) == 1:
            row = earlier.iloc[0]
            differing = [
                key
                for key in (
                    "cohort_capped",
                    "cohort_cap",
                    "n_cohort_users",
                    "n_cohort_users_with_any_future_event",
                    "n_ranking_eligible_users",
                )
                if str(row.get(key)) != str(own_denoms.get(key))
                and not (pd.isna(row.get(key)) and own_denoms.get(key) is None)
            ]
            if differing:
                split_note = (
                    f"\n\n_Not shown: the standalone splits stage `{splits_run.name}` "
                    f"recorded a different cohort for this stage ({', '.join(differing)}), "
                    "because it ran under an earlier cohort setting. This evaluation "
                    "scored the population above, so the two are not interchangeable._"
                )
    scope = own_denoms or {}
    if scope.get("cohort_capped") is False or (
        not scope and protocol.max_users is None
    ):
        cohort_scope = (
            "**Cohort scope:** every history-eligible user was scored; no cap was "
            "applied. The specification allowed a 5,000-user seeded cap as a compute "
            "fallback, and decision D-022 records why it was not used."
        )
    else:
        cap = scope.get("cohort_cap", protocol.max_users)
        cohort_scope = (
            f"**Cohort scope:** capped at {cap} users drawn with seed "
            f"{scope.get('cohort_seed', protocol.cohort_seed)} from the history-eligible "
            "cohort **before** labels were examined."
        )
    stage_cfg = protocol.stages
    body = f"""**The temporal protocol, locked before any result was produced:**

| stage | history | labels |
|---|---|---|
| validation | everything before {stage_cfg['validation'].history_end_exclusive} | {stage_cfg['validation'].label_start} to {stage_cfg['validation'].label_end_inclusive} |
| final | everything before {stage_cfg['final'].history_end_exclusive} | {stage_cfg['final'].label_start} to the dataset's observed endpoint |

At both cutoffs:

- a candidate recipe must have been **submitted** before the cutoff, so no recipe enters
  the catalogue through the very review being predicted;
- user profiles and the popularity baseline read history events only;
- anything the user interacted with before the cutoff — including an unrated (0) event —
  is **seen** and is removed from the candidate set;
- warm-user eligibility is at least {protocol.min_distinct_positive_history} distinct
  positively rated recipes, computed from history alone, **before** any label is examined;
- ranking metrics are reported only for users with at least one eligible novel positive in
  the label window. That conditional population is stated with every result.

**Positive rating definition:** {protocol.positive_ratings}.
Ratings {protocol.observed_nonpositive_ratings} are observed non-positive.
Rating {protocol.unknown_rating_value} is **unknown / unrated** — never a zero-star
dislike, never inferred positive from review text. Unreviewed recipes are not negatives:
the data records ratings, not a complete account of what each user liked.

{cohort_scope}

### Table 3 — Split and user eligibility

"""
    if split_tbl is not None:
        if own_denoms and split_src.startswith(run_id):
            body += (
                f"_From run `{run_id}`'s own `metrics/split_denominators.json`: the "
                "population this evaluation actually scored._\n\n"
            )
        elif split_src != run_id:
            body += f"_From run `{split_src}`, the splits stage this evaluation consumed._\n\n"
        body += to_markdown(split_tbl, max_rows=50)
        body += split_note
    else:
        body += PENDING
    parts.append(_section("3. Temporal split and evaluation population", body))

    # ---------------------------------------------------------------- 4. AI layer
    enc = _read_json(metrics / "encoder_provenance.json") or {}
    body = f"""**Model:** `{enc.get('model_id', cfg.model.encoder.model_id)}`
**Pinned revision:** `{enc.get('model_revision', cfg.model.encoder.model_revision)}`
**Dimension:** {enc.get('dimension', '—')} · **Device:** {enc.get('device', '—')} ·
**Max input:** {cfg.model.encoder.max_seq_length} wordpieces
**Library versions:** sentence-transformers {enc.get('sentence_transformers_version', '—')},
transformers {enc.get('transformers_version', '—')}, torch {enc.get('torch_version', '—')}

**What the encoder is:** a frozen pretrained text encoder. It is not a generative model,
does not predict ratings, and is never fine-tuned here.

**What it reads:** a deterministic string per recipe, in a fixed order —
name, ingredients, whitelisted descriptive tags, short description. Nothing else. In
particular no review text, no user id, no rating, no popularity, no review count, no
timestamp, no contributor id, no administrative or duration tag. Duration tags are excluded
deliberately: they encode the preparation-time band, which is the axis the constraint acts
on, so admitting them would confound the relevance score with the constraint dimension.

**User profile:** the normalised mean of the vectors of recipes the user rated 4 or 5
before the cutoff, with equal weights. No weights were tuned after seeing test results.

**Score:** `s(u,i) = (1 + cosine(p_u, e_i)) / 2`, which lands in [0, 1] by construction.
Clipping only absorbs floating-point drift.

**What the score means:** {SCORE_MEANING}

**Limitation to state in the paper.** The encoder postdates the review period and was
pretrained on public web text that may include Food.com content. This is retrospective
offline benchmarking, not a system that could have been deployed in 2016.
"""
    parts.append(_section("4. The AI scoring layer", body))

    # ---------------------------------------------------------------- 5. LPP
    band_defs = "\n".join(
        f"- **{label}**: {desc}"
        for label, desc in __import__(
            "foodcom.models.bands", fromlist=["band_bounds_text"]
        ).band_bounds_text(protocol).items()
    )
    body = f"""For user *u*, over eligible unseen candidate recipes *C_u* with relevance
scores *s_ui*:

```
maximise    Σ_{{i ∈ C_u}} s_ui · x_i

subject to  Σ_{{i ∈ C_u}} x_i = k                     (exactly k recipes)
            Σ_{{i ∈ G_g}}  x_i ≤ b_g   for every band g   (variety cap)
            0 ≤ x_i ≤ 1                              (continuous)
```

with **k = {k}** and **b_g = {b}** for every band.

**The four disjoint preparation-time bands**, from reported minutes:

{band_defs}

**Deliberately absent:** price constraints, summed calories, total preparation-time limits,
pairwise diversity penalties, overlapping quota groups, transportation costs. Each either
requires data this dataset does not contain, or destroys the structure the next section
depends on.

**Feasibility rule.** Before solving, check `Σ_g min(b_g, |G_g ∩ C_u|) ≥ k`. This is exact:
it holds if and only if a feasible shortlist exists. A user who fails it is recorded as
structurally infeasible and reported separately — never rescued by quietly relaxing a cap.

**Solver:** `scipy.optimize.linprog(method="highs-ds")`. SciPy minimises, so the objective
vector passed to it is `c = −s`. Tolerance {cfg.model.solver.tolerance:g} on the equality
residual, the bounds, the capacities and the distance to the nearest integer.

### Why a continuous LP returns whole recipes

{ARGUMENT_SUMMARY}

This guarantee is checked on every single solve rather than assumed, and cross-checked
against three independent oracles: exhaustive enumeration on small cases, a score-sorted
capacity-respecting greedy oracle, and the identity that with every `b_g = k` the LP
optimum must equal the unconstrained top-k sum.

**The honest claim.** {HONEST_CLAIM}
"""
    parts.append(_section("5. The linear programme", body))

    # ---------------------------------------------------------------- 6. duality
    dual_tbl = _read_csv(tables / "t10_primal_dual_verification.csv")
    body = f"""With α free for the exact-size equality, β_g ≥ 0 for each band cap and
γ_i ≥ 0 for each upper bound x_i ≤ 1:

```
minimise    k·α + Σ_g b_g·β_g + Σ_i γ_i
subject to  α + β_g(i) + γ_i ≥ s_ui      for every eligible i
```

**What β_g means:** {BETA_MEANING}

**What it does not mean:** it is not money, not cognitive load, not a psychological
benefit, and not a measure of user welfare.

**A caution for the viva.** At a kink or a tied optimum the shadow value is not unique. For
any whole-number change to a cap, the model is **re-solved** and the actual score change
reported; a local marginal is never extrapolated to a whole extra slot.

### Table 10 — Primal-dual verification (one real user)

"""
    body += to_markdown(dual_tbl, max_rows=30) if dual_tbl is not None else PENDING
    parts.append(_section("6. Duality", body))

    # ---------------------------------------------------------------- 7. methods
    body = "All four methods see the same users, the same eligible catalogue and the same "
    body += "shortlist length. Only the score and the caps differ.\n\n"
    for name in ["RANDOM", "POPULARITY_LP", "AI_TOPK", "AI_LP"]:
        body += f"- **{name}** — {METHOD_DESCRIPTIONS[name]}\n"
    body += f"""
**Metric definitions.** With *R_u* the set of eligible novel recipes the user rated 4 or 5
in the label window, and *L_u* the ranked k-item output:

```
Recall@k = |L_u ∩ R_u| / |R_u|
DCG@k    = Σ_{{j=1..k}} 1[item_j ∈ R_u] / log₂(j+1)
NDCG@k   = DCG@k / IDCG@k,   IDCG@k = Σ_{{j=1..min(k,|R_u|)}} 1 / log₂(j+1)
```

Both are macro-averaged per user, never review-weighted. They are reported only for users
with |R_u| > 0, and that conditional population is stated alongside.

**Reduction ratio.** {REDUCTION_MEANING}

**Runtimes.** {RUNTIME_MEANING}
"""
    parts.append(_section("7. The four comparison methods and the metrics", body))

    # ---------------------------------------------------------------- 8. results
    comp = _read_csv(tables / "t04_method_comparison.csv")
    paired = _read_csv(tables / "t05_paired_differences.csv")
    feas = _read_csv(tables / "t08_feasibility_and_failures.csv")
    body = f"### Table 4 — Method comparison (k={k}, b={b})\n\n"
    body += to_markdown(comp) if comp is not None else PENDING
    body += "\n\n### Table 5 — Preplanned paired differences with bootstrap intervals\n\n"
    body += (
        interval_meaning(
            protocol.bootstrap_ci, protocol.bootstrap_resamples, protocol.bootstrap_seed
        )
        + "\n\n"
    )
    body += to_markdown(paired) if paired is not None else PENDING
    body += "\n\n### Table 8 — Feasibility and failures\n\n"
    body += (
        "A method that failed on a **feasible** input is charged recall zero in the primary "
        "table: dropping difficult users would flatter whichever method fails most. A "
        "**structurally infeasible** profile is different — no valid k-item shortlist "
        "exists at all — and is reported separately, with the coverage loss shown. A "
        "common-success table, restricted to users where every method worked, accompanies "
        "the primary one rather than replacing it.\n\n"
    )
    body += to_markdown(feas) if feas is not None else PENDING
    parts.append(_section("8. Results", body))

    # ---------------------------------------------------------------- 9. sensitivity
    s_len = _read_csv(tables / "t06_sensitivity_length.csv")
    s_cap = _read_csv(tables / "t07_sensitivity_cap.csv")
    body = "Both sweeps were declared in `config/research.yaml` before any result was seen.\n\n"
    body += "### Table 6 — Shortlist-length sensitivity (k=4/b=2, k=6/b=3, k=8/b=4)\n\n"
    body += to_markdown(s_len) if s_len is not None else PENDING
    body += "\n\n### Table 7 — Band-cap sensitivity (k=6 with b=2, 3, 6; b=6 removes the cap)\n\n"
    body += to_markdown(s_cap) if s_cap is not None else PENDING
    parts.append(_section("9. Sensitivity analysis", body))

    # ---------------------------------------------------------------- 10. worked example
    worked = _read_csv(tables / "t09_worked_lpp_example.csv")
    example = _read_json(metrics / "worked_example.json") or {}
    body = ""
    if example:
        vr = example.get("solution", {}).get("verification", {})
        fe = example.get("solution", {}).get("feasibility", {})
        body += f"""**User:** demo label `{example.get('user_label', '—')}`
(the real id is archived in the run directory and is not printed here)
**Eligible unseen candidates:** {example.get('solution', {}).get('n_candidates', '—'):,}
**Objective value:** {example.get('solution', {}).get('objective_value', float('nan')):.6f}
**Band usage:** `{example.get('solution', {}).get('band_usage')}`
**Reachable capacity Σ_g min(b_g, |G_g|):** {fe.get('reachable_capacity')} (needs ≥ {k})
**Solver status:** {vr.get('solver_message', '—')}
**Equality residual:** {vr.get('equality_residual', float('nan')):.3g} ·
**Max distance to an integer:** {vr.get('max_distance_to_integer', float('nan')):.3g} ·
**Tolerance:** {vr.get('tolerance', float('nan')):g}
**All structural checks passed:** {vr.get('checks_passed')}

"""
    body += "### Table 9 — Worked shortlist\n\n"
    body += to_markdown(worked) if worked is not None else PENDING

    slice_json = _read_json(metrics / "graphical_slice.json")
    body += "\n\n### The two-variable graphical slice\n\n"
    if slice_json:
        body += f"{slice_json['explanation']}\n\n"
        body += "Figure: `figures/fig09_graphical_method_slice.png`\n\n"
        body += (
            "This is a **slice** of the full model, with all but two selection variables "
            "held fixed. It illustrates why a linear objective over this feasible set is "
            "optimised at a vertex; it is not a claim that the model has two variables.\n"
        )
    else:
        body += PENDING
    parts.append(_section("10. One worked real example", body))

    # ---------------------------------------------------------------- 11. figures
    fig_index = _read_json(run_dir / "figures" / "index.json")
    if fig_index:
        rows = "\n".join(
            f"| `{f['name']}` | {f['units']} | `{Path(f['underlying_csv']).name}` |"
            for f in fig_index
        )
        body = (
            "Every figure below has a title, explicit units, a caption and the CSV it was "
            "drawn from, all inside the run directory.\n\n"
            "| figure | units | underlying data |\n|---|---|---|\n" + rows + "\n\n"
        )
        body += "\n".join(f"**{f['name']}** — {f['caption']}\n" for f in fig_index)
    else:
        body = PENDING
    parts.append(_section("11. Figures", body))

    # ---------------------------------------------------------------- 12. limitations
    limitations = cfg.path("docs_dir") / "LIMITATIONS.md"
    if limitations.exists():
        inlined = limitations.read_text(encoding="utf-8").split("---", 1)[-1].strip()
        # Demote the inlined headings by one level so they nest under section 12 instead of
        # breaking the pack's own numbering.
        body = "\n".join(
            ("#" + line) if line.startswith("## ") else line for line in inlined.splitlines()
        )
    else:
        body = "See `docs/LIMITATIONS.md`."
    parts.append(_section("12. Limitations", body))

    # ---------------------------------------------------------------- 13. claim discipline
    parts.append(_section("13. Statements you must not make", STATEMENTS_TO_AVOID))

    # ---------------------------------------------------------------- 14. prompts
    parts.append(
        _section(
            "14. Interpretation prompts",
            """These are questions for you to answer in the discussion, not answers. The
technical work does not settle any of them.

1. Look at Table 4. Which method retrieved the most later positive ratings, and by how much
   in **absolute** terms? If a baseline is near zero, a large relative lift means very
   little — say the absolute number.
2. Look at Table 5. Does either interval exclude zero? If an interval contains zero, that
   is *not* evidence the methods are equivalent; say only that this benchmark did not
   separate them.
3. Compare AI_LP with AI_TOPK. AI_TOPK optimises the same score over a larger feasible set,
   so its total relevance score is at least AI_LP's by construction. Any difference in
   *recall* is therefore about which items the caps forced in or out — is that a cost, a
   benefit, or neither?
4. Look at Figure 7. Is there a measurable trade-off between band coverage and recall? A
   trade-off, a null difference, and popularity beating the AI are all acceptable findings.
5. Look at Table 7. What happens when the cap is removed (b = 6)? If the capped and
   uncapped results barely differ, what does that say about how often the cap actually
   bound?
6. Look at Table 8. How many users could not be served at all, and does that change who the
   headline number describes?
7. Connect back to the choice-overload literature carefully. It motivates *why*
   shortlisting might matter. It cannot supply an outcome this study did not measure.""",
        )
    )

    # ---------------------------------------------------------------- 15. reproduction
    pkg = manifest.get("packages", {})
    code = manifest.get("code", {})
    ds_files = manifest.get("dataset_files", [])
    ds_md = "\n".join(
        f"- `{f.get('path')}` — SHA-256 `{f.get('sha256')}`" for f in ds_files
    ) or "_(none recorded)_"
    body = f"""**Run id:** `{run_id}`
**Config fingerprint (SHA-256):** `{manifest.get('config_sha256')}`
**Code revision:** `{code.get('revision')}` on branch `{code.get('branch')}`
(working tree dirty: `{code.get('dirty')}`)
**Python:** {manifest.get('python')} on {manifest.get('platform', {}).get('system')}
**Seeds:** `{manifest.get('seeds')}`
**Model revision:** `{manifest.get('model_revision')}`

**Data files this run read:**

{ds_md}

**Package versions:**

{chr(10).join(f'- {name}: {version}' for name, version in sorted(pkg.items()))}

To reproduce: check out the code revision above, place the same raw files (the hashes must
match), restore `runs/{run_id}/config/config_snapshot.json` over `config/`, and run
`python tasks.py final`. Same seeds, same config, same numbers.
"""
    parts.append(_section("15. How to reproduce every number here", body))

    out = out_path or (cfg.path("docs_dir") / "RESULTS_PACK.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    log.info("results pack written to %s", out)
    return out
