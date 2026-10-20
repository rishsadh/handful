# Results Pack — Food.com recipe shortlisting

**For:** the researcher (research writing, interpretation, submission)
**Prepared by:** the technical pipeline in `handful`, run `final-20260911T120041Z-5af9c102`
**Protocol version:** 2.0.0
**Run status:** completed
**Started / completed (UTC):** 2026-09-11T12:00:41.511029+00:00 → 2026-09-11T13:15:23.978012+00:00

Every number below can be traced to run `final-20260911T120041Z-5af9c102`. The run directory holds the exact
configuration, the dataset hashes, the code revision, the package versions and the logs
that produced it. If a number here disagrees with the run directory, the run directory is
right.

This pack does not contain interpretation, discussion or conclusions. Those are yours to
write. What it contains is what the code computed and what those quantities mean.


## 1. Dataset identity, licence and provenance

**Dataset:** Food.com Recipes and Interactions
**Uploader:** Shuyang Li (shuyangli94)
**Source:** <https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions>
**Kaggle version:** 2
**Download date:** 2026-09-06
**Licence, as stated by the source:**

> Data files (c) Original Authors

**Redistribution permitted:** False
(`null` means unknown, and unknown is treated as "no". Permission to redistribute raw data
or review text has to be established from the licence itself, not inferred from a code
licence in the same repository.)

**Files, hashed at acquisition:**

- `RAW_recipes.csv` — 294,520,189 bytes — SHA-256 `6a8136d1da9e03396a9f52d72200b3fddb8fe103f11e1496effca30ac4e0539f`
- `RAW_interactions.csv` — 349,436,524 bytes — SHA-256 `4e278d2f687b1020f5694e51003a7d6174344b51aebbdf4530de88b5c6a78ee4`

Raw bytes are immutable. Every transformation writes to `data/interim` or `data/processed`.

**A note on counts.** The source paper's widely quoted 180K+/700K+ figures describe *its
filtered task corpus*; it reports collecting 230K+ recipes and 1M+ reviews before
filtering. Neither number is ours. Every count in this pack was computed from the
downloaded files listed above under our own documented rules.


## 2. Audit and cleaning

### Table 1 — Raw dataset audit

_From run `audit-20260906T164448Z-4c524298`, the audit stage this evaluation consumed._

| quantity | value |
| --- | --- |
| recipes: raw rows | 231637 |
| recipes: unique ids | 231637 |
| recipes: exact duplicate rows | 0 |
| recipes: conflicting ids | 0 |
| recipes: submitted date range | 1999-08-06 00:00:00 .. 2018-12-04 00:00:00 |
| recipes: non-positive minutes | 1094 |
| recipes: missing/blank description | 2.1508 |
| interactions: raw rows | 1132367 |
| interactions: unique users | 226570 |
| interactions: unique recipe ids | 231637 |
| interactions: exact duplicate rows | 0 |
| interactions: repeated user-recipe pairs | 0 |
| interactions: date range | 2000-01-25 00:00:00 .. 2018-12-20 00:00:00 |
| interactions: rating 0 (unknown) | 60847 |
| interactions: positive (4-5) | 1003724 |
| interactions: observed non-positive (1-3) | 67796 |
| interactions: orphan recipe joins | 0 |
| interactions: dated before submission | 1246 |
| recipe id is a unique key | True |

### Table 2 — Cleaning and exclusion ledger

Read this top to bottom. Each row is one ordered stage; `n_removed` is what that stage excluded and `reason` is why. The ledger reconciles the raw download to the final catalogue with no unexplained gap.

_From run `clean-20260906T165026Z-269a4986`, the clean stage this evaluation consumed._

