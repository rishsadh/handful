# Handful

**A handful of recipes, not a thousand.**

*Personalised recipe shortlisting using linear programming - an offline study of
Food.com ratings.*

- Project page: <https://handful.netlify.app>
- Repository: <https://github.com/reidifydesign/handful> (private)

Working subtitle for the paper: *a choice-overload-motivated approach to balancing
relevance and preparation-time variety.*

Secondary data only. No surveys, no recruited participants, no primary data collection, no
real food ordering, and no invented research data.

---

## The question

Given what a Food.com user rated highly before a cutoff date, choose a shortlist of six
recipes that maximises estimated relevance while keeping the shortlist spread across
preparation-time bands. Then measure, offline, whether that constraint costs anything in
retrieval of the recipes the user actually went on to rate highly.

## The method in one page

**Relevance.** A frozen `sentence-transformers/all-MiniLM-L6-v2` encoder turns each
recipe's text (name, ingredients, whitelisted descriptive tags, short description) into a
unit vector. A user's profile is the normalised mean of the vectors of the recipes they
rated 4 or 5 **before** the cutoff. The score is `s(u,i) = (1 + cos(p_u, e_i)) / 2`, which
lands in `[0, 1]`. It estimates semantic relevance. It is not a predicted rating, a
probability, or a satisfaction estimate.

**Selection.** A linear programme over the eligible unseen candidates:

```
maximise    Σ_{i ∈ C_u} s_ui · x_i
subject to  Σ_{i ∈ C_u} x_i = k                      k = 6
            Σ_{i ∈ G_g}  x_i ≤ b_g   for each band   b = 3
            0 ≤ x_i ≤ 1
```

Four disjoint preparation-time bands from reported minutes: `0–15`, `15–30`, `30–60`,
`>60`, upper-inclusive.

**Why continuous variables suffice.** The bands *partition* the candidates, so the
constraint matrix is that of a min-cost flow with integer supplies and capacities, whose
basic optimal solutions are integral. Every solve verifies this rather than assuming it,
and is cross-checked against exhaustive enumeration, a greedy oracle, and the identity that
with `b_g = k` the LP optimum equals the unconstrained top-k sum.

**The honest claim.** A score-sorted, capacity-respecting greedy selection also solves this
restricted case. The LP is not claimed to be computationally necessary. Its contribution is
a transparent formulation, an exact feasibility condition, a certified optimum and an
interpretable dual.

## What this project can and cannot conclude

It can report: retrieval of later positive ratings, ranking quality, preparation-time band
representation, constraint compliance, feasibility, machine runtime, and sensitivity to `k`
and `b`.

It cannot report, and must never claim, reduced choice overload, reduced stress, greater
confidence, less regret, faster human decisions, better meal satisfaction, better nutrition,
allergy safety, clinical outcomes, or anything about consumers in general. Choice overload
is the *motivation* for shortlisting. It is not an outcome this study observed.

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) and the "Statements you must not make"
section of the generated Results Pack.

---

## Status

**Gate 1 (data) is passed.** Food.com version 2, acquired via the official Kaggle API and
hashed into the provenance manifest: 231,637 recipes and 1,132,367 interactions raw,
230,541 and 1,126,591 after cleaning, with the exclusion ledger reconciling in full.

**Gate 3 (validation) is complete.** The 2017-label validation stage scored 812 users. It
is the development stage: it is where the pipeline was built and checked, and its numbers
are not the study's result.

**The final evaluation is complete.** It used the 2018 labels, ran once on 11 September
2026 after the configuration was frozen, and is recorded as run
`final-20260911T120041Z-5af9c102`. Under decision D-022 it scored every history-eligible
user instead of a 5,000-user sample. Every number in the next section comes from that run's
files, and the [Results Pack](docs/RESULTS_PACK.md) lists them with the run id.

## Results

**Who was scored.** 20,557 users had rated at least five distinct recipes 4 or 5 before
1 January 2018. Of those, 582 rated something in the 2018 label window, and 530 rated at
least one eligible unseen recipe 4 or 5 in it. Those 530 users are the evaluated
population. Each was offered a shortlist of six recipes drawn from an average of about
230,000 eligible candidates.

**What was found.** The popularity baseline retrieved more of the recipes users went on to
rate highly than the personalised method did. Personalised relevance with the preparation
time cap retrieved almost nothing.

