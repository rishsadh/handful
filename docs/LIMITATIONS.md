# Limitations

What this study cannot support, and why. Written to be quoted directly in the paper's
limitations section.

---

## Design

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

## Data

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

## Method

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

## Evaluation

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

## Scope

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

## Reproducibility caveats

**Solver ties.** Different SciPy or HiGHS versions may return different equally optimal sets
for tied scores. Objective values and constraint compliance will agree; the specific set may
not, which is why the documented lexicographic tie-break is applied and verified.

**Floating point.** Metrics agree to within the declared `1e-7` tolerance, not bit-for-bit,
across platforms and BLAS implementations.

**Model availability.** Reproduction requires the same pinned model revision. If it becomes
unavailable, the run is not reproducible as specified, and substituting a different revision
would be a different experiment.
