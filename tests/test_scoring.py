"""Text rendering, encoders, the embedding cache, profiles and the relevance score."""

from __future__ import annotations

import numpy as np
import pytest

from foodcom.features.embed import EmbeddingStore, build_embeddings
from foodcom.features.encoders import DeterministicTestEncoder, l2_normalise
from foodcom.features.profiles import build_profiles
from foodcom.features.text import (
    assert_no_forbidden_fields,
    render_catalogue,
    render_recipe_text,
    select_tags,
)
from foodcom.models.scoring import half_shifted_cosine, score_candidates
from foodcom.utils.hashing import sha256_text

# ------------------------------------------------------------------ tag whitelist


def test_duration_tags_are_denied(real_config):
    rules = real_config.tags
    for tag in (
        "time-to-make",
        "60-minutes-or-less",
        "30-minutes-or-less",
        "15-minutes-or-less",
        "4-hours-or-less",
        "weeknight",
    ):
        assert not rules.allowed(tag), f"{tag} encodes the band and must be excluded"


def test_administrative_and_label_derived_tags_are_denied(real_config):
    rules = real_config.tags
    for tag in ("ratings", "popular-recipes", "reviews", "contributor-favourite", "2011"):
        assert not rules.allowed(tag)


def test_descriptive_tags_are_allowed(real_config):
    rules = real_config.tags
    for tag in ("italian", "main-dish", "chicken", "vegetarian", "comfort-food"):
        assert rules.allowed(tag)


def test_unknown_tags_are_excluded_by_default(real_config):
    assert real_config.tags.unknown_tag_policy == "exclude"
    assert not real_config.tags.allowed("some-tag-that-does-not-exist-anywhere")


def test_select_tags_preserves_order_and_caps_length(real_config):
    tags = ["italian", "time-to-make", "chicken", "easy", "vegetarian", "spicy",
            "sweet", "savory", "oven", "bake", "salads", "pizza", "beef", "pork"]
    picked = select_tags(tags, real_config.tags)
    assert "time-to-make" not in picked
    assert picked[0] == "italian"
    assert len(picked) <= real_config.tags.max_tags_per_recipe


# ------------------------------------------------------------------ rendered text


def test_forbidden_fields_are_structurally_impossible(real_config):
    assert_no_forbidden_fields(real_config.model)


def test_rendered_text_contains_no_forbidden_content(real_config):
    row = {
        "name": "Test dish",
        "ingredients": ["garlic", "onion"],
        "tags": ["italian", "60-minutes-or-less"],
        "description": "A description.",
        "review": "THIS REVIEW TEXT MUST NEVER APPEAR",
        "user_id": 424242,
        "rating": 5,
        "submitted": "2011-01-01",
        "contributor_id": 999,
    }
    text = render_recipe_text(row, real_config.model, real_config.tags)
    for forbidden in ("THIS REVIEW TEXT", "424242", "2011-01-01", "999",
                      "60-minutes-or-less"):
        assert forbidden not in text
    assert "Test dish" in text
    assert "garlic" in text
    assert "italian" in text


def test_rendered_text_is_deterministic(real_config):
    row = {"name": "A", "ingredients": ["b", "c"], "tags": ["italian"], "description": "d"}
    a = render_recipe_text(row, real_config.model, real_config.tags)
    b = render_recipe_text(row, real_config.model, real_config.tags)
    assert a == b
    assert sha256_text(a) == sha256_text(b)


def test_description_is_truncated_at_the_configured_length(real_config):
    limit = real_config.model.text_render.description_max_chars
    row = {"name": "A", "ingredients": ["b"], "tags": [], "description": "x" * (limit + 500)}
    text = render_recipe_text(row, real_config.model, real_config.tags)
    assert len(text) < limit + 100


def test_render_catalogue_hashes_every_row(cleaned, real_config):
    rec, _ = cleaned
    rendered = render_catalogue(rec.frame, real_config.model, real_config.tags)
    assert len(rendered) == len(rec.frame)
    assert rendered["text_sha256"].notna().all()
    assert (rendered["text_sha256"].str.len() == 64).all()


# ------------------------------------------------------------------ encoders


def test_test_encoder_is_not_research_grade():
    enc = DeterministicTestEncoder()
    assert enc.is_research_grade is False
    assert enc.provenance()["is_research_grade"] is False
    assert "SYNTHETIC" in enc.provenance()["note"]


def test_encoder_output_is_unit_normalised():
    enc = DeterministicTestEncoder(dimension=16)
    vectors = enc.encode(["one", "two", "three"])
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_encoder_is_deterministic():
    a = DeterministicTestEncoder(dimension=16).encode(["alpha", "beta"])
    b = DeterministicTestEncoder(dimension=16).encode(["alpha", "beta"])
    assert np.array_equal(a, b)


def test_l2_normalise_leaves_a_zero_row_zero():
    out = l2_normalise(np.array([[0.0, 0.0], [3.0, 4.0]]))
    assert np.array_equal(out[0], np.zeros(2))
    assert np.allclose(np.linalg.norm(out[1]), 1.0)


# ------------------------------------------------------------------ embedding cache


def test_cache_reuses_vectors_for_identical_text(cleaned, real_config, tmp_path):
    rec, _ = cleaned
    rendered = render_catalogue(rec.frame.head(50), real_config.model, real_config.tags)
    enc = DeterministicTestEncoder(dimension=16)

    first = build_embeddings(rendered, enc, cache_dir=tmp_path / "cache")
    second = build_embeddings(rendered, enc, cache_dir=tmp_path / "cache")
    assert np.array_equal(first.vectors, second.vectors)
    assert list(first.recipe_ids) == list(second.recipe_ids)


