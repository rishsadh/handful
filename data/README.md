# Data directory

Nothing in `raw/`, `interim/` or `processed/` is committed. `.gitignore` enforces that.

```
raw/         the two official files, byte-for-byte as downloaded. NEVER modified.
interim/     quarantined records and the private review-text table
processed/   cleaned tables, rendered recipe text, the embedding cache, source manifest
```

---

## Getting the raw files

**The two files are not present and cannot be downloaded automatically.** Kaggle requires
your own authenticated session, and an unofficial mirror is not an acceptable substitute
for the selected release.

1. Sign in to Kaggle and open
   <https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions>
2. Note the **version number** shown on the dataset page and copy the **licence wording**
   exactly as Kaggle states it.
3. Download the archive and place these two files, unmodified, in this directory:

   ```
   C:\Users\HP\dev\foodcom-research\data\raw\RAW_recipes.csv
   C:\Users\HP\dev\foodcom-research\data\raw\RAW_interactions.csv
   ```

4. Fill in `config/research.yaml`:

   ```yaml
   dataset:
     kaggle_version: "..."       # from the dataset page
     download_date: "2026-..-.." # ISO date
     licence_text: "..."         # transcribed exactly
     licence_permits_redistribution: null   # true only if the licence actually says so
   ```

5. Run `python tasks.py acquire`. It hashes both files, writes
   `processed/source_manifest.json` and probes the schema. It refuses to proceed while any
   provenance field still reads `UNRECORDED`.

**Do not** substitute another uploader's copy, a prefiltered classroom subset, or a mirror.
The dataset identity is part of the citation.

---

## Expected schema

`RAW_recipes.csv` — `name, id, minutes, contributor_id, submitted, tags, nutrition,
n_steps, steps, description, ingredients, n_ingredients`

`RAW_interactions.csv` — `user_id, recipe_id, date, rating, review`

`acquire` validates these column lists against the first rows and fails if any expected
column is absent, so a wrong file is caught before a full read.

---

## Counts

The source paper's widely quoted 180K+/700K+ figures describe *its filtered task corpus*;
it reports collecting 230K+ recipes and 1M+ reviews before filtering. Neither is ours. Every
count this project publishes is computed from the files you place here, under the rules in
`config/cleaning.yaml`, and is reconciled by the exclusion ledger.

---

## Immutability and privacy

- `raw/` is read-only in practice: every transformation writes elsewhere. If a raw file's
  SHA-256 changes between runs, the run manifests will disagree and that is the signal.
- **Review text** is separated during cleaning, written only to
  `interim/review_text.parquet`, never used as a feature, never rendered in the demo, and
  never committed.
- **User ids** are pseudonymous keys. They are never enriched with real-world identities,
  and the demo shows mapped labels (`profile-0007`) instead.
- Redistribution of the raw data or review text requires permission established from the
  dataset licence itself. `licence_permits_redistribution: null` means unknown, and unknown
  is treated as **no**.
