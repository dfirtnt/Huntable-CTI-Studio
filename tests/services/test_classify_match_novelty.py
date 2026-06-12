"""Tests for the shared per-match novelty classifier (Phase 2 of the
sigma-similarity unification: docs/development/sigma-similarity-unification-plan-2026-06-05.md).

`classify_match_novelty` is the single source of truth for the legacy
atom/logic-shape thresholds + exact-hash override. ai.py's /sigma-matches route
classified each candidate match inline with a duplicated copy of these rules;
this function replaces that copy. It classifies ONE candidate match (per-match
semantics), not a whole assessment — distinct from the proposed rule's single
overall verdict.
"""

import pytest

from src.services.sigma_novelty_service import NoveltyLabel, classify_match_novelty

pytestmark = pytest.mark.unit


def test_exact_hash_match_is_duplicate_regardless_of_metrics():
    """An exact-hash match is a DUPLICATE even if atom/logic metrics are low."""
    match = {"exact_hash_match": True, "atom_jaccard": 0.1, "logic_shape_similarity": 0.1}
    assert classify_match_novelty(match) == "DUPLICATE"


def test_high_atom_and_logic_is_duplicate():
    match = {"atom_jaccard": 0.97, "logic_shape_similarity": 0.98}
    assert classify_match_novelty(match) == NoveltyLabel.DUPLICATE


def test_atom_above_080_is_similar():
    match = {"atom_jaccard": 0.85, "logic_shape_similarity": 0.2}
    assert classify_match_novelty(match) == NoveltyLabel.SIMILAR


def test_low_atom_is_novel():
    match = {"atom_jaccard": 0.4, "logic_shape_similarity": 0.9}
    assert classify_match_novelty(match) == NoveltyLabel.NOVEL


def test_none_logic_shape_is_treated_as_perfect():
    """logic_shape None (early-exit perfect-match signal) must count as 1.0, so a
    high-atom match with None logic still classifies DUPLICATE (not NOVEL)."""
    match = {"atom_jaccard": 0.99, "logic_shape_similarity": None}
    assert classify_match_novelty(match) == NoveltyLabel.DUPLICATE


def test_missing_metrics_default_to_novel():
    assert classify_match_novelty({}) == NoveltyLabel.NOVEL


def test_classification_is_per_match():
    """Each candidate is classified on its own metrics — the regression guard for
    replacing ai.py's per-match loop (must NOT broadcast one label to all)."""
    matches = [
        {"atom_jaccard": 0.99, "logic_shape_similarity": 0.99},  # DUPLICATE
        {"atom_jaccard": 0.85, "logic_shape_similarity": 0.10},  # SIMILAR
        {"atom_jaccard": 0.40, "logic_shape_similarity": 0.90},  # NOVEL
    ]
    labels = [str(classify_match_novelty(m)) for m in matches]
    assert labels == ["DUPLICATE", "SIMILAR", "NOVEL"]