| entity | order | stage | n_in | n_out | n_removed | reason |
| --- | --- | --- | --- | --- | --- | --- |
| recipes | 0 | raw | 231637 | 231637 | 0 | as downloaded |
| recipes | 1 | drop_exact_duplicate_rows | 231637 | 231637 | 0 | byte-identical rows |
| recipes | 2 | quarantine_conflicting_ids | 231637 | 231637 | 0 | 0 recipe ids had disagreeing rows and were quarantined; identical repeats collapsed |
| recipes | 3 | require_valid_id | 231637 | 231637 | 0 | recipe id is the primary key |
| recipes | 4 | require_name | 231637 | 231636 | 1 | empty or missing recipe name |
| recipes | 5 | require_valid_submitted_date | 231636 | 231636 | 0 | catalogue availability date is required for historical evaluation |
| recipes | 6 | require_positive_finite_minutes | 231636 | 230542 | 1094 | non-positive or non-finite reported minutes cannot be banded |
| recipes | 7 | exclude_sentinel_minutes | 230542 | 230541 | 1 | reported minutes exactly equal to a known overflow sentinel [2147483647] |
| recipes | 8 | require_parsable_ingredients | 230541 | 230541 | 0 | an empty or unparsable ingredient list cannot produce recipe text |
| recipes | 9 | core_catalogue | 230541 | 230541 | 0 | final cleaned recipe catalogue |
| interactions | 0 | raw | 1132367 | 1132367 | 0 | as downloaded |
| interactions | 1 | drop_exact_duplicate_rows | 1132367 | 1132367 | 0 | byte-identical rows |
| interactions | 2 | quarantine_missing_keys | 1132367 | 1132367 | 0 | missing user_id or recipe_id |
| interactions | 3 | quarantine_invalid_dates | 1132367 | 1132367 | 0 | unparsable review date |
| interactions | 4 | quarantine_invalid_ratings | 1132367 | 1132367 | 0 | rating outside [1, 2, 3, 4, 5] or the unknown value 0 |
| interactions | 5 | drop_orphan_recipe_ids | 1132367 | 1127836 | 4531 | recipe_id absent from the clean catalogue |
| interactions | 6 | collapse_repeat_pairs_to_earliest | 1127836 | 1127836 | 0 | one row per (user, recipe); 0 tied-earliest conflicts kept as seen but excluded from labels |
| interactions | 7 | exclude_interaction_before_submission | 1127836 | 1126591 | 1245 | a review dated before the recipe existed is an unresolved inconsistency |
| interactions | 8 | core_interactions | 1126591 | 1126591 | 0 | final cleaned interaction events |


## 3. Temporal split and evaluation population

**The temporal protocol, locked before any result was produced:**

| stage | history | labels |
|---|---|---|
| validation | everything before 2017-01-01 | 2017-01-01 to 2017-12-31 |
| final | everything before 2018-01-01 | 2018-01-01 to the dataset's observed endpoint |

At both cutoffs:

- a candidate recipe must have been **submitted** before the cutoff, so no recipe enters
  the catalogue through the very review being predicted;
- user profiles and the popularity baseline read history events only;
- anything the user interacted with before the cutoff — including an unrated (0) event —
  is **seen** and is removed from the candidate set;
- warm-user eligibility is at least 5 distinct
  positively rated recipes, computed from history alone, **before** any label is examined;
- ranking metrics are reported only for users with at least one eligible novel positive in
  the label window. That conditional population is stated with every result.

**Positive rating definition:** [4, 5].
Ratings [1, 2, 3] are observed non-positive.
Rating 0 is **unknown / unrated** — never a zero-star
dislike, never inferred positive from review text. Unreviewed recipes are not negatives:
the data records ratings, not a complete account of what each user liked.

**Cohort scope:** every history-eligible user was scored; no cap was applied. The specification allowed a 5,000-user seeded cap as a compute fallback, and decision D-022 records why it was not used.

### Table 3 — Split and user eligibility

_From run `final-20260911T120041Z-5af9c102`'s own `metrics/split_denominators.json`: the population this evaluation actually scored._

| stage | history_end_exclusive | label_start | label_end_inclusive | n_history_events | n_label_events | n_catalogue_recipes | n_users_in_history | n_users_with_any_positive_history | n_history_eligible_users | cohort_capped | cohort_cap | cohort_seed | n_cohort_users | n_cohort_users_with_any_future_event | n_ranking_eligible_users | min_distinct_positive_history |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final | 2018-01-01 | 2018-01-01 | 2018-12-20 | 1105982 | 20609 | 230352 | 210253 | 169390 | 20557 | False |  | 42 | 20557 | 582 | 530 | 5 |

_Not shown: the standalone splits stage `splits-20260906T165247Z-781726a4` recorded a different cohort for this stage (cohort_capped, cohort_cap, n_cohort_users, n_cohort_users_with_any_future_event, n_ranking_eligible_users), because it ran under an earlier cohort setting. This evaluation scored the population above, so the two are not interchangeable._


## 4. The AI scoring layer

**Model:** `sentence-transformers/all-MiniLM-L6-v2`
**Pinned revision:** `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
**Dimension:** 384 · **Device:** cpu ·
**Max input:** 256 wordpieces
**Library versions:** sentence-transformers 6.0.1,
transformers 5.16.1, torch 2.14.0+cpu

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

**What the score means:** Estimated semantic relevance: the shifted cosine between a frozen sentence-encoder representation of the recipe text and the mean representation of the user's pre-cutoff positively rated recipes. Not a predicted rating, not a probability, not a satisfaction estimate.

**Limitation to state in the paper.** The encoder postdates the review period and was
pretrained on public web text that may include Food.com content. This is retrospective
offline benchmarking, not a system that could have been deployed in 2016.



## 5. The linear programme

For user *u*, over eligible unseen candidate recipes *C_u* with relevance
scores *s_ui*:

```
maximise    Σ_{i ∈ C_u} s_ui · x_i

