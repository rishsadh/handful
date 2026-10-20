# Technical methods

Written so that Khushi can describe the method accurately without reading Python, and so
that a reviewer can check that each choice does what it claims. Every design decision that
could plausibly have gone the other way says *why* it went this way.

---

## 1. Acquisition and provenance

The two files come from one selected Kaggle release by Shuyang Li. Nothing is downloaded
automatically: Kaggle needs the user's own authenticated session, and an unofficial mirror
is not the same artifact.

Recorded at acquisition: source URL, uploader, version number, download date, licence
wording, file sizes and SHA-256 hashes. `scripts/acquire_data.py` refuses to write a
manifest while any of version, download date or licence text still reads `UNRECORDED` — a
dataset we cannot name a version and a licence for is not a citable source.

Redistribution permission is `true`, `false` or `null`. `null` means unknown and is treated
as **no**. Permission has to be established from the dataset licence itself, never inferred
from a code licence in the same repository.

Raw bytes are immutable. Every transformation writes to `data/interim` or `data/processed`.

## 2. Audit

The audit reads and reports; it modifies nothing. Its purpose is to make each later
cleaning rule justifiable against evidence rather than habit.

It computes row counts, unique ids, date ranges, column types, missingness, exact
duplicates, conflicting recipe ids, repeated user–recipe pairs, invalid dates and ratings,
orphan joins, join coverage, the ratings distribution including zero, the minutes
distribution with the 15/30/60 boundary counts, band composition, list-field parse
outcomes, missing descriptions, nutrition array lengths, interactions dated before
submission, and the distribution of usable positive history per user. It also exports the
full tag vocabulary with whitelist status, which is what makes completing
`config/tag_rules.yaml` an evidence-based act rather than guesswork.

Finally it produces a **coverage verdict**: are the locked 2017/2018 windows workable
against these bytes? If not, the specification requires a diagnosed, recorded and approved
replacement window — never a silent one.

## 3. Cleaning

Two principles: nothing disappears without a count, and ambiguity is quarantined rather
than resolved by convenience.

**Recipes.** Exact duplicate rows dropped. Rows sharing a recipe id but disagreeing on
name, minutes, submitted, ingredients or steps are **quarantined**, not resolved keep-first
— keep-first would silently pick a version. Identical repeats collapse to one row. A recipe
enters the core catalogue only with a valid id, a name, a valid submitted date, positive
finite minutes and a parsable non-empty ingredient list.

Serialised list fields are parsed with `ast.literal_eval`, which evaluates literals only —
no names, no calls, no attribute access. Plain `eval` over 230k rows of third-party text
would be a remote-code-execution surface, and is never used. Raw strings and a parse status
are retained alongside every parsed value.

Long durations are **flagged, not deleted**. No IQR trimming is applied: marinating,
chilling and slow cooking are legitimate, and an IQR rule would quietly delete an entire
band. Nutrition is retained with its length checked but its units unverified, and is not
used in the core model. No prices, servings, health classifications or allergen labels are
invented.

**Interactions.** Review text is separated immediately. Exact duplicates dropped. Missing
keys, unparsable dates and out-of-range ratings are quarantined. Orphan recipe joins are
dropped with counts, and the recipe key's uniqueness is asserted so a join can never
multiply interaction rows.

For repeated `(user, recipe)` pairs the **earliest** event is retained: a later,
contradicting rating is never averaged into the earlier history. Tied earliest dates with
conflicting ratings make the pair unusable as a label but the recipe still counts as
**seen**. Interactions dated before the recipe's submission are excluded as unresolved
inconsistencies.

Rating semantics, stated once and never contradicted: 4–5 positive, 1–3 observed
non-positive, **0 unknown/unrated** — not a zero-star dislike, and never inferred positive
from review text. The data records ratings, not a complete account of what each user liked;
an unreviewed recipe is not a negative.

## 4. The temporal protocol

| stage | history | labels |
|---|---|---|
| validation | everything before 2017-01-01 | calendar 2017 |
| final | everything before 2018-01-01 | 2018 → the observed endpoint |

