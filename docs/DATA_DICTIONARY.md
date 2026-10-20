# Data dictionary

Three layers: the raw files as downloaded, the cleaned tables the pipeline produces, and
the derived structures used for evaluation. Column semantics that carry a research meaning
— the positive-rating rule, the unknown rating, the seen definition — are stated here and
nowhere contradicted.

---

## 1. Raw — `data/raw/RAW_recipes.csv`

| column | type | meaning | notes |
|---|---|---|---|
| `name` | text | recipe title as submitted | whitespace-normalised on cleaning |
| `id` | int64 | **primary key** | read as `Int64`, never as float: float conversion silently loses precision on large ids |
| `minutes` | int64 | contributor-**reported** preparation duration | not a measured time; not validated by the platform |
| `contributor_id` | int64 | pseudonymous submitter key | not a demographic attribute and not used as a feature |
| `submitted` | date | when the recipe entered the catalogue | governs candidate availability at each cutoff |
| `tags` | list[str] | site tags, mixing descriptive and administrative | filtered by `config/tag_rules.yaml` before use |
| `nutrition` | list[float] | seven values | **units unverified.** Commonly documented as calories plus six percentage-daily-value fields, not seven gram quantities. Retained, not used in the core model |
| `n_steps` | int64 | source step count | compared with the parsed length; both retained |
| `steps` | list[str] | instructions | not part of the rendered encoder text |
| `description` | text | free-text blurb | truncated to 300 chars for the encoder; may be empty |
| `ingredients` | list[str] | ingredient names | part of the rendered encoder text |
| `n_ingredients` | int64 | source ingredient count | compared with the parsed length |

## 2. Raw — `data/raw/RAW_interactions.csv`

| column | type | meaning | notes |
|---|---|---|---|
| `user_id` | int64 | pseudonymous history key | never enriched with real-world identity |
| `recipe_id` | int64 | foreign key to `recipes.id` | many interactions map to one recipe |
| `date` | date | review event date | a date, not a session timer; no time-of-day is invented |
| `rating` | int64 | 1–5, or 0 | **0 means unknown / unrated.** Never a zero-star dislike, never inferred positive from review text |
| `review` | text | free-text review | separated during cleaning; never a feature, never displayed, never committed |

---

## 3. Cleaned — `data/processed/recipes_clean.parquet`

Every raw column above survives, plus:

| column | type | meaning |
|---|---|---|
| `band` | string | preparation-time band: `G1_0_15`, `G2_15_30`, `G3_30_60`, `G4_60_plus` |
| `minutes_flagged_long` | bool | reported minutes above the review threshold (24 h). **Flagged, never dropped** — marinating and slow cooking are legitimate |
| `description_missing` | bool | the description was absent or blank before normalisation |
| `raw_tags`, `raw_ingredients`, `raw_steps`, `raw_nutrition` | string | the original serialised strings, retained for audit |
| `tags_parse_status` etc. | string | `ok` / `empty` / `missing` / `not_a_list` / `malformed` |
| `n_ingredients_parsed`, `n_steps_parsed` | int64 | lengths of the parsed lists, kept **separate** from the source counts |
| `n_ingredients_matches_parsed`, `n_steps_matches_parsed` | bool | source count agrees with the parsed length |
| `nutrition_length`, `nutrition_length_expected` | int64, bool | observed array length and whether it is the expected 7 |

Guarantees after cleaning: `id` is unique and int64; `minutes` is positive and finite;
`submitted` is a valid date; `ingredients` is non-empty; `band` is never null.

## 4. Cleaned — `data/processed/interactions_clean.parquet`

One row per `(user_id, recipe_id)` pair — the **earliest** event.

| column | type | meaning |
|---|---|---|
| `user_id`, `recipe_id` | int64 | keys |
| `date` | datetime | the **earliest** event date for this pair |
| `rating` | int64 | the earliest event's rating |
| `is_positive` | bool | `rating ∈ {4, 5}` |
| `is_unknown_rating` | bool | `rating == 0` |
| `n_events_for_pair` | int64 | how many raw events collapsed into this row |
| `tied_earliest_conflict` | bool | two events shared the earliest date with different ratings |
| `label_eligible` | bool | usable as a label. `False` for tied-earliest conflicts |

