"""Unit tests for idea snapshot hashing and versioning policy helpers."""

from app.services.idea_versioning_policy import (
    compute_content_hash,
    compute_content_hash_from_version_row,
    snapshot_payload_from_idea,
)


def test_compute_content_hash_stable_for_same_payload():
    idea = {
        "title": "T",
        "description": "<p>x</p>",
        "business_model_canvas": None,
        "pitch_deck": None,
        "product_requirements_document": None,
        "provisional_patent": None,
    }
    a = compute_content_hash(idea)
    b = compute_content_hash(idea)
    assert a == b
    assert len(a) == 64


def test_compute_content_hash_differs_when_title_changes():
    base = {
        "title": "A",
        "description": None,
        "business_model_canvas": None,
        "pitch_deck": None,
        "product_requirements_document": None,
        "provisional_patent": None,
    }
    other = {**base, "title": "B"}
    assert compute_content_hash(base) != compute_content_hash(other)


def test_compute_content_hash_from_version_row_matches_direct():
    idea = {
        "title": "Hello",
        "description": "D",
        "business_model_canvas": "bmc",
        "pitch_deck": "pd",
        "product_requirements_document": "prd",
        "provisional_patent": "pat",
    }
    h1 = compute_content_hash(idea)
    h2 = compute_content_hash_from_version_row(idea)
    assert h1 == h2


def test_snapshot_payload_json_is_sorted_keys():
    s = snapshot_payload_from_idea({"title": "z", "description": "a"})
    assert s.index('"description"') < s.index('"title"')