Three rules do the real work, and each exists to stop a specific way of accidentally
cheating:

1. **Catalogue availability.** A candidate must have been *submitted* before the cutoff.
   Otherwise a recipe enters the catalogue through the very review we are predicting.
2. **History-only features.** Profiles and the popularity baseline read history events
   only. One future rating leaking into a profile makes every downstream metric
   meaningless.
3. **Cohort before labels.** Warm-user eligibility — at least five distinct positively
   rated recipes — is computed from history alone, *before* any label is examined. Choosing
   who to evaluate after seeing their future is selection on the outcome.

Anything a user interacted with before the cutoff, **including an unrated (0) event**, is
seen and removed from the candidate set. Recommending something already reviewed is not a
novel recommendation.

Ranking is against the **full frozen eligible catalogue**. No sampled negatives: sampled
metrics systematically distort the ranking of recommenders (S8), and the extra compute is
worth an undistorted denominator.

Scope: **all eligible users.** The specification allows a 5,000-user seeded sample if
compute requires it; measured against the real data it does not, and the cap cost four
fifths of the evaluated population (validation 202 → 812 rankable users, final 126 → 530).
Only ranking-eligible users are ever scored, so the uncapped run costs minutes. Recorded as
D-022.

Reported denominators: history-eligible users, the selected cohort, cohort users with any
future event, ranking-eligible users, users with a feasible shortlist, and the final paired
metric denominator.

## 5. The AI layer

`sentence-transformers/all-MiniLM-L6-v2`, frozen. Not a generator, not fine-tuned, not a
rating predictor. Pinned: model revision, sentence-transformers version, transformers
version, torch version, device, precision and the 256-wordpiece input limit. The fraction
of texts truncated is measured with the real tokeniser, or reported as unmeasured — never
guessed from character counts.

**Rendered text**, in fixed order: `name | ingredients | whitelisted tags | short
description`. Excluded by construction: review text, user ids, ratings, popularity, review
counts, timestamps, contributor ids, administrative tags. Duration tags
(`60-minutes-or-less`, `time-to-make`, `weeknight`) are excluded deliberately — they encode
the preparation-time band, which is the axis the constraint acts on, so admitting them
would confound the relevance score with the constraint dimension. A unit test asserts a
forbidden field cannot appear.

The rendered string is hashed, and the hash is part of the embedding cache key
`(recipe_id, text_sha256, model_id, model_revision)`. All four matter: a re-render after a
tag-rule change is a different text, and the same text under a different revision is a
different vector.

**Profile.** `p_u` = normalised mean of the unit vectors of recipes rated 4–5 before the
cutoff, equal weights, no post-test tuning. A user with no usable positive history, or
whose vectors cancel to a zero norm, is flagged **cold** and excluded from every warm-user
AI claim. The demo may show a cold profile a clearly labelled popularity fallback.

**Score.** `s(u,i) = (1 + cos(p_u, e_i)) / 2 ∈ [0,1]`. Both operands are unit vectors, so
the cosine is a dot product and the range holds by construction; clipping absorbs
floating-point drift only, and a value meaningfully outside raises rather than being
clamped.

**A limitation to state in the paper.** The encoder postdates the review period and was
pretrained on public web text that may include Food.com content. This is retrospective
offline benchmarking, not a system that could have been deployed in 2016.

## 6. The linear programme

```
maximise    Σ_{i ∈ C_u} s_ui · x_i
subject to  Σ_{i ∈ C_u} x_i = k                            k = 6
            Σ_{i ∈ G_g}  x_i ≤ b_g   for each band g       b = 3
            0 ≤ x_i ≤ 1
```

Bands from reported minutes, upper-inclusive and disjoint: `G1: 0 < m ≤ 15`,
`G2: 15 < m ≤ 30`, `G3: 30 < m ≤ 60`, `G4: m > 60`.

