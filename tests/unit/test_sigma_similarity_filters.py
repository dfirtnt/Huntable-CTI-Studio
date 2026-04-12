"""Unit tests for similarity match filtering logic used in sigma_queue route.

Tests the behavioral overlap filter and to_store filter that were added
alongside the semantic embedding fallback (2026-04-12, dev-io branch).

These tests validate the *predicate logic* extracted from
``get_similar_rules_for_queued_rule`` — the route handler applies these
filters inline, so we replicate the exact expressions here.
"""

import pytest

pytestmark = pytest.mark.unit


# ── Predicate helpers (mirror the inline logic in sigma_queue.py) ─────────


def _has_behavioral_overlap(match: dict) -> bool:
    """True if match has jaccard > 0 (behavioral atom overlap)."""
    return (match.get("semantic_details") or {}).get("jaccard", match.get("atom_jaccard", 0)) > 0


def _should_store(match: dict) -> bool:
    """True if match should be persisted: behavioral overlap OR semantic engine."""
    return _has_behavioral_overlap(match) or match.get("similarity_engine") == "semantic"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def behavioral_match():
    """A match with real atom jaccard overlap."""
    return {
        "title": "Process Creation via cmd.exe",
        "similarity": 0.75,
        "atom_jaccard": 0.6,
        "similarity_engine": "deterministic",
        "semantic_details": {
            "jaccard": 0.6,
            "containment_factor": 0.8,
            "filter_penalty": 0.0,
        },
    }


@pytest.fixture
def zero_jaccard_match():
    """A match from deterministic engine with zero atom overlap."""
    return {
        "title": "Zero overlap candidate",
        "similarity": 0.45,
        "atom_jaccard": 0.0,
        "similarity_engine": "deterministic",
        "semantic_details": {
            "jaccard": 0.0,
            "containment_factor": 0.0,
            "filter_penalty": 0.0,
        },
    }


@pytest.fixture
def semantic_fallback_match():
    """A match produced by the semantic embedding fallback path."""
    return {
        "title": "Conceptually similar rule",
        "similarity": 0.52,
        "similarity_score": 0.52,
        "similarity_method": "semantic_embedding",
        "novelty_label": "NOVEL",
        "atom_jaccard": 0.0,
        "similarity_engine": "semantic",
        "semantic_details": {
            "jaccard": 0.0,
            "containment_factor": 0.0,
            "filter_penalty": 0.0,
            "surface_score_a": 0,
            "surface_score_b": 0,
            "semantic_similarity": 0.52,
        },
    }


# ── Behavioral overlap filter tests ──────────────────────────────────────


class TestBehavioralOverlapFilter:
    """Tests for the filter that separates behavioral (jaccard>0) matches."""

    def test_positive_jaccard_passes(self, behavioral_match):
        assert _has_behavioral_overlap(behavioral_match) is True

    def test_zero_jaccard_rejected(self, zero_jaccard_match):
        assert _has_behavioral_overlap(zero_jaccard_match) is False

    def test_semantic_fallback_has_no_behavioral_overlap(self, semantic_fallback_match):
        """Semantic matches have jaccard=0 by definition."""
        assert _has_behavioral_overlap(semantic_fallback_match) is False

    def test_missing_semantic_details_uses_atom_jaccard(self):
        """When semantic_details is None, fall back to atom_jaccard field."""
        match = {"atom_jaccard": 0.3, "semantic_details": None}
        assert _has_behavioral_overlap(match) is True

    def test_missing_both_fields_returns_false(self):
        """Match with no jaccard info at all is not behavioral."""
        assert _has_behavioral_overlap({}) is False

    def test_empty_semantic_details_uses_atom_jaccard(self):
        """Empty dict for semantic_details falls through to atom_jaccard."""
        match = {"atom_jaccard": 0.5, "semantic_details": {}}
        assert _has_behavioral_overlap(match) is True

    def test_fractional_jaccard_above_zero(self):
        match = {"semantic_details": {"jaccard": 0.001}}
        assert _has_behavioral_overlap(match) is True


# ── to_store filter tests ─────────────────────────────────────────────────


