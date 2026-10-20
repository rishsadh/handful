"""Schema, safe parsing and the cleaning rules."""

from __future__ import annotations

import pandas as pd
import pytest

from foodcom.data.schema import (
    INTERACTION_COLUMNS,
    RECIPE_COLUMNS,
    ParseStatus,
    normalise_whitespace,
    parse_list_field,
    validate_schema,
)

# ------------------------------------------------------------------ schema


def test_expected_schema_is_detected(raw_frames):
    recipes, interactions = raw_frames
    assert validate_schema(recipes, RECIPE_COLUMNS, "recipes").ok
    assert validate_schema(interactions, INTERACTION_COLUMNS, "interactions").ok


def test_missing_column_is_reported_not_ignored(raw_frames):
    recipes, _ = raw_frames
    report = validate_schema(recipes.drop(columns=["minutes"]), RECIPE_COLUMNS, "recipes")
    assert not report.ok
    assert "minutes" in report.missing


# ------------------------------------------------------------------ safe parsing


@pytest.mark.parametrize(
    ("raw", "expected", "status"),
    [
        ("['a', 'b']", ["a", "b"], ParseStatus.OK),
        ("[]", [], ParseStatus.EMPTY),
        ("[1, 2, 3]", [1, 2, 3], ParseStatus.OK),
        ("['unclosed'", None, ParseStatus.MALFORMED),
        ("not a list", None, ParseStatus.MALFORMED),
        ("'a string'", None, ParseStatus.NOT_A_LIST),
        ("", None, ParseStatus.MISSING),
        (None, None, ParseStatus.MISSING),
        (float("nan"), None, ParseStatus.MISSING),
    ],
)
def test_parse_list_field(raw, expected, status):
    value, got = parse_list_field(raw)
    assert got == status
    assert value == expected


def test_parser_never_executes_code(tmp_path):
    """`ast.literal_eval` evaluates literals only. A call in a cell must not run."""
    marker = tmp_path / "should_not_exist.txt"
    payload = f"__import__('pathlib').Path({str(marker)!r}).write_text('pwned')"
    value, status = parse_list_field(payload)
    assert value is None
    assert status == ParseStatus.MALFORMED
    assert not marker.exists()


def test_normalise_whitespace():
    assert normalise_whitespace("  a   b \n c ") == "a b c"
    assert normalise_whitespace(None) == ""
    assert normalise_whitespace(float("nan")) == ""


# ------------------------------------------------------------------ recipe cleaning


def test_recipe_ids_are_unique_and_int64(cleaned):
    rec, _ = cleaned
    assert rec.frame["id"].is_unique
    assert str(rec.frame["id"].dtype) == "int64"


def test_exact_duplicate_recipe_rows_are_dropped_with_a_count(cleaned):
    rec, _ = cleaned
    ledger = rec.ledger.to_frame()
    row = ledger[ledger["stage"] == "drop_exact_duplicate_rows"].iloc[0]
    assert row["n_removed"] >= 1


def test_conflicting_recipe_ids_are_quarantined_not_kept_first(cleaned):
    rec, _ = cleaned
    assert rec.notes["n_conflicting_recipe_ids_quarantined"] >= 1
    assert "recipes_conflicting_ids" in rec.quarantine
    quarantined = set(rec.quarantine["recipes_conflicting_ids"]["id"].tolist())
    assert not quarantined & set(rec.frame["id"].tolist())


def test_non_positive_minutes_are_excluded(cleaned):
    rec, _ = cleaned
    assert (rec.frame["minutes"] > 0).all()
    assert 999_001 not in set(rec.frame["id"].tolist())


def test_malformed_list_field_does_not_reach_the_catalogue(cleaned):
    rec, _ = cleaned
    assert 999_002 not in set(rec.frame["id"].tolist())


def test_missing_name_and_bad_date_are_excluded(cleaned):
    rec, _ = cleaned
    ids = set(rec.frame["id"].tolist())
    assert 999_003 not in ids
    assert 999_004 not in ids


def test_long_durations_are_flagged_not_deleted(cleaned, cfg):
    rec, _ = cleaned
    threshold = float(cfg.cleaning.recipes["minutes"]["flag_above_minutes"])
    long_ones = rec.frame[rec.frame["minutes"] > threshold]
    if len(long_ones):
        assert long_ones["minutes_flagged_long"].all()
    assert "minutes_flagged_long" in rec.frame.columns


def test_raw_strings_and_parse_status_are_retained(cleaned):
    rec, _ = cleaned
    for col in ("tags", "ingredients", "steps", "nutrition"):
        assert f"raw_{col}" in rec.frame.columns
        assert f"{col}_parse_status" in rec.frame.columns


def test_derived_counts_are_separate_from_source_counts(cleaned):
    rec, _ = cleaned
    assert "n_ingredients" in rec.frame.columns
    assert "n_ingredients_parsed" in rec.frame.columns


def test_nutrition_is_retained_but_flagged_unverified(cleaned, cfg):
    rec, _ = cleaned
    assert "nutrition" in rec.frame.columns
    assert rec.notes["nutrition"]["used_in_core_model"] is False
    assert cfg.cleaning.recipes["nutrition"]["units_verified"] is False