**Deliberately absent:** price constraints, summed calories, total preparation-time limits,
pairwise diversity penalties, overlapping quota groups, transportation costs. Each either
requires data this dataset does not contain, or destroys the partition structure the
integrality guarantee rests on. No transportation-cost analysis is performed: the dataset
has no genuine supply, destination and shipping-cost problem, and the flow argument below is
a proof device, not shipping data.

**Feasibility.** `Σ_g min(b_g, |G_g ∩ C_u|) ≥ k`, checked before every solve. Exact: it
holds if and only if a feasible shortlist exists. A user who fails it is recorded as
structurally infeasible and reported separately — never rescued by quietly relaxing a cap.

**Solver.** `scipy.optimize.linprog(method="highs-ds")`. SciPy minimises, so `c = −s`.
`highs-ds` is dual simplex, which returns a *basic* solution — necessary, because a
non-basic optimum at a tie can be fractional even when an integral optimum exists.

**A practical limit, measured.** `highs-ds` does not converge on the unpruned catalogue
problem: 229,279 columns against 5 rows runs for minutes and returns `success=False`. That
reproduces on a synthetic problem of identical shape, so it is a solver limitation rather
than a property of the data. Every solve therefore runs on the pruned problem, which is
exact here, and optimality over the full candidate set is established by the dual
certificate below rather than by asking the simplex to converge.

**Verification, on every solve:** solver success, equality residual, bound violations, band
capacity violations, exactly `k` unique items, and the maximum distance to the nearest
integer. Tolerance `1e-7`. A fractional result is a **failed structural test**, recorded as
such — never permission to round.

**Ranking.** The LP returns a set; NDCG needs positions. The set is ordered by score
descending, then recipe id ascending.

**Tie handling.** POPULARITY_LP produces ties in bulk (most recipes share a positive-review
count of zero) and the solver may return any equally optimal set. Rather than perturbing
the scores — which would silently change the objective — the optimum is recomputed with the
documented lexicographic rule and accepted **only after** its objective is confirmed equal
to the LP's. The score definition is untouched; only the choice among equally optimal sets
becomes deterministic.

**Pruning.** For the primal shortlist only, at most the top `b_g` candidates per band are
kept. This is exact here: no optimum can use a `(b_g + 1)`-th best candidate in band `g`,
because it could be swapped for a better-scoring one in the same band without touching a
constraint. Evaluation denominators still use the full catalogue, and reported dual
certificates come from the full unpruned problem, since pruning removes the constraints
whose sensitivity we want to interpret.

## 7. Why continuous variables return whole recipes

Map the model to a min-cost flow: a source supplies `k` units; source→group arcs have
capacity `b_g`; group→recipe arcs have unit capacity and cost `−s_ui`; recipe→sink arcs have
unit capacity. Because the bands **partition** the candidates, every recipe node has exactly
one parent group, the incidence matrix is totally unimodular, and with integer supplies and
capacities a basic optimal flow is integral. Projecting the group→recipe flows gives the
selection variables.

**Boundaries.** This justifies *our* model, not arbitrary LPs. It breaks under overlapping
quota groups, pairwise penalties, or general weighted resource constraints. None may be
added without revising the protocol.

**Independent checks**, run against the LP: exhaustive enumeration of feasible `k`-subsets
on tiny cases; a score-sorted capacity-respecting greedy oracle; and the identity that with
every `b_g = k` the LP optimum equals the unconstrained top-k sum. All compare **objective
values**, not sets — at a tie two different sets can both be optimal, and demanding set
equality would fail a correct solver.

**The honest claim.** Greedy also solves this restricted case. The LP is not claimed to be
computationally necessary. Its contribution is a transparent formulation, an exact
feasibility condition, a certified optimum and an interpretable dual.

## 8. Duality

```
minimise    k·α + Σ_g b_g·β_g + Σ_i γ_i
subject to  α + β_g(i) + γ_i ≥ s_ui     for every eligible i
            β_g ≥ 0,  γ_i ≥ 0,  α free
```