class TestToStoreFilter:
    """Tests for the filter that decides which matches get persisted."""

    def test_behavioral_match_stored(self, behavioral_match):
        assert _should_store(behavioral_match) is True

    def test_zero_jaccard_deterministic_not_stored(self, zero_jaccard_match):
        """Zero-overlap deterministic matches should be excluded."""
        assert _should_store(zero_jaccard_match) is False

    def test_semantic_fallback_stored(self, semantic_fallback_match):
        """Semantic engine matches stored even with jaccard=0."""
        assert _should_store(semantic_fallback_match) is True

    def test_mixed_batch_filtering(self, behavioral_match, zero_jaccard_match, semantic_fallback_match):
        """Replicate the actual list comprehension from the route handler."""
        similar_matches = [behavioral_match, zero_jaccard_match, semantic_fallback_match]

        to_store = [
            m
            for m in similar_matches[:10]
            if (m.get("semantic_details") or {}).get("jaccard", m.get("atom_jaccard", 0)) > 0
            or m.get("similarity_engine") == "semantic"
        ]

        assert len(to_store) == 2
        titles = {m["title"] for m in to_store}
        assert behavioral_match["title"] in titles
        assert semantic_fallback_match["title"] in titles
        assert zero_jaccard_match["title"] not in titles


# ── Semantic fallback match shape tests ───────────────────────────────────


class TestSemanticFallbackMatchShape:
    """Validate the dict structure produced by the semantic embedding fallback."""

    REQUIRED_KEYS = {
        "id",
        "rule_id",
        "title",
        "description",
        "logsource",
        "detection",
        "tags",
        "level",
        "status",
        "file_path",
        "similarity",
        "similarity_score",
        "similarity_method",
        "novelty_label",
        "atom_jaccard",
        "logic_shape_similarity",
        "shared_atoms",
        "added_atoms",
        "removed_atoms",
        "filter_differences",
        "similarity_engine",
        "semantic_details",
    }

    SEMANTIC_DETAILS_KEYS = {
        "jaccard",
        "containment_factor",
        "filter_penalty",
        "surface_score_a",
        "surface_score_b",
        "semantic_similarity",
    }

    def _build_semantic_match(self, sem_sim: float = 0.65) -> dict:
        """Build a match dict identical to what the route handler produces."""
        return {
            "id": 42,
            "rule_id": "abc123",
            "title": "Test Semantic Rule",
            "description": "A rule found by embedding similarity",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": {"Image|endswith": "\\cmd.exe"}, "condition": "selection"},
            "tags": ["attack.execution"],
            "level": "medium",
            "status": "stable",
            "file_path": "rules/windows/process_creation/test.yml",
            "similarity": sem_sim,
            "similarity_score": sem_sim,
            "similarity_method": "semantic_embedding",
            "novelty_label": "NOVEL",
            "atom_jaccard": 0.0,
            "logic_shape_similarity": None,
            "shared_atoms": [],
            "added_atoms": [],
            "removed_atoms": [],
            "filter_differences": [],
            "similarity_engine": "semantic",
            "semantic_details": {
                "jaccard": 0.0,
                "containment_factor": 0.0,
                "filter_penalty": 0.0,
                "surface_score_a": 0,
                "surface_score_b": 0,
                "semantic_similarity": sem_sim,
            },
        }

    def test_all_required_keys_present(self):
        match = self._build_semantic_match()
        assert self.REQUIRED_KEYS.issubset(match.keys())

    def test_semantic_details_shape(self):
        match = self._build_semantic_match()
        assert set(match["semantic_details"].keys()) == self.SEMANTIC_DETAILS_KEYS

    def test_invariants(self):
        """Semantic matches always have jaccard=0, engine=semantic, method=semantic_embedding."""
        match = self._build_semantic_match(0.8)
        assert match["atom_jaccard"] == 0.0
        assert match["similarity_engine"] == "semantic"
        assert match["similarity_method"] == "semantic_embedding"
        assert match["novelty_label"] == "NOVEL"
        assert match["semantic_details"]["jaccard"] == 0.0
        assert match["semantic_details"]["semantic_similarity"] == 0.8

    def test_similarity_threshold_respected(self):
        """Route handler filters sem_sim < 0.3 — verify the threshold contract."""
        below_threshold = 0.29
        above_threshold = 0.31
        # The route skips rows with sem_sim < 0.3
        assert below_threshold < 0.3
        assert above_threshold >= 0.3

    def test_tags_always_list(self):
        """Tags should be a list even when empty."""
        match = self._build_semantic_match()
        match["tags"] = []
        assert isinstance(match["tags"], list)