**Repeat-pair rule.** The earliest event wins. A later, contradicting rating is never
averaged into the earlier history. A tied-earliest conflict is unusable as a label but the
recipe still counts as **seen**.

## 5. Quarantine — `data/interim/quarantine/*.parquet`

Records excluded for a reason, kept for inspection rather than deleted:
`recipes_conflicting_ids`, `recipes_unusable_ingredients`, `interactions_missing_keys`,
`interactions_invalid_dates`, `interactions_invalid_ratings`,
`interactions_tied_earliest_conflicts`, `interactions_before_submission`.

`data/interim/review_text.parquet` holds the separated review text. Gitignored, local only.

## 6. Ledger — `data/processed/exclusion_ledger.csv`

| column | meaning |
|---|---|
| `entity` | `recipes` or `interactions` |
| `order` | position in the ordered pipeline |
| `stage` | the rule applied |
| `n_in`, `n_out`, `n_removed` | rows before, after, and excluded |
| `reason` | plain-language justification |

Each stage's `n_in` equals the previous stage's `n_out`; a test asserts it. The ledger
reconciles the raw download to the final catalogue with no unexplained gap.

## 7. Rendered text — `data/processed/rendered_text.parquet`

| column | meaning |
|---|---|
| `recipe_id` | key |
| `text` | the exact string the encoder sees |
| `text_sha256` | its hash — part of the embedding cache key |
| `n_chars` | length |

Composition, in fixed order: `name | ingredients | whitelisted tags | short description`.
Excluded by construction: review text, user ids, ratings, popularity, review counts,
timestamps, contributor ids, administrative tags, and every duration tag.

## 8. Embeddings — `data/processed/embeddings/`

`vectors.npy` (n × d float32, unit-normalised), `index.parquet` (`recipe_id`,
`text_sha256`) and `meta.json` (encoder provenance). Cache key:
`(recipe_id, text_sha256, model_id, model_revision)` — all four, so a re-render or a model
change invalidates the vector instead of silently mixing two models' outputs.

---

## 9. Derived structures (in memory, per stage)

| name | meaning |
|---|---|
| `history` | interactions strictly before the cutoff |
| `labels` | interactions inside the label window |
| `catalogue` | recipes **submitted** before the cutoff |
| `seen[u]` | every recipe `u` interacted with before the cutoff, **including unrated (0)** |
| `positives[u]` | recipes `u` rated 4–5 before the cutoff, restricted to the catalogue |
| `history_eligible_users` | `len(positives[u]) ≥ 5`, computed before any label is examined |
| `cohort_users` | the evaluated cohort; capped at 5,000 with seed 42 if needed |
| `ranking_users` | cohort users with ≥1 eligible **novel** positive in the label window |
| `label_positives[u]` | `R_u` — the ground truth for Recall and NDCG |

## 10. Per-user results — `runs/<run_id>/tables/per_user_results.csv`

| column | meaning |
|---|---|
| `user_id`, `method`, `stage`, `k`, `cap` | the cell being reported |
| `n_candidates` | size of the eligible unseen catalogue for this user |
| `n_relevant` | `|R_u|`. Ranking metrics are defined only when this is > 0 |
| `recall_at_k`, `ndcg_at_k` | the metrics; `NaN` where undefined |
| `bands_represented` | distinct bands in the shortlist (0–4) |
| `band_<label>` | items per band |
| `cap_violations` | overflow beyond the declared cap. Non-zero for AI_TOPK **by design** |
| `exact_size_ok` | exactly `k` items returned |
| `feasible` | a `k`-item shortlist satisfying the caps exists at all |
| `failed` | the method failed on a **feasible** input; charged recall 0 |
| `solver_status` | solver outcome, including whether the canonical tie-break moved the set |
| `reduction_ratio` | `1 − k/|C_u|`. A descriptive identity, not an overload measure |
| `scoring_seconds`, `solve_seconds`, `total_seconds` | **machine** runtimes, never human decision times |
| `repeat` | present for RANDOM only; averaged within user before any statistics |