**How the certificate is obtained.** Solving this dual directly is not viable at catalogue
scale either — it carries one constraint per candidate, so the real problem is a
229,279-constraint LP. Instead it is solved on a top-`(b_g + 2)`-per-band subproblem and
`gamma` is extended to every remaining candidate in closed form,
`gamma_i = max(0, s_i − alpha − beta_g(i))`, which is dual-feasible on all `n` constraints
by construction.

That margin is not arbitrary. At most `b_g` items per band are selected, so the
highest-scoring *non-selected* item in a band is ranked at most `b_g + 1`, and its score is
what pins `alpha + beta_g` from below. Keeping only `b_g` disagreed with the directly
solved dual on **22 of 273** random problems, worst gap 0.57. At `b_g + 1` the disagreement
is **0 of 273**, worst gap exactly zero.

**Why this is stronger than running the full simplex.** A primal-feasible `x*`, a
dual-feasible `(alpha, beta, gamma)` satisfying all `n` constraints, and equal objectives
together *prove* `x*` optimal by weak duality. That is a certificate checked against every
constraint, not a solver run that happened to terminate.

Two independent routes are computed and compared: solving the dual LP directly, and reading
SciPy's marginals off the primal and converting their signs. The conversion matters: SciPy
minimised `−s`, so a reported marginal is `d(min objective)/d(rhs)` and the effect on the
*maximised* score is its negative. Getting that backwards turns "this cap costs you 0.03 of
score" into "this cap gains you 0.03". It is verified against a re-solved finite
perturbation rather than trusted as algebra.

Checked: strong duality within tolerance, dual feasibility, and complementary slackness
(`β_g × cap slack`, `γ_i × (1 − x_i)`, `x_i × dual-constraint slack`).

**Interpretation.** A positive `β_g` means the band-`g` cap is locally binding — holding
the model's total relevance score below what it would otherwise reach — in **AI relevance
score units**. It is not money, not cognitive load, not a psychological benefit, not user
welfare. At a kink or a tied optimum the shadow value is not unique, so any whole-number cap
change reported is **re-solved**, never extrapolated from a local marginal.

## 9. The graphical slice

Optional syllabus material, not the solver. Take a solved real case, hold `k−1` selections
fixed, and let two candidates that both fit the remaining band capacity compete for the last
position. The equality becomes `x_a + x_b = 1`, so the feasible region is the segment from
`(1,0)` to `(0,1)` in the unit square; a linear objective is maximised at an endpoint.
Exported as PNG + CSV + caption + explanation, labelled a **slice** of the full model
everywhere it appears.

## 10. Comparison methods

All four see the same users, the same eligible catalogue and the same shortlist length.

- **RANDOM** — shuffle the catalogue with a fixed seed, accept recipes in that order while
  their band has room. *Random-priority feasible selection*, not a uniform sample over
  feasible shortlists, and never described as one. Twenty seeded repeats per user, averaged
  within the user. The shuffle order is the ranking: re-sorting by score would import the
  very signal this baseline is meant to lack.
- **POPULARITY_LP** — pre-cutoff positive-review counts, same capped LP, ties by ascending
  recipe id.
- **AI_TOPK** — the six highest AI scores, **no caps**. An ablation that isolates the effect
  of the constraints. It is expected to violate the caps; that is reported transparently and
  is not a solver bug. For identical scores its total relevance upper-bounds AI_LP, because
  it optimises the same objective over a superset of the feasible region.
- **AI_LP** — the proposed method.
- **TFIDF_LP** — optional, separately labelled ablation. Never a silent substitute for the
  sentence-transformer model.

## 11. Metrics

```
Recall@k = |L_u ∩ R_u| / |R_u|
DCG@k    = Σ_{j=1..k} 1[item_j ∈ R_u] / log₂(j+1)
NDCG@k   = DCG@k / IDCG@k,   IDCG@k = Σ_{j=1..min(k,|R_u|)} 1 / log₂(j+1)
```

Macro-averaged per user, never review-weighted: a review-weighted mean would let the handful
of users with hundreds of reviews decide the headline number. Reported only for users with
`|R_u| > 0`, and that conditional population is stated alongside — averaging users with no
observed positive in as zeros would make the number depend on how many such users exist.