subject to  Σ_{i ∈ C_u} x_i = k                     (exactly k recipes)
            Σ_{i ∈ G_g}  x_i ≤ b_g   for every band g   (variety cap)
            0 ≤ x_i ≤ 1                              (continuous)
```

with **k = 6** and **b_g = 3** for every band.

**The four disjoint preparation-time bands**, from reported minutes:

- **G1_0_15**: 0 < minutes <= 15
- **G2_15_30**: 15 < minutes <= 30
- **G3_30_60**: 30 < minutes <= 60
- **G4_60_plus**: minutes > 60

**Deliberately absent:** price constraints, summed calories, total preparation-time limits,
pairwise diversity penalties, overlapping quota groups, transportation costs. Each either
requires data this dataset does not contain, or destroys the structure the next section
depends on.

**Feasibility rule.** Before solving, check `Σ_g min(b_g, |G_g ∩ C_u|) ≥ k`. This is exact:
it holds if and only if a feasible shortlist exists. A user who fails it is recorded as
structurally infeasible and reported separately — never rescued by quietly relaxing a cap.

**Solver:** `scipy.optimize.linprog(method="highs-ds")`. SciPy minimises, so the objective
vector passed to it is `c = −s`. Tolerance 1e-07 on the equality
residual, the bounds, the capacities and the distance to the nearest integer.

### Why a continuous LP returns whole recipes

The disjoint preparation-time bands make the constraint matrix that of a min-cost flow problem with integer supplies and capacities, whose basic optimal solutions are integral. The continuous LP therefore returns whole recipes without a binary formulation. This holds for this restricted structure only.

This guarantee is checked on every single solve rather than assumed, and cross-checked
against three independent oracles: exhaustive enumeration on small cases, a score-sorted
capacity-respecting greedy oracle, and the identity that with every `b_g = k` the LP
optimum must equal the unconstrained top-k sum.

**The honest claim.** A score-sorted, capacity-respecting greedy selection also solves this special case. The LP is not claimed to be computationally necessary here. Its contribution is a transparent formulation, an exact feasibility condition, a certified optimum and an interpretable dual.



## 6. Duality

With α free for the exact-size equality, β_g ≥ 0 for each band cap and
γ_i ≥ 0 for each upper bound x_i ≤ 1:

```
minimise    k·α + Σ_g b_g·β_g + Σ_i γ_i
subject to  α + β_g(i) + γ_i ≥ s_ui      for every eligible i
```

**What β_g means:** Shadow value of a preparation-time band cap, in AI relevance score units. A positive value means the cap is locally restricting the achievable model score. It is not money, not cognitive load, not a psychological benefit.

**What it does not mean:** it is not money, not cognitive load, not a psychological
benefit, and not a measure of user welfare.

**A caution for the viva.** At a kink or a tied optimum the shadow value is not unique. For
any whole-number change to a cap, the model is **re-solved** and the actual score change
reported; a local marginal is never extrapolated to a whole extra slot.

### Table 10 — Primal-dual verification (one real user)

| quantity | value |
| --- | --- |
| primal objective (max total relevance score) | 5.4432584047317505 |
| dual objective (min k*alpha + sum b_g*beta_g + sum gamma_i) | 5.4432584047317505 |
| duality gap \|primal - dual\| | 0.0 |
| strong duality holds within tolerance | True |
| max dual constraint violation | 0.0 |
| alpha (shadow value of the exact-size constraint) | 0.9029040336608887 |
| beta[G1_0_15] (shadow value of the band cap) | 0.0 |
| beta[G2_15_30] (shadow value of the band cap) | 0.0 |
| beta[G3_30_60] (shadow value of the band cap) | 0.0 |
| beta[G4_60_plus] (shadow value of the band cap) | 0.0 |
| gamma: number of binding upper bounds | 5 |
| complementary slackness: max beta x cap slack | 0.0 |
| complementary slackness: max gamma x (1 - x) | 0.0 |
| complementary slackness: max x x dual slack | 0.0 |
| tolerance | 1e-07 |
| all checks passed | True |


## 7. The four comparison methods and the metrics

All four methods see the same users, the same eligible catalogue and the same shortlist length. Only the score and the caps differ.

- **RANDOM** — Random-priority feasible selection: the eligible catalogue is shuffled with a fixed seed and recipes are accepted in that order while their band has capacity. Repeated 20 times per user and averaged within the user. Not a uniform sample over feasible shortlists.
- **POPULARITY_LP** — Recipes scored by their count of positive ratings before the history cutoff, then the same band-capped LP. Ties resolved by ascending recipe id.
- **AI_TOPK** — The six highest AI relevance scores, with no band caps applied. An ablation that isolates the effect of the optimisation constraints; it may violate the caps.
- **AI_LP** — AI relevance scores with the band-capped LP. The proposed method.

**Metric definitions.** With *R_u* the set of eligible novel recipes the user rated 4 or 5
in the label window, and *L_u* the ranked k-item output:

```
Recall@k = |L_u ∩ R_u| / |R_u|
DCG@k    = Σ_{j=1..k} 1[item_j ∈ R_u] / log₂(j+1)
NDCG@k   = DCG@k / IDCG@k,   IDCG@k = Σ_{j=1..min(k,|R_u|)} 1 / log₂(j+1)
```

Both are macro-averaged per user, never review-weighted. They are reported only for users
with |R_u| > 0, and that conditional population is stated alongside.

**Reduction ratio.** Descriptive identity 1 - k/|C_u|: the proportion of the eligible catalogue not shown. It is a property of the arithmetic, not evidence about attention, effort or psychological choice overload.

**Runtimes.** Machine runtime of the scoring and solving code. Never a human decision time.



## 8. Results

### Table 4 — Method comparison (k=6, b=3)

| stage | method | k | cap | n_users_evaluated | n_users_with_positives | mean_recall_at_k | mean_ndcg_at_k | mean_bands_represented | mean_cap_violations | pct_exact_size_ok | pct_feasible | failure_rate_pct | mean_candidates | mean_reduction_ratio | mean_scoring_seconds | mean_solve_seconds | mean_total_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final | AI_LP | 6 | 3 | 530 | 530 | 0.0000 | 0.0006 | 3.0736 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0041 | 0.0082 | 0.5666 |
| final | AI_TOPK | 6 | 3 | 530 | 530 | 0.0000 | 0.0006 | 2.8566 | 0.5132 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0041 | 0.1554 | 0.1595 |
| final | POPULARITY_LP | 6 | 3 | 530 | 530 | 0.0085 | 0.0049 | 2.9226 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0083 | 0.4798 |
| final | RANDOM | 6 | 3 | 530 | 530 | 0.0000 | 0.0000 | 3.3356 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0186 | 0.0192 |

### Table 5 — Preplanned paired differences with bootstrap intervals

95% paired user-bootstrap interval over 2,000 resamples of users, seed 42. Describes resampling uncertainty within this benchmark only. Not a population inference, and an interval containing zero is not evidence of equivalence.

| metric | method_a | method_b | n_paired_users | mean_a | mean_b | mean_absolute_difference | ci_low | ci_high | ci_level | n_bootstrap_resamples | seed | interval_excludes_zero |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| recall_at_k | AI_LP | POPULARITY_LP | 530 | 0.0000 | 0.0085 | -0.0084 | -0.0150 | -0.0029 | 0.9500 | 2000 | 42 | True |
| recall_at_k | AI_LP | AI_TOPK | 530 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.9500 | 2000 | 42 | False |
| ndcg_at_k | AI_LP | POPULARITY_LP | 530 | 0.0006 | 0.0049 | -0.0043 | -0.0081 | -0.0010 | 0.9500 | 2000 | 42 | True |
| ndcg_at_k | AI_LP | AI_TOPK | 530 | 0.0006 | 0.0006 | 0.0000 | 0.0000 | 0.0000 | 0.9500 | 2000 | 42 | False |

### Table 8 — Feasibility and failures

A method that failed on a **feasible** input is charged recall zero in the primary table: dropping difficult users would flatter whichever method fails most. A **structurally infeasible** profile is different — no valid k-item shortlist exists at all — and is reported separately, with the coverage loss shown. A common-success table, restricted to users where every method worked, accompanies the primary one rather than replacing it.

| stage | method | k | cap | n_users | n_feasible | pct_feasible | n_exact_size_ok | pct_exact_size_ok | n_failed_on_feasible_input | failure_rate_pct | mean_cap_violations | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final | AI_LP | 6 | 3 | 530 | 530 | 100.0000 | 530 | 100.0000 | 0 | 0.0000 | 0.0000 |  |
| final | AI_TOPK | 6 | 3 | 530 | 530 | 100.0000 | 530 | 100.0000 | 0 | 0.0000 | 0.5132 | cap violations are expected for AI_TOPK by design |
| final | POPULARITY_LP | 6 | 3 | 530 | 530 | 100.0000 | 530 | 100.0000 | 0 | 0.0000 | 0.0000 |  |
| final | RANDOM | 6 | 3 | 530 | 530 | 100.0000 | 530 | 100.0000 | 0 | 0.0000 | 0.0000 |  |


## 9. Sensitivity analysis

Both sweeps were declared in `config/research.yaml` before any result was seen.

### Table 6 — Shortlist-length sensitivity (k=4/b=2, k=6/b=3, k=8/b=4)

| stage | method | k | cap | n_users_evaluated | n_users_with_positives | mean_recall_at_k | mean_ndcg_at_k | mean_bands_represented | mean_cap_violations | pct_exact_size_ok | pct_feasible | failure_rate_pct | mean_candidates | mean_reduction_ratio | mean_scoring_seconds | mean_solve_seconds | mean_total_seconds | sweep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final | AI_LP | 4 | 2 | 530 | 530 | 0.0000 | 0.0007 | 2.7396 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0059 | 0.0049 | 0.3658 | length_sweep |
| final | AI_TOPK | 4 | 2 | 530 | 530 | 0.0000 | 0.0007 | 2.4396 | 0.4585 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0059 | 0.1059 | 0.1119 | length_sweep |
| final | POPULARITY_LP | 4 | 2 | 530 | 530 | 0.0043 | 0.0032 | 2.9208 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0052 | 0.3067 | length_sweep |
| final | RANDOM | 4 | 2 | 10600 | 10600 | 0.0000 | 0.0000 | 2.8646 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0116 | 0.0120 | length_sweep |
| final | AI_LP | 6 | 3 | 530 | 530 | 0.0000 | 0.0006 | 3.0736 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0024 | 0.0040 | 0.2743 | length_sweep |
| final | AI_TOPK | 6 | 3 | 530 | 530 | 0.0000 | 0.0006 | 2.8566 | 0.5132 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0024 | 0.0798 | 0.0823 | length_sweep |
| final | POPULARITY_LP | 6 | 3 | 530 | 530 | 0.0085 | 0.0049 | 2.9226 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0040 | 0.2290 | length_sweep |
| final | RANDOM | 6 | 3 | 10600 | 10600 | 0.0000 | 0.0000 | 3.3356 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0087 | 0.0089 | length_sweep |
| final | AI_LP | 8 | 4 | 530 | 530 | 0.0000 | 0.0005 | 3.2698 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0039 | 0.0074 | 0.5352 | length_sweep |
| final | AI_TOPK | 8 | 4 | 530 | 530 | 0.0000 | 0.0005 | 3.1189 | 0.5755 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0039 | 0.1615 | 0.1655 | length_sweep |
| final | POPULARITY_LP | 8 | 4 | 530 | 530 | 0.0119 | 0.0062 | 2.9245 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0075 | 0.4368 | length_sweep |
| final | RANDOM | 8 | 4 | 10600 | 10600 | 0.0000 | 0.0000 | 3.6062 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0172 | 0.0177 | length_sweep |

### Table 7 — Band-cap sensitivity (k=6 with b=2, 3, 6; b=6 removes the cap)

| stage | method | k | cap | n_users_evaluated | n_users_with_positives | mean_recall_at_k | mean_ndcg_at_k | mean_bands_represented | mean_cap_violations | pct_exact_size_ok | pct_feasible | failure_rate_pct | mean_candidates | mean_reduction_ratio | mean_scoring_seconds | mean_solve_seconds | mean_total_seconds | sweep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final | AI_LP | 6 | 2 | 530 | 530 | 0.0000 | 0.0006 | 3.4415 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0035 | 0.0042 | 0.3040 | cap_sweep |
| final | AI_TOPK | 6 | 2 | 530 | 530 | 0.0000 | 0.0006 | 2.8566 | 1.4226 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0035 | 0.0925 | 0.0960 | cap_sweep |
| final | POPULARITY_LP | 6 | 2 | 530 | 530 | 0.0086 | 0.0050 | 3.0264 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0045 | 0.2481 | cap_sweep |
| final | RANDOM | 6 | 2 | 10600 | 10600 | 0.0000 | 0.0000 | 3.6525 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0098 | 0.0101 | cap_sweep |
| final | AI_LP | 6 | 3 | 530 | 530 | 0.0000 | 0.0006 | 3.0736 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0058 | 0.0071 | 0.5151 | cap_sweep |
| final | AI_TOPK | 6 | 3 | 530 | 530 | 0.0000 | 0.0006 | 2.8566 | 0.5132 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0058 | 0.1542 | 0.1600 | cap_sweep |
| final | POPULARITY_LP | 6 | 3 | 530 | 530 | 0.0085 | 0.0049 | 2.9226 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0080 | 0.4193 | cap_sweep |
| final | RANDOM | 6 | 3 | 10600 | 10600 | 0.0000 | 0.0000 | 3.3356 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0165 | 0.0170 | cap_sweep |
| final | AI_LP | 6 | 6 | 530 | 530 | 0.0000 | 0.0006 | 2.8566 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0024 | 0.0047 | 0.3215 | cap_sweep |
| final | AI_TOPK | 6 | 6 | 530 | 530 | 0.0000 | 0.0006 | 2.8566 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0024 | 0.0913 | 0.0937 | cap_sweep |
| final | POPULARITY_LP | 6 | 6 | 530 | 530 | 0.0094 | 0.0051 | 2.8755 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0048 | 0.2705 | cap_sweep |
| final | RANDOM | 6 | 6 | 10600 | 10600 | 0.0000 | 0.0000 | 3.2432 | 0.0000 | 100.0000 | 100.0000 | 0.0000 | 230150.8208 | 1.0000 | 0.0000 | 0.0102 | 0.0105 | cap_sweep |


## 10. One worked real example

**User:** demo label `demo-user-1535`
(the real id is archived in the run directory and is not printed here)
**Eligible unseen candidates:** 229,561
**Objective value:** 5.443258
**Band usage:** `{'G1_0_15': 2, 'G2_15_30': 2, 'G3_30_60': 0, 'G4_60_plus': 2}`
**Reachable capacity Σ_g min(b_g, |G_g|):** 12 (needs ≥ 6)
**Solver status:** Optimization terminated successfully. (HiGHS Status 7: Optimal)
**Equality residual:** 0 ·
**Max distance to an integer:** 0 ·
**Tolerance:** 1e-07
**All structural checks passed:** True

### Table 9 — Worked shortlist

| rank | recipe_id | name | reported_minutes | band | ai_relevance_score | selection_variable_x |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 21329 | no bakes | 10 | G1_0_15 | 0.9154 | 1.0000 |
| 2 | 133716 | quick and elegant french toast | 30 | G2_15_30 | 0.9091 | 1.0000 |
| 3 | 18280 | butter crunch lemon cheese bars | 70 | G4_60_plus | 0.9085 | 1.0000 |
| 4 | 278711 | grab n go breakfast cookies | 30 | G2_15_30 | 0.9043 | 1.0000 |
| 5 | 178568 | crispy brown rice snacks | 10 | G1_0_15 | 0.9030 | 1.0000 |
| 6 | 182080 | cherry cream crumble pie | 70 | G4_60_plus | 0.9029 | 1.0000 |

### The two-variable graphical slice

With 5 of the 6 shortlist positions held fixed, one position remains and exactly two candidates compete for it. The equality constraint becomes x_a + x_b = 1, so the feasible region is the straight segment between (1, 0) and (0, 1); the unit-interval bounds add nothing beyond it here. The objective s_a x_a + s_b x_b is linear, so its maximum sits at an endpoint. Recipe 182080 wins with a relevance score of 0.9029 against 0.9025, a difference of 0.0004 score units. Any interior point - splitting the position between the two - scores strictly less than the better endpoint, which is why a fractional answer never pays here.

Figure: `figures/fig09_graphical_method_slice.png`

This is a **slice** of the full model, with all but two selection variables held fixed. It illustrates why a linear objective over this feasible set is optimised at a vertex; it is not a claim that the model has two variables.



## 11. Figures

Every figure below has a title, explicit units, a caption and the CSV it was drawn from, all inside the run directory.

| figure | units | underlying data |
|---|---|---|
| `fig01_rating_distribution` | counts of interaction events | `fig01_rating_distribution.csv` |
| `fig02_minutes_distribution` | counts of recipes; x axis in minutes | `fig02_minutes_distribution.csv` |
| `fig03_band_composition` | counts of recipes; percentages of the banded catalogue | `fig03_band_composition.csv` |
| `fig04_user_history_sizes` | counts of users; x axis counts of distinct recipes | `fig04_user_history_sizes.csv` |
| `fig05_method_comparison_recall_at_6` | unitless ratio in [0,1]; macro-averaged per user | `fig05_method_comparison_recall_at_6.csv` |
| `fig06_method_comparison_ndcg_at_6` | unitless ratio in [0,1]; macro-averaged per user | `fig06_method_comparison_ndcg_at_6.csv` |
| `fig07_relevance_variety_tradeoff` | x: count of bands (0-4); y: unitless ratio in [0,1] | `fig07_relevance_variety_tradeoff.csv` |
| `fig08_sensitivity` | unitless ratio in [0,1]; x axis is a predeclared (k, b) configuration | `fig08_sensitivity.csv` |
| `fig09_graphical_method_slice` | axes are selection variables in [0,1]; objective in AI relevance score units | `fig09_graphical_method_slice.csv` |

**fig01_rating_distribution** — Rating distribution after cleaning. Rating 0 denotes an unrated interaction, not a zero-star dislike, and is excluded from the positive definition (positive = 4 or 5). Counts are events, not users.

**fig02_minutes_distribution** — Reported preparation time for recipes in the cleaned catalogue. These are the durations recorded by recipe contributors, not measured cooking times. Long durations are retained: marinating and slow cooking are legitimate.

**fig03_band_composition** — How the cleaned catalogue divides across the four disjoint preparation-time bands. Band imbalance is what the capacity constraint acts against: an unconstrained top-k can concentrate entirely in whichever band dominates.

**fig04_user_history_sizes** — Distribution of how many distinct recipes each user rated 4 or 5. The warm-user eligibility threshold of five distinct positives is applied to history events only, before any label is examined. Log scale on the y axis.

**fig05_method_comparison_recall_at_6** — Mean Recall@6 by method, macro-averaged over the 530 evaluated users who had at least one eligible novel positive in the label window. All methods used the same users and the same full eligible catalogue. AI_TOPK does not apply the band caps by design. This measures retrieval of later positive ratings, not user satisfaction or decision effort.

**fig06_method_comparison_ndcg_at_6** — Mean NDCG@6 by method, macro-averaged over the 530 evaluated users who had at least one eligible novel positive in the label window. All methods used the same users and the same full eligible catalogue. AI_TOPK does not apply the band caps by design. This measures retrieval of later positive ratings, not user satisfaction or decision effort.

**fig07_relevance_variety_tradeoff** — Each method plotted by the variety it produces and the later positives it retrieves. Movement up-and-left or down-and-right is the empirical trade-off this study reports. Band coverage is a property of the shortlist, not evidence that users wanted variety.

**fig08_sensitivity** — Predeclared sensitivity sweeps. Within each sweep the users, profiles, scores, dates and positive-rating definition are identical; only k and b change. b = k removes the effective band cap. Users made structurally infeasible by a tighter cap are reported in the infeasibility table, not dropped.

**fig09_graphical_method_slice** — Two-variable slice of the shortlist LP for one real user (user 1535): recipes 182080 (band G4_60_plus) and 130844 (band G4_60_plus) competing for the final position, with the other 5 selections held fixed. This is a slice of the full 229561-variable model, not the model itself.



## 12. Limitations

### Design

**Observational, not experimental.** Users chose which recipes to cook and review. Nothing
was randomised, no treatment was assigned, and no counterfactual is available. Every
comparison here is between *retrieval procedures on historical data*, not between
interventions on people.

**Retrospective, not deployable.** The encoder was released years after the review period
and was pretrained on public web text that may include Food.com content. Even with correct
temporal splitting, this is offline benchmarking of a modern model against old data — not a
demonstration that such a system could have run in 2016.

**A benchmark, not a population.** The cohort is Food.com users who reviewed enough recipes
to be warm at a cutoff. They are not a sample from any population of interest. Nothing here
generalises to consumers, to other platforms, or to people who read recipes without
reviewing them.

### Data

**Ratings are not preferences.** The data records ratings, not a complete account of what
each user liked, cooked or would have enjoyed. An unreviewed recipe is not a negative — it
is unobserved, and treating unobserved as negative would fabricate the majority of the
label matrix.

**Rating 0 is unknown.** It is treated as unrated throughout: never a zero-star dislike,
never inferred positive from review text. If the platform's documentation later establishes
another meaning, the positive-rating rule and every result depending on it would need
revisiting.

**Selection at every layer.** Who reviews, which recipes get reviewed, and which get
reviewed *quickly* are all non-random. Popularity in particular is a measure of exposure as
much as quality.

**Reported, not measured, preparation times.** `minutes` is what a contributor typed. It is
unvalidated, occasionally implausible, and the definition of what it includes (marinating?
chilling? resting?) varies by contributor. The whole band structure rests on this field, so
its noise propagates into the constraint.

**Nutrition units are unverified.** The seven-value array is commonly documented as calories
plus six percentage-daily-value fields rather than gram quantities. This has not been
verified against the downloaded release, and nutrition is not used in the core model. No
nutritional or clinical claim is made.

**Quarantined records are excluded, not resolved.** Conflicting recipe ids, tied-earliest
conflicting events and interactions dated before submission are set aside with counts. They
are unresolved ambiguities, not clean deletions, and a different resolution rule could shift
the counts.

**Dataset identity is part of the result.** Counts depend on the exact Kaggle version
downloaded. The source paper's headline figures describe its filtered task corpus and are
not ours.

### Method

**The band cap is a design choice.** Nothing in this data shows that users want
preparation-time variety. The constraint is a modelling decision motivated by the
choice-overload literature; its effect on retrieval is what is measured, and that
measurement says nothing about whether variety is wanted.

**The relevance score is similarity, not satisfaction.** It is the shifted cosine between a
recipe's text representation and the mean of the user's past positives. It is not a
predicted rating, not a probability, and not calibrated to anything.

**Content-only.** No collaborative signal, no interaction history beyond the mean profile,
no temporal drift in taste, no context. A user whose preferences changed after the cutoff
looks like a model failure and is indistinguishable from one.

**Text coverage varies.** Some recipes have rich descriptions and many descriptive tags;
others have almost nothing. The representation quality is not uniform across the catalogue,
and sparse recipes are systematically disadvantaged.

**The tag whitelist is a judgement.** Duration tags are excluded because they encode the
constraint dimension; administrative tags because they carry no content. Reasonable people
could draw the line differently, and the whitelist is seeded from documented tag families
rather than being exhaustive.

**Cold users are excluded.** Users without a usable positive-history vector are outside
every warm-user AI claim. That exclusion is reported, but it means the results describe
users who already had history — the population a cold-start system most needs to serve is
absent.

**The LP is not computationally necessary here.** A score-sorted, capacity-respecting greedy
selection solves this restricted case. Its value is formulation transparency, an exact
feasibility condition, a certified optimum and an interpretable dual — not speed.

**Shadow values are local and possibly non-unique.** At a kink or a tied optimum the dual is
not unique. Reported whole-number cap trade-offs are re-solved rather than extrapolated, but
the local marginals should not be read as prices.

### Evaluation

**Recall's denominator is thin.** `|R_u|` is the number of eligible novel recipes a user
rated 4–5 in a one-year window. Absolute recall against a catalogue of hundreds of thousands
of recipes will be small for every method; small absolute differences deserve absolute
reporting, not relative lifts.

**Ranking metrics are conditional.** They exist only for users with at least one eligible
novel positive. That population is smaller than the cohort, and is stated with every result.

**Bootstrap intervals understate dependence.** Users share recipes, so their outcomes are
not independent. The interval describes resampling uncertainty within this benchmark and
nothing wider.

**No p-values, by design.** None are reported. Absence of a significant difference is not
evidence of equivalence, and "preserved quality" would require a non-inferiority margin
declared in advance — which this protocol does not have.

**AI_TOPK violates the caps by design.** It is an ablation. Its cap violations are a
property of the comparison, not a defect, and its total relevance score upper-bounds AI_LP's
by construction.

**Failures and infeasibility are different things.** A method failing on a feasible input is
charged recall zero. A structurally infeasible profile is reported separately. Both are
published; neither is hidden by dropping the user.

### Scope

**No causal claim is available.** Nothing here identifies a causal effect of shortlisting,
of variety, or of the AI score on any human outcome.

**No human outcome was measured at all.** No participant, no survey, no decision timer, no
confidence rating, no satisfaction measure, no observation of anyone choosing anything. The
project measured what a retrieval procedure returns and how well those returns match later
ratings.

Specifically, this study did **not** measure and must **never** claim: reduced choice
overload, reduced stress, increased confidence, reduced regret, faster human decisions,
improved meal satisfaction, better nutrition, allergy safety, clinical outcomes, or
universal consumer behaviour.

**Choice overload is the motivation, not the finding.** It explains why shortlisting is
worth studying. The literature (S3, S4) supports a cautious motivation; it cannot supply an
outcome this study did not observe.

### Reproducibility caveats

**Solver ties.** Different SciPy or HiGHS versions may return different equally optimal sets
for tied scores. Objective values and constraint compliance will agree; the specific set may
not, which is why the documented lexicographic tie-break is applied and verified.

**Floating point.** Metrics agree to within the declared `1e-7` tolerance, not bit-for-bit,
across platforms and BLAS implementations.

**Model availability.** Reproduction requires the same pinned model revision. If it becomes
unavailable, the run is not reproducible as specified, and substituting a different revision
would be a different experiment.


## 13. Statements you must not make

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



## 14. Interpretation prompts

These are questions for you to answer in the discussion, not answers. The
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
   shortlisting might matter. It cannot supply an outcome this study did not measure.


## 15. How to reproduce every number here

**Run id:** `final-20260911T120041Z-5af9c102`
**Config fingerprint (SHA-256):** `258f2c7edf14bcbfc7fb2c8ca475557b1a51097b799de55eb793e6271ca1f873`
**Code revision:** `6f42a98a6327bf8d7b96e6fde72a9e06f359a5fb` on branch `main`
(working tree dirty: `False`)
**Python:** 3.12.10 on Windows
**Seeds:** `{'cohort_seed': 42, 'random_method_seed': 42, 'bootstrap_seed': 42}`
**Model revision:** `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`

**Data files this run read:**

_(none recorded)_

**Package versions:**

- PyYAML: 6.0.3
- huggingface-hub: 1.30.0
- matplotlib: 3.11.1
- numpy: 2.5.2
- pandas: 3.0.5
- plotly: 7.0.0
- pyarrow: 25.0.1
- pydantic: 2.13.5
- scikit-learn: 1.9.0
- scipy: 1.18.1
- sentence-transformers: 6.0.1
- streamlit: 1.63.0
- torch: 2.14.0
- transformers: 5.16.1

To reproduce: check out the code revision above, place the same raw files (the hashes must
match), restore `runs/final-20260911T120041Z-5af9c102/config/config_snapshot.json` over `config/`, and run
`python tasks.py final`. Same seeds, same config, same numbers.