def test_cache_is_invalidated_when_the_text_changes(cleaned, real_config, tmp_path):
    rec, _ = cleaned
    rendered = render_catalogue(rec.frame.head(20), real_config.model, real_config.tags)
    enc = DeterministicTestEncoder(dimension=16)
    first = build_embeddings(rendered, enc, cache_dir=tmp_path / "cache")

    changed = rendered.copy()
    changed.loc[0, "text"] = "completely different text"
    changed.loc[0, "text_sha256"] = sha256_text("completely different text")
    second = build_embeddings(changed, enc, cache_dir=tmp_path / "cache")

    assert not np.array_equal(first.vectors[0], second.vectors[0])
    assert np.array_equal(first.vectors[1:], second.vectors[1:])


def test_cache_is_ignored_when_the_model_identity_changes(cleaned, real_config, tmp_path):
    """A stale vector from another model must never be mixed into a result."""
    rec, _ = cleaned
    rendered = render_catalogue(rec.frame.head(10), real_config.model, real_config.tags)
    enc_a = DeterministicTestEncoder(dimension=16)
    build_embeddings(rendered, enc_a, cache_dir=tmp_path / "cache")

    class OtherModel(DeterministicTestEncoder):
        def provenance(self):
            out = super().provenance()
            out["model_id"] = "a-different-model"
            return out

    store = build_embeddings(rendered, OtherModel(dimension=16), cache_dir=tmp_path / "cache")
    assert store.provenance["model_id"] == "a-different-model"


def test_store_round_trips(tmp_path):
    store = EmbeddingStore(
        recipe_ids=np.array([3, 1, 2], dtype="int64"),
        vectors=l2_normalise(np.random.default_rng(0).normal(size=(3, 8)).astype("float32")),
        text_sha256=np.array(["a", "b", "c"], dtype=object),
        provenance={"model_id": "x", "model_revision": None},
    )
    store.save(tmp_path / "s")
    back = EmbeddingStore.load(tmp_path / "s")
    assert np.array_equal(store.vectors, back.vectors)
    assert list(store.recipe_ids) == list(back.recipe_ids)


# ------------------------------------------------------------------ profiles + score


def test_profile_is_the_normalised_mean_of_positive_history():
    vectors = l2_normalise(np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32"))
    store = EmbeddingStore(
        recipe_ids=np.array([10, 20], dtype="int64"),
        vectors=vectors,
        text_sha256=np.array(["a", "b"], dtype=object),
        provenance={"model_id": "x", "model_revision": None},
    )
    profiles = build_profiles({1: {10, 20}}, store, users=[1])
    expected = np.array([0.5, 0.5]) / np.linalg.norm([0.5, 0.5])
    assert np.allclose(profiles.vector(1), expected, atol=1e-6)
    assert profiles.n_used(1) == 2


def test_user_with_no_positive_history_is_cold():
    store = EmbeddingStore(
        recipe_ids=np.array([10], dtype="int64"),
        vectors=l2_normalise(np.array([[1.0, 0.0]], dtype="float32")),
        text_sha256=np.array(["a"], dtype=object),
        provenance={"model_id": "x", "model_revision": None},
    )
    profiles = build_profiles({1: set()}, store, users=[1])
    assert 1 in profiles.cold_users


def test_zero_norm_profile_is_cold_not_nan():
    """Opposing vectors cancel. The result must be a cold flag, not a NaN score."""
    store = EmbeddingStore(
        recipe_ids=np.array([10, 20], dtype="int64"),
        vectors=np.array([[1.0, 0.0], [-1.0, 0.0]], dtype="float32"),
        text_sha256=np.array(["a", "b"], dtype=object),
        provenance={"model_id": "x", "model_revision": None},
    )
    profiles = build_profiles({1: {10, 20}}, store, users=[1])
    assert 1 in profiles.cold_users
    with pytest.raises(ValueError, match="cold"):
        score_candidates(1, np.array([10], dtype="int64"), profiles, store)


@pytest.mark.parametrize(
    ("cosine", "expected"),
    [(1.0, 1.0), (0.0, 0.5), (-1.0, 0.0), (0.5, 0.75)],
)
def test_score_maps_cosine_onto_the_unit_interval(cosine, expected):
    profile = np.array([1.0, 0.0])
    angle = np.arccos(np.clip(cosine, -1, 1))
    recipe = np.array([[np.cos(angle), np.sin(angle)]])
    assert np.isclose(half_shifted_cosine(profile, recipe)[0], expected, atol=1e-9)


def test_score_stays_inside_the_unit_interval(cleaned, real_config, tmp_path):
    rec, _ = cleaned
    rendered = render_catalogue(rec.frame, real_config.model, real_config.tags)
    store = build_embeddings(rendered, DeterministicTestEncoder(dimension=24), cache_dir=None)
    ids = store.recipe_ids[:30]
    profiles = build_profiles({7: {int(i) for i in ids[:6]}}, store, users=[7])
    scores = score_candidates(7, ids, profiles, store)
    assert scores.min() >= 0.0
    assert scores.max() <= 1.0


def test_non_unit_vectors_raise_rather_than_being_clamped():
    profile = np.array([3.0, 4.0])  # norm 5, not a unit vector
    recipes = np.array([[3.0, 4.0]])
    with pytest.raises(AssertionError, match="unit-normalised"):
        half_shifted_cosine(profile, recipes)
