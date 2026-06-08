"""Tests for the unified similarity-match serializer (Phase 1 of the
sigma-similarity unification: docs/development/sigma-similarity-unification-plan-2026-06-05.md).

The serializer takes a raw match dict as emitted by
``SigmaMatchingService.assess_rule_novelty()`` and projects it onto the single
canonical contract that every similarity endpoint will emit, while keeping
additive legacy aliases so existing frontends keep working until Phase 4/5.
"""

import pytest

from src.services.similarity_serialization import serialize_similarity_match

# Pure unit tests — no infrastructure required.
pytestmark = pytest.mark.unit


def test_containment_is_lifted_from_semantic_details_to_top_level():
    """`overlap_ratio_a` (directional containment) must surface as a top-level
    canonical `containment` field so every surface can read it the same way.

    Today only the queue renderer reaches into semantic_details.overlap_ratio_a;
    that is the exact divergence that let the 2026-06-05 containment bug hide.
    """
    match = {
        "rule_id": "abc-123",
        "similarity": 0.42,
        "atom_jaccard": 0.5,
        "logic_shape_similarity": 0.3,
        "similarity_engine": "deterministic",
        "semantic_details": {
            "overlap_ratio_a": 0.65,
            "containment_factor": 0.85,
            "jaccard": 0.5,
        },
    }

    result = serialize_similarity_match(match)

    assert result["containment"] == 0.65


def test_containment_is_none_for_legacy_engine_without_semantic_details():
    """Legacy matches carry no semantic_details; containment must be None, not 0."""
    match = {"rule_id": "x", "similarity": 0.1, "similarity_engine": "legacy"}

    result = serialize_similarity_match(match)

    assert result["containment"] is None


def test_canonical_scalar_fields_passed_through():
    match = {
        "rule_id": "abc-123",
        "similarity": 0.42,
        "atom_jaccard": 0.5,
        "logic_shape_similarity": 0.3,
        "novelty_label": "SIMILAR",
        "novelty_score": 0.58,
        "similarity_engine": "deterministic",
    }

    result = serialize_similarity_match(match)

    assert result["similarity"] == 0.42
    assert result["atom_jaccard"] == 0.5
    assert result["logic_shape_similarity"] == 0.3
    assert result["novelty_label"] == "SIMILAR"
    assert result["novelty_score"] == 0.58
    assert result["similarity_engine"] == "deterministic"


def test_none_logic_shape_is_preserved_not_coerced():
    """logic_shape_similarity is None on the perfect-match early-exit path; the
    serializer must not coerce it to 0.0 (which would misrender as 0% shape)."""
    match = {"rule_id": "x", "similarity": 1.0, "logic_shape_similarity": None}

    result = serialize_similarity_match(match)

    assert result["logic_shape_similarity"] is None


def test_explainability_lists_passed_through():
    match = {
        "rule_id": "x",
        "similarity": 0.4,
        "shared_atoms": ["a", "b"],
        "added_atoms": ["c"],
        "removed_atoms": ["d"],
        "filter_differences": ["e"],
    }

    result = serialize_similarity_match(match)

    assert result["shared_atoms"] == ["a", "b"]
    assert result["added_atoms"] == ["c"]
    assert result["removed_atoms"] == ["d"]
    assert result["filter_differences"] == ["e"]


def test_explainability_lists_default_to_empty():
    result = serialize_similarity_match({"rule_id": "x", "similarity": 0.4})

    assert result["shared_atoms"] == []
    assert result["added_atoms"] == []
    assert result["removed_atoms"] == []
    assert result["filter_differences"] == []


def test_identity_and_metadata_fields_passed_through():
    match = {
        "id": 7,
        "rule_id": "abc-123",
        "title": "Suspicious rundll32",
        "description": "desc",
        "tags": ["attack.t1218"],
        "file_path": "rules/x.yml",
        "similarity": 0.4,
    }

    result = serialize_similarity_match(match)

    assert result["id"] == 7
    assert result["rule_id"] == "abc-123"
    assert result["title"] == "Suspicious rundll32"
    assert result["tags"] == ["attack.t1218"]
    assert result["file_path"] == "rules/x.yml"


def test_legacy_aliases_are_additive():
    """Existing frontends read similarity_score and similarity_breakdown.* . Until
    Phase 4/5 the serializer must keep emitting these alongside canonical keys."""
    match = {
        "rule_id": "x",
        "similarity": 0.42,
        "atom_jaccard": 0.5,
        "logic_shape_similarity": 0.3,
    }

    result = serialize_similarity_match(match)

    assert result["similarity_score"] == result["similarity"] == 0.42
    assert result["similarity_breakdown"]["atom_jaccard"] == 0.5
    assert result["similarity_breakdown"]["logic_shape_similarity"] == 0.3


def test_semantic_details_preserved_for_deterministic_surfaces():
    sd = {"overlap_ratio_a": 0.65, "containment_factor": 0.85, "jaccard": 0.5}
    match = {"rule_id": "x", "similarity": 0.4, "semantic_details": sd}

    result = serialize_similarity_match(match)

    assert result["semantic_details"] == sd
