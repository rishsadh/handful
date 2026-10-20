"""Generate synthetic raw files shaped like the real Food.com CSVs.

SYNTHETIC. NOT RESEARCH DATA. See the package docstring.

The generator deliberately injects every messy case the cleaning rules claim to handle, so
the tests exercise the handling rather than the happy path:

* exact duplicate rows in both files
* two rows sharing a recipe id but disagreeing on the identity fields
* a recipe with non-positive minutes, and one with a malformed list field
* ratings of 0 (unknown) and an out-of-range rating
* repeated (user, recipe) pairs, including one with tied earliest dates and conflicting
  ratings
* an interaction dated before its recipe was submitted
* an orphan interaction pointing at a recipe id that does not exist
* recipes spread across all four preparation-time bands, including exact boundary values
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from foodcom.testing import SYNTHETIC_MARKER

_TAGS_DESCRIPTIVE = [
    "main-dish", "desserts", "italian", "mexican", "chicken", "vegetables", "pasta",
    "easy", "vegetarian", "comfort-food", "oven", "stove-top", "salads", "soups-stews",
    "beef", "seafood", "asian", "american", "spicy", "sweet", "breakfast", "snacks",
]
# Tags the whitelist must reject: duration proxies and administrative noise.
_TAGS_DENIED = [
    "time-to-make", "60-minutes-or-less", "30-minutes-or-less", "15-minutes-or-less",
    "4-hours-or-less", "weeknight", "number-of-servings", "preparation", "course",
]
_INGREDIENTS = [
    "olive oil", "garlic", "onion", "tomato", "chicken breast", "ground beef", "salt",
    "black pepper", "butter", "flour", "sugar", "eggs", "milk", "parmesan", "basil",
    "cumin", "paprika", "rice", "pasta", "carrot", "celery", "lemon", "spinach", "cream",
]
_WORDS = [
    "roasted", "creamy", "spicy", "classic", "quick", "hearty", "grilled", "baked",
    "chilled", "rustic", "simple", "golden", "smoky", "fresh",
]
_DISHES = [
    "chicken", "pasta", "soup", "salad", "casserole", "stew", "tart", "risotto", "curry",
    "chowder", "pie", "skillet", "bake", "bowl",
]

# Values chosen so every band is populated and the 15/30/60 boundaries are hit exactly.
_MINUTES_POOL = [5, 10, 12, 15, 15, 20, 25, 30, 30, 35, 45, 55, 60, 60, 75, 90, 120, 240, 480]


def make_synthetic_raw(
    *,
    seed: int = 7,
    n_recipes: int = 400,
    n_users: int = 60,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return `(recipes, interactions)` in the raw file schema."""
    rng = np.random.default_rng(seed)

    # ---------------------------------------------------------------- recipes
    base = dt.date(2005, 1, 1)
    span = (dt.date(2016, 6, 30) - base).days
    rows = []
    for i in range(n_recipes):
        rid = 100_000 + i
        submitted = base + dt.timedelta(days=int(rng.integers(0, span)))
        minutes = int(_MINUTES_POOL[int(rng.integers(0, len(_MINUTES_POOL)))])
        n_ing = int(rng.integers(3, 10))
        ingredients = sorted(
            rng.choice(_INGREDIENTS, size=n_ing, replace=False).tolist()
        )
        tags = rng.choice(_TAGS_DESCRIPTIVE, size=int(rng.integers(2, 6)), replace=False).tolist()
        tags += rng.choice(_TAGS_DENIED, size=2, replace=False).tolist()
        steps = [f"step {j + 1}: combine and cook" for j in range(int(rng.integers(2, 8)))]
        name = f"{rng.choice(_WORDS)} {rng.choice(_DISHES)} {i}"
        rows.append(
            {
                "name": name,
                "id": rid,
                "minutes": minutes,
                "contributor_id": int(rng.integers(1000, 9999)),
                "submitted": submitted.isoformat(),
                "tags": repr(tags),
                "nutrition": repr(
                    [
                        round(float(rng.uniform(50, 900)), 1),
                        *[round(float(rng.uniform(0, 90)), 1) for _ in range(6)],
                    ]
                ),
                "n_steps": len(steps),
                "steps": repr(steps),
                "description": (
                    "" if i % 37 == 0 else f"a {rng.choice(_WORDS)} dish for any evening."
                ),
                "ingredients": repr(ingredients),
                "n_ingredients": n_ing,
            }
        )
    recipes = pd.DataFrame(rows)

    # --- injected messiness (recipes) ---
    recipes = pd.concat([recipes, recipes.iloc[[0]]], ignore_index=True)  # exact duplicate
    conflicting = recipes.iloc[1].copy()
    conflicting["minutes"] = int(conflicting["minutes"]) + 45
    conflicting["name"] = conflicting["name"] + " (variant)"
    recipes = pd.concat([recipes, pd.DataFrame([conflicting])], ignore_index=True)

    bad_minutes = recipes.iloc[2].copy()
    bad_minutes["id"] = 999_001
    bad_minutes["minutes"] = 0
    malformed = recipes.iloc[3].copy()
    malformed["id"] = 999_002
    malformed["ingredients"] = "['unclosed', 'list'"
    no_name = recipes.iloc[4].copy()
    no_name["id"] = 999_003
    no_name["name"] = "   "
    bad_date = recipes.iloc[5].copy()
    bad_date["id"] = 999_004
    bad_date["submitted"] = "not-a-date"
    recipes = pd.concat(
        [recipes, pd.DataFrame([bad_minutes, malformed, no_name, bad_date])], ignore_index=True
    )

    # ---------------------------------------------------------------- interactions
    valid_ids = [100_000 + i for i in range(n_recipes)]
    inter_rows = []
    for u in range(n_users):
        uid = 500_000 + u
        # History: at least 8 distinct recipes, most rated positively, all before 2017.
        hist_ids = rng.choice(valid_ids, size=int(rng.integers(8, 16)), replace=False)
        for rid in hist_ids:
            day = dt.date(2010, 1, 1) + dt.timedelta(days=int(rng.integers(0, 2550)))
            rating = int(rng.choice([5, 5, 4, 4, 3, 0], p=[0.35, 0.25, 0.2, 0.1, 0.05, 0.05]))
            inter_rows.append(
                {
                    "user_id": uid,
                    "recipe_id": int(rid),
                    "date": day.isoformat(),
                    "rating": rating,
                    "review": f"{SYNTHETIC_MARKER}: generated placeholder review text.",
                }
            )
        # Validation labels (2017) and final labels (2018), on recipes not seen in history.
        unseen = [r for r in valid_ids if r not in set(hist_ids.tolist())]
        for year, n_labels in ((2017, int(rng.integers(1, 5))), (2018, int(rng.integers(1, 4)))):
            for rid in rng.choice(unseen, size=n_labels, replace=False):
                day = dt.date(year, 1, 1) + dt.timedelta(days=int(rng.integers(0, 360)))
                inter_rows.append(
                    {
                        "user_id": uid,
                        "recipe_id": int(rid),
                        "date": day.isoformat(),
                        "rating": int(rng.choice([5, 4, 3], p=[0.55, 0.3, 0.15])),
                        "review": f"{SYNTHETIC_MARKER}: generated placeholder review text.",
                    }
                )
    interactions = pd.DataFrame(inter_rows)

    # --- injected messiness (interactions) ---
    extra = []
    first_user = 500_000

    # exact duplicate row
    extra.append(interactions.iloc[0].to_dict())

    # repeated pair, later event with a different rating: the earliest must win
    repeat = interactions.iloc[1].to_dict()
    repeat["date"] = "2016-12-01"
    repeat["rating"] = 1
    extra.append(repeat)

    # tied earliest dates with conflicting ratings -> excluded from labels, still SEEN
    tied_a = {
        "user_id": first_user, "recipe_id": valid_ids[5], "date": "2012-06-01",
        "rating": 5, "review": SYNTHETIC_MARKER,
    }
    tied_b = dict(tied_a, rating=2)
    extra.extend([tied_a, tied_b])

    # out-of-range rating, orphan recipe id, review before the recipe existed
    extra.append({"user_id": first_user, "recipe_id": valid_ids[6], "date": "2013-02-02",
                  "rating": 7, "review": SYNTHETIC_MARKER})
    extra.append({"user_id": first_user, "recipe_id": 777_777, "date": "2013-02-03",
                  "rating": 5, "review": SYNTHETIC_MARKER})
    extra.append({"user_id": first_user + 1, "recipe_id": valid_ids[7], "date": "1999-01-01",
                  "rating": 4, "review": SYNTHETIC_MARKER})
    # missing key and unparsable date
    extra.append({"user_id": None, "recipe_id": valid_ids[8], "date": "2014-05-05",
                  "rating": 4, "review": SYNTHETIC_MARKER})
    extra.append({"user_id": first_user + 2, "recipe_id": valid_ids[9], "date": "not-a-date",
                  "rating": 4, "review": SYNTHETIC_MARKER})

    interactions = pd.concat([interactions, pd.DataFrame(extra)], ignore_index=True)
    return recipes, interactions


def write_synthetic_raw(target_dir: Path, **kwargs) -> tuple[Path, Path]:
    """Write the synthetic files with the real filenames into `target_dir`."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    recipes, interactions = make_synthetic_raw(**kwargs)
    rp = target_dir / "RAW_recipes.csv"
    ip = target_dir / "RAW_interactions.csv"
    recipes.to_csv(rp, index=False)
    interactions.to_csv(ip, index=False)
    return rp, ip


def synthetic_config_overrides() -> dict[str, str]:
    """Provenance values that make the synthetic run's origin unmistakable."""
    return {
        "kaggle_version": SYNTHETIC_MARKER,
        "download_date": dt.date.today().isoformat(),
        "licence_text": (
            f"{SYNTHETIC_MARKER}. Generated locally by foodcom.testing.synthetic. "
            "No real Food.com data is present and no result from this run is research "
            "evidence."
        ),
    }