Also reported: bands represented, exact-size success, feasibility, cap violations under each
method's declared rules, candidate-catalogue size, solver status, and separate runtimes for
scoring, solving and the full request.

`reduction_ratio = 1 − k/|C_u|` is a descriptive identity about the arithmetic. It is not
evidence about attention, effort or psychological overload. Runtimes are machine runtimes,
never human decision times.

## 12. Statistics

Preplanned, before any result was seen: `AI_LP − POPULARITY_LP` and `AI_LP − AI_TOPK`, for
Recall@6 and NDCG@6, on the same users within each comparison.

Percentile bootstrap over **users**: 2,000 resamples, seed 42, each resample drawing users
with their whole paired record. The user is the unit that varies; resampling
`(user, method)` rows independently would break the pairing and understate the correlation
between methods that share a catalogue. RANDOM's 20 repeats are averaged within each user
first — they are 20 looks at one user, not 20 users.

**A post-hoc diagnostic, disclosed.** Validation returned Recall@6 = 0.000 for three of the
four methods, so the primary metric barely discriminates on this task.
`scripts/rank_diagnostic.py` reports where each scorer places the user's best true positive,
which separates "weak" from "inert". It was written after seeing that result and is
disclosed as post-hoc in D-023: Recall@6 remains primary and NDCG@6 secondary with nothing
swapped, the script sits outside the pipeline so it cannot change a reported number, and it
carries no test, interval or significance claim.

Formal p-values are not part of this protocol. If the professor requests one, the test and
any correction must be specified before the final test set is touched. A test is never
chosen after seeing which one produces significance.

**Reading the intervals honestly.** They describe resampling uncertainty within this
benchmark, on this catalogue, for this cohort. Users share recipes and were not sampled from
any population of interest. An interval containing zero is **not** evidence of equivalence;
"preserved quality" needs a non-inferiority margin declared in advance, which this protocol
does not have. Where a baseline is near zero, report the absolute difference — a relative
lift on a tiny base is a headline, not a finding.

**Failures.** A method that fails on a *feasible* input is charged recall zero in the
primary table; dropping difficult users would flatter whichever method fails most. A
*structurally infeasible* profile is different — no valid `k`-item shortlist exists at all —
and is reported separately with the coverage loss shown. A common-success table, restricted
to users where every method worked, accompanies the primary one rather than replacing it.

## 13. Sensitivity

Predeclared in `config/research.yaml`:

- length sweep: `(k=4, b=2)`, `(k=6, b=3)`, `(k=8, b=4)`
- cap sweep: `k=6` with `b=2, 3, 6` — `b=6` removes the effective cap

Within a sweep, users, profiles, candidate rules, scores, dates and the positive-rating
definition are all held fixed; only `k` and `b` move. Infeasibility is recorded, not
dropped: a tighter cap makes some users structurally infeasible, and losing them silently
would make the tighter cap look better than it is by removing the users it hurt.

## 14. Reproducibility

Every run creates `runs/<run_id>/` with the configuration snapshot and its SHA-256, dataset
file hashes, git revision and dirty state, package versions, model revision, all seeds,
start and completion times, logs, metrics, tables, figures and recorded failures. Every
table and figure carries its run id.

The final evaluation is gated twice: `config/FROZEN.lock` must exist and match the current
configuration's hash, and the test suite must pass. If a genuine software bug is found
afterwards, it is fixed transparently, the reason for rerunning is recorded in
`docs/DECISION_LOG.md`, and the new run takes a new id — the superseded result is preserved
as evidence about the project's history.

## 15. Synthetic fixtures

`src/foodcom/testing/` generates synthetic files shaped like the real ones, injecting every
messy case the cleaning rules claim to handle. They exist so the pipeline, the LP, the
duality checks and the metrics can be exercised deterministically before the data gate is
passed.

They are never research data. The evaluation harness refuses to emit numbers from a
non-research-grade encoder unless a test explicitly opts in, and the demo displays a
permanent warning banner on every screen when it is pointed at a synthetic workspace.