def test_every_surviving_recipe_gets_exactly_one_band(cleaned):
    rec, _ = cleaned
    assert rec.frame["band"].notna().all()


# ------------------------------------------------------------------ interactions


def test_review_text_never_reaches_the_processed_table(cleaned):
    _, inter = cleaned
    assert "review" not in inter.frame.columns


def test_invalid_ratings_are_quarantined(cleaned):
    _, inter = cleaned
    assert "interactions_invalid_ratings" in inter.quarantine
    assert inter.frame["rating"].isin([0, 1, 2, 3, 4, 5]).all()


def test_zero_rating_is_unknown_not_negative_and_not_positive(cleaned):
    _, inter = cleaned
    zeros = inter.frame[inter.frame["rating"] == 0]
    assert len(zeros) > 0, "the fixture should contain unknown ratings"
    assert not zeros["is_positive"].any()
    assert zeros["is_unknown_rating"].all()


def test_positive_definition_is_four_and_five(cleaned):
    _, inter = cleaned
    positives = inter.frame[inter.frame["is_positive"]]
    assert set(positives["rating"].unique()) <= {4, 5}


def test_missing_keys_and_bad_dates_are_quarantined(cleaned):
    _, inter = cleaned
    assert "interactions_missing_keys" in inter.quarantine
    assert "interactions_invalid_dates" in inter.quarantine
    assert inter.frame["user_id"].notna().all()
    assert inter.frame["recipe_id"].notna().all()


def test_orphan_recipe_ids_are_dropped_with_counts(cleaned):
    rec, inter = cleaned
    assert inter.notes["n_orphan_interactions"] >= 1
    assert inter.frame["recipe_id"].isin(set(rec.frame["id"].tolist())).all()


def test_repeat_pairs_collapse_to_one_row_each(cleaned):
    _, inter = cleaned
    assert not inter.frame.duplicated(subset=["user_id", "recipe_id"]).any()


def test_earliest_event_is_retained_not_the_later_one(cfg):
    """A later, contradicting rating must never be averaged into the earlier history."""
    from foodcom.data.clean import clean_interactions, clean_recipes
    from foodcom.testing.synthetic import make_synthetic_raw

    recipes_raw, _ = make_synthetic_raw(seed=3, n_recipes=30, n_users=2)
    rec = clean_recipes(recipes_raw, cfg)
    rid = int(rec.frame["id"].iloc[0])
    interactions = pd.DataFrame(
        [
            {"user_id": 1, "recipe_id": rid, "date": "2015-01-01", "rating": 5, "review": "x"},
            {"user_id": 1, "recipe_id": rid, "date": "2016-01-01", "rating": 1, "review": "y"},
        ]
    )
    out = clean_interactions(interactions, rec.frame, cfg)
    assert len(out.frame) == 1
    assert out.frame.iloc[0]["rating"] == 5
    assert str(pd.Timestamp(out.frame.iloc[0]["date"]).date()) == "2015-01-01"
    assert out.frame.iloc[0]["label_eligible"]


def test_tied_earliest_conflict_is_excluded_from_labels_but_still_seen(cfg):
    from foodcom.data.clean import clean_interactions, clean_recipes
    from foodcom.testing.synthetic import make_synthetic_raw

    recipes_raw, _ = make_synthetic_raw(seed=3, n_recipes=30, n_users=2)
    rec = clean_recipes(recipes_raw, cfg)
    rid = int(rec.frame["id"].iloc[0])
    interactions = pd.DataFrame(
        [
            {"user_id": 1, "recipe_id": rid, "date": "2015-01-01", "rating": 5, "review": "x"},
            {"user_id": 1, "recipe_id": rid, "date": "2015-01-01", "rating": 2, "review": "y"},
        ]
    )
    out = clean_interactions(interactions, rec.frame, cfg)
    assert len(out.frame) == 1
    row = out.frame.iloc[0]
    assert row["tied_earliest_conflict"]
    assert not row["label_eligible"]
    assert not row["is_positive"]
    assert out.notes["n_tied_earliest_conflicts"] == 1


def test_interaction_before_submission_is_excluded(cleaned):
    _, inter = cleaned
    assert inter.notes["n_interactions_before_submission"] >= 1


def test_join_is_many_to_one_and_never_multiplies_rows(cleaned):
    rec, inter = cleaned
    before = len(inter.frame)
    merged = inter.frame.merge(
        rec.frame[["id", "minutes"]], left_on="recipe_id", right_on="id", how="left"
    )
    assert len(merged) == before


def test_exclusion_ledger_is_ordered_and_reconciles(cleaned):
    rec, inter = cleaned
    for result in (rec, inter):
        ledger = result.ledger.to_frame()
        assert list(ledger["order"]) == sorted(ledger["order"])
        # Each stage's n_in must equal the previous stage's n_out: no unexplained gap.
        for prev, cur in zip(ledger.itertuples(), ledger.iloc[1:].itertuples(), strict=False):
            assert cur.n_in == prev.n_out, f"gap at stage {cur.stage}"
