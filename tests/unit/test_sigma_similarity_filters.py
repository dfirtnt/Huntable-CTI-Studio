"""Unit tests for similarity match filtering logic.

Covers two predicate families:
  - sigma_queue route: jaccard > 0 (behavioral atom overlap, for storage)
  - agentic_workflow + ai route: similarity > 0 (weighted score, for display)

Tests validate the *predicate logic* extracted from inline list comprehensions
in the respective handlers, so they remain fast and dependency-free.
"""

import pytest

pytestmark = pytest.mark.unit


# ── Predicate helpers (mirror the inline logic in sigma_queue.py) ─────────


def _has_behavioral_overlap(match: dict) -> bool:
    """True if match has jaccard > 0 (behavioral atom overlap)."""
    return (match.get("semantic_details") or {}).get("jaccard", match.get("atom_jaccard", 0)) > 0


def _should_store(match: dict) -> bool:
    """True if match should be persisted: behavioral overlap (jaccard > 0)."""
    return _has_behavioral_overlap(match)


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

    def test_semantic_fallback_not_stored(self, semantic_fallback_match):
        """Semantic engine matches with jaccard=0 are not stored (semantic fallback reverted)."""
        assert _should_store(semantic_fallback_match) is False

    def test_mixed_batch_filtering(self, behavioral_match, zero_jaccard_match, semantic_fallback_match):
        """Replicate the actual list comprehension from the route handler."""
        similar_matches = [behavioral_match, zero_jaccard_match, semantic_fallback_match]

        to_store = [
            m
            for m in similar_matches[:10]
            if (m.get("semantic_details") or {}).get("jaccard", m.get("atom_jaccard", 0)) > 0
        ]

        assert len(to_store) == 1
        assert to_store[0]["title"] == behavioral_match["title"]


# ── Soft cross-field match filtering tests ────────────────────────────────


class TestSoftCrossFieldMatchFiltering:
    """Verify that soft cross-field matches (jaccard > 0 via dampened soft path)
    are correctly stored and displayed."""

    def test_soft_match_stored(self):
        """A match with small but positive jaccard from soft matching is stored."""
        soft_match = {
            "title": "Rundll32 via CommandLine",
            "atom_jaccard": 0.10,
            "similarity_engine": "deterministic",
            "semantic_details": {"jaccard": 0.10, "containment_factor": 0.0, "filter_penalty": 0.0},
        }
        assert _should_store(soft_match) is True

    def test_zero_jaccard_after_soft_matching_not_stored(self):
        """If soft matching still yields 0 (no shared exe values), not stored."""
        no_overlap = {
            "title": "DNS rule vs process rule",
            "atom_jaccard": 0.0,
            "similarity_engine": "deterministic",
            "semantic_details": {"jaccard": 0.0},
        }
        assert _should_store(no_overlap) is False

    def test_batch_with_soft_and_zero_matches(self):
        """Mixed batch: soft matches kept, zeros dropped."""
        matches = [
            {"title": "Strong", "semantic_details": {"jaccard": 0.75}},
            {"title": "Soft", "semantic_details": {"jaccard": 0.10}},
            {"title": "Zero", "semantic_details": {"jaccard": 0.0}},
            {"title": "Missing", "atom_jaccard": 0.0},
        ]
        stored = [m for m in matches if _should_store(m)]
        assert len(stored) == 2
        titles = {m["title"] for m in stored}
        assert titles == {"Strong", "Soft"}


# ── Display filter: similarity > 0 (agentic_workflow + ai route) ─────────
#
# These predicates guard what ends up in `similar_rules` / `similar_existing_rules`
# on the novelty_results dict.  Mirrors the inline comprehension:
#   [r for r in similar_rules if r.get("similarity", 0.0) > 0][:10]


def _display_filter(matches: list, limit: int = 10) -> list:
    """Mirror the display filter added to agentic_workflow.py and ai.py."""
    return [r for r in matches if r.get("similarity", 0.0) > 0][:limit]


class TestWorkflowDisplayFilter:
    """Tests for the similarity > 0 display filter (agentic_workflow.py / ai.py)."""

    def test_all_zero_similarity_returns_empty(self):
        """When every candidate scores 0.0 the display list should be empty."""
        candidates = [
            {"title": "Rule A", "similarity": 0.0},
            {"title": "Rule B", "similarity": 0.0},
            {"title": "Rule C", "similarity": 0.0},
        ]
        assert _display_filter(candidates) == []

    def test_nonzero_similarity_included(self):
        """Candidates with any positive similarity score are kept."""
        candidates = [
            {"title": "High", "similarity": 0.75},
            {"title": "Low", "similarity": 0.05},
        ]
        result = _display_filter(candidates)
        assert len(result) == 2

    def test_mixed_zero_and_nonzero(self):
        """Only nonzero-similarity candidates appear in the display list."""
        candidates = [
            {"title": "Real", "similarity": 0.40},
            {"title": "Zero", "similarity": 0.0},
            {"title": "Also Real", "similarity": 0.12},
        ]
        result = _display_filter(candidates)
        assert len(result) == 2
        titles = {r["title"] for r in result}
        assert titles == {"Real", "Also Real"}

    def test_missing_similarity_field_treated_as_zero(self):
        """Match dicts with no similarity key default to 0.0 and are excluded."""
        candidates = [{"title": "No score field"}]
        assert _display_filter(candidates) == []

    def test_limit_respected(self):
        """Display list is capped at the specified limit."""
        candidates = [{"title": f"Rule {i}", "similarity": 0.5} for i in range(15)]
        result = _display_filter(candidates, limit=10)
        assert len(result) == 10

    def test_max_similarity_computed_before_filter(self):
        """max_similarity must be derived from ALL candidates (including zeros),
        not from the filtered display list -- regression guard for the
        intentional threshold=0.0 comment in agentic_workflow.py."""
        all_candidates = [
            {"similarity": 0.0},
            {"similarity": 0.0},
            {"similarity": 0.65},
        ]
        all_sims = [r.get("similarity", 0.0) for r in all_candidates]
        max_sim = max(all_sims) if all_sims else 0.0

        display = _display_filter(all_candidates)

        assert max_sim == 0.65
        assert len(display) == 1

    def test_ai_route_entry_suppressed_when_all_zero(self):
        """ai.py only appends to similar_rules_by_generated when the
        filtered list is non-empty.  All-zero candidates => nothing appended."""
        all_matches = [{"similarity": 0.0}, {"similarity": 0.0}]
        similar_matches = _display_filter(all_matches)
        similar_rules_by_generated: list = []

        if similar_matches:
            similar_rules_by_generated.append({"similar_existing_rules": similar_matches[:5]})

        assert similar_rules_by_generated == []

    def test_ai_route_entry_added_when_nonzero_match_exists(self):
        """ai.py appends an entry when at least one match has similarity > 0."""
        all_matches = [{"similarity": 0.0}, {"similarity": 0.35}]
        similar_matches = _display_filter(all_matches)
        similar_rules_by_generated: list = []

        if similar_matches:
            similar_rules_by_generated.append({"similar_existing_rules": similar_matches[:5]})

        assert len(similar_rules_by_generated) == 1
        assert len(similar_rules_by_generated[0]["similar_existing_rules"]) == 1