| method | Recall@6 | NDCG@6 | users with a hit | mean bands represented (of 4) | mean cap violations |
|---|---|---|---|---|---|
| Random (feasible, capped) | 0.0000 | 0.0000 | 0 of 530 | 3.34 | 0.00 |
| Popularity, capped LP | 0.0085 | 0.0049 | 10 of 530 | 2.92 | 0.00 |
| AI relevance, top 6, no cap | 0.0000 | 0.0006 | 1 of 530 | 2.86 | 0.51 |
| AI relevance, capped LP (proposed) | 0.0000 | 0.0006 | 1 of 530 | 3.07 | 0.00 |

Recall@6 for the proposed method is 0.00003 before rounding: one user out of 530 had one
of six recipes match a later rating. Random was averaged over 20 draws per user and never
matched.

Paired differences, proposed method minus popularity, with a 95% bootstrap interval over
2,000 resamples of users (seed 42):

- Recall@6: -0.0084, interval [-0.0150, -0.0029]
- NDCG@6: -0.0043, interval [-0.0081, -0.0010]

Neither interval includes zero, so within this benchmark the popularity baseline did better
on both metrics. That is a legitimate finding and the project was built to report it either
way. It is a near-zero result for the proposed method, not evidence that it works.

**What the band cap did.** The capped and uncapped versions of the AI method have identical
Recall@6 and NDCG@6, because the same single user is the only hit in both. The cap raised
mean band representation from 2.86 to 3.07 bands and removed the 0.51 cap violations per
shortlist that uncapped top-6 produces. Because recall sits at the floor for both, the
identical scores show only that the cap did not lose a hit that was there. They do not show
that the cap is free in general, and a zero-width interval on a difference of exactly zero
is not evidence of equivalence.

**Sensitivity.** The ordering did not change with shortlist length or cap. Recall@6 of the
proposed method is 0.0000 in every setting. Popularity recall is 0.0043 at k=4 (cap 2),
0.0085 at k=6 (cap 3) and 0.0119 at k=8 (cap 4). At k=6 with caps of 2, 3 and 6 (6 removes
the cap) it is 0.0086, 0.0085 and 0.0094.

**How much weight this can bear.**

- The differences rest on very few users: 10 users with a hit for popularity, 1 for the
  proposed method, out of 530. Absolute recall is tiny for every method.
- The bootstrap resamples users as if they were independent. They are not: users share many
  of the same recipes, so the intervals understate the real uncertainty. They
  describe resampling within this benchmark and nothing wider.
- No p-values are reported, by design, and no claim of "significant" difference is made or
  needed.
- This is one platform, one year of labels, and only users who already had history. It says
  nothing about consumers in general.
- The 2017 validation stage (812 users) showed the same pattern: popularity 0.0103, the
  proposed method 0.0000, difference -0.0103 with interval [-0.0162, -0.0051]. Validation
  is not an independent confirmation, since it is the stage the pipeline was developed on.

Interpretation and discussion belong to the paper. This section reports what the code
computed.

---

## Setup

Python 3.11+ (built and tested on 3.12).

```bash
python tasks.py setup
```

That creates `.venv` and installs the core stack. The AI encoder is a separate, large
install:

```bash
python tasks.py setup-ai
```

`torch` and `sentence-transformers` are ~2.5 GB. They are **not** needed for the test suite,
since the tests use a deterministic hash-based test encoder, but they are required for any
real scoring run.

## Commands

`make` is not installed on the development machine, so `tasks.py` is the entry point that
works everywhere. The `Makefile` simply delegates to it.

| command | what it does |
|---|---|
| `python tasks.py acquire` | Data gate: hash the raw files, record provenance, probe the schema |
| `python tasks.py audit` | Full raw-data audit → `docs/DATA_AUDIT.md` + `reports/audit/*.csv` |
| `python tasks.py clean` | Cleaning, quarantine, ordered exclusion ledger |
| `python tasks.py splits` | Temporal splits, cohorts, structural leakage checks |
| `python tasks.py embeddings` | Render recipe text deterministically and encode it |
| `python tasks.py validate` | Validation-stage evaluation (2017 labels) + sensitivity |
| `python tasks.py final` | **Final** evaluation (2018 labels). Frozen config, runs once |
| `python tasks.py results-pack` | Build `docs/RESULTS_PACK.md` |
| `python tasks.py test` | Test suite |
| `python tasks.py lint` | ruff |
| `python tasks.py smoke` | End-to-end run on the **synthetic** fixture |
| `python tasks.py demo` | Launch the local Streamlit demo |
| `python tasks.py all` | audit → clean → splits → embeddings → validate → results-pack |

