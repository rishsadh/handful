# Contribution disclosure

An accurate record of who did what. It exists so that neither person has to reconstruct it
later, and so that any acknowledgement or authorship decision rests on facts rather than
recollection.

**Project:** Personalised Recipe Shortlisting Using Linear Programming — An Offline Study of
Food.com Ratings
**Protocol version:** 2.0.0
**Last updated:** 2026-09-06

---

## Rish — technical implementation

Everything in this repository. Specifically:

- **Data acquisition support** — the download procedure, the provenance recorder, SHA-256
  file hashing, licence and version capture, and the gate that refuses to proceed on an
  unidentified dataset. (No data was downloaded by Rish's tooling; Kaggle requires the
  account holder's own session.)
- **Data audit** — the full audit of counts, keys, dates, missingness, duplicates,
  conflicts, join coverage, rating and duration distributions, list-field parsing, tag
  vocabulary, temporal inconsistencies and user-history sizes, plus `docs/DATA_AUDIT.md`.
- **Cleaning** — every rule, the quarantine policy, the ordered exclusion ledger, and the
  separation of review text from the feature path.
- **Technical design** — repository structure, configuration schema, run-context and
  provenance machinery, and the gates between stages.
- **Temporal protocol implementation** — split construction, catalogue availability, the
  seen definition, cohort selection, and the structural leakage checks.
- **AI implementation** — deterministic recipe-text rendering, the tag whitelist, the frozen
  encoder wrapper with pinned revisions, the embedding cache, history-only user profiles,
  and the relevance score.
- **LPP implementation** — the primal formulation, the exact feasibility condition, the
  solver integration, solution verification, exact band pruning, the greedy and enumeration
  oracles, and the integrality argument in code.
- **Duality** — the explicit dual, strong-duality and complementary-slackness checks,
  marginal sign conversion, re-solved cap perturbations, and the two-variable graphical
  slice.
- **Evaluation** — the four comparison methods, the metrics, the harness, the paired user
  bootstrap, the predeclared sensitivity sweeps, and the denominator and failure reporting.
- **Demo** — the local Streamlit application, its visual system, all seven screens, the
  scenario controls and their safety behaviour.
- **Testing** — the full automated suite and the synthetic fixtures it runs on.
- **Technical documentation** — README, data dictionary, technical methods, decision log,
  limitations, and the Results Pack generator.

## The researcher — research

- Research question, scope and instructor approval.
- Literature review and theoretical framing, including the choice-overload basis.
- Methodology approval: the positive-rating rule, eligibility, the temporal windows, the
  constraint structure, and the metrics — approved **before** the final test set is used.
- Interpretation of the results and their limits.
- Discussion and conclusions.
- Citation management and referencing.
- Writing, revision and submission of the paper.
- Viva preparation and defence.

## Not claimed by anyone

Neither person wrote the other's contribution. In particular:

- The researcher did **not** write the code in this repository.
- Rish did **not** write the research paper, its literature review, its interpretation, or
  its conclusions.

---

## AI assistance

The implementation in this repository was produced by Rish working with an AI coding
assistant (Claude, Anthropic), used as a development tool under Rish's direction and review.
The research design it implements is the Release 2.0 specification authored for this
project; the protocol decisions were not delegated to the tool.

No AI system generated, imputed, simulated or altered any research data. The only synthetic
data in the repository is in `src/foodcom/testing/`, exists solely for unit tests and the
smoke run, is labelled `SYNTHETIC-FIXTURE-NOT-RESEARCH-DATA` in its own provenance, and is
blocked from producing research numbers by an explicit guard in the evaluation harness.

If the institution requires a declaration of AI assistance, this paragraph is the accurate
statement of it. Rish should confirm the required wording and placement with the department,
since disclosure requirements differ by institution and this record cannot substitute for
the institution's own form.

---

## Authorship and acknowledgement

**This document does not determine authorship.** Institutional policy does, and it must be
followed.

The facts a policy would need are above: the researcher is responsible for the research design,
theory, interpretation and written work; Rish is responsible for the entire technical
implementation and its documentation. How that maps onto authorship, acknowledgement, or a
declared technical contribution is a question for the department, the supervisor, and the
institution's rules on collaboration and outside assistance — not a question this repository
can settle.

**Status:** the research presentation was completed before this repository was published.
Any further declaration about credit or AI-assisted development is a matter for the
institution's own rules, not for this repository.

---

## Verification

Every claim above is checkable. Each pipeline stage writes a run directory under `runs/`
recording the code revision, configuration, data hashes, package versions and timings that
produced it. The git history records who committed what and when.