`all` deliberately stops before `final`. The final test set is used exactly once, after the
configuration is frozen; chaining it into a convenience target is how a test set gets spent
by accident.

### Running the final evaluation

```bash
python scripts/run_final_evaluation.py --freeze   # once, deliberately
python tasks.py final
```

The freeze writes `config/FROZEN.lock` recording the configuration's SHA-256. The final run
refuses to start if the lock is missing, if the configuration has changed since, or if the
test suite fails.

---

## Repository layout

```
app/          local Streamlit demo (seven screens)
site/         the public project page, deployed to Netlify
config/       research.yaml, cleaning.yaml, model.yaml, tag_rules.yaml
data/raw/     the two immutable source files (gitignored)
data/interim/ quarantine and private review text (gitignored)
data/processed/ cleaned tables, rendered text, embedding cache (gitignored)
docs/         data dictionary, methods, audit, decision log, limitations, Results Pack
figures/      the latest run's figures, copied out for convenience
reports/      audit tables and split summaries
runs/         one directory per research run - the canonical record
scripts/      thin CLIs over src/foodcom/pipeline.py
src/foodcom/  the library
tests/        the test suite
```

## Reproducibility

Every research run creates `runs/<run_id>/` holding the configuration snapshot and its
SHA-256, the dataset file hashes, the git revision and dirty state, package versions, the
model revision, every seed, start and completion times, logs, metrics, tables, figures and
any recorded failures.

Every table and figure in the Results Pack carries the run id that produced it. To
reproduce a number: check out that revision, restore
`runs/<run_id>/config/config_snapshot.json` over `config/`, confirm the raw-file hashes
match, and run the same stage.

## Configuration

| file | what it controls |
|---|---|
| `config/research.yaml` | dataset provenance, the locked protocol, cohort rules, metrics, sweeps |
| `config/cleaning.yaml` | cleaning rules and the ordered exclusion-ledger stages |
| `config/model.yaml` | encoder, text rendering, scoring, embedding cache, solver |
| `config/tag_rules.yaml` | the fixed descriptive-tag whitelist |

Anything under `research.yaml → protocol` is a methodological setting. Changing one is a
methodological change: record it in `docs/DECISION_LOG.md` with a reason and an approver,
and bump `protocol_version`.

## What must never be committed

Kaggle credentials, API keys, raw personal review text, the raw datasets, model caches, or
environment folders. `.gitignore` enforces this; review text is separated out during
cleaning and written only to gitignored `data/interim/`.

## Responsibilities

Rish owns the implementation: acquisition support, cleaning, audit, technical design, the
AI layer, the LP and duality work, evaluation, statistics, the demo, tests and technical
documentation. Khushi owns the research: literature, theory, methodology approval,
interpretation, discussion, referencing, submission and the viva. See
[`docs/CONTRIBUTION_DISCLOSURE.md`](docs/CONTRIBUTION_DISCLOSURE.md).

## References

- **S1** Li, S. (2019). *Food.com Recipes and Interactions* [Data set]. Kaggle.
- **S2** Majumder, B. P., Li, S., Ni, J., & McAuley, J. (2019). Generating personalized
  recipes from historical user preferences. *EMNLP-IJCNLP*, 5976–5982.
- **S3** Scheibehenne, B., Greifeneder, R., & Todd, P. M. (2010). Can there ever be too
  many options? *Journal of Consumer Research*, 37(3), 409–425.
- **S4** Chernev, A., Böckenholt, U., & Goodman, J. (2015). Choice overload: a conceptual
  review and meta-analysis. *Journal of Consumer Psychology*, 25(2), 333–358.
- **S5** MIT OpenCourseWare (2013). *The minimum cost flow problem*, 15.053, Lecture 16.
- **S6** Sentence Transformers. *all-MiniLM-L6-v2* model card, Hugging Face.
- **S7** SciPy community. `linprog(method="highs-ds")` documentation.
- **S8** Krichene, W., & Rendle, S. (2020). On sampled metrics for item recommendation.
  *KDD*. doi:10.1145/3394486.3403226
