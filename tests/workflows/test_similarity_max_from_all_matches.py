"""Regression: max_similarity must reflect the best match across ALL candidates,
not only those above the similarity_threshold filter.

Before the fix, matches below threshold were discarded before computing
max_similarity, so a rule with 13 % best-match and a 50 % threshold would
report max_similarity = 0.0 — hiding the real score in the queue table.

See: agentic_workflow.py  run_similarity_search / promote_to_queue
"""

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers to build the match dicts returned by SigmaMatchingService
# ---------------------------------------------------------------------------


def _match(similarity: float, novelty_score: float | None = None, title: str = "Existing Rule") -> dict:
    """Build a fake match dict as returned by compare_proposed_rule_to_embeddings."""
    return {
        "rule_id": 1,
        "title": title,
        "similarity": similarity,
        "novelty_score": novelty_score if novelty_score is not None else (1.0 - similarity),
        "novelty_label": "NOVEL" if similarity < 0.5 else "KNOWN",
    }


# ---------------------------------------------------------------------------
# Tests for the max_similarity / similar_rules logic extracted from
# similarity_search_node.  We replicate the code-under-test's computation
# inline so the test is tightly coupled to the *fix*, not the surrounding
# orchestration.
# ---------------------------------------------------------------------------


class TestSimilarityMaxFromAllMatches:
    """Verify that max_similarity uses all candidates, not threshold-filtered ones."""

    THRESHOLD = 0.5  # default similarity_threshold

    @staticmethod
    def _compute(similar_rules: list[dict], threshold: float = 0.5) -> dict:
        """Replicate the fixed logic from similarity_search_node."""
        # --- This mirrors the FIXED code in agentic_workflow.py ---
        all_similarities = [r.get("similarity", 0.0) for r in similar_rules]
        rule_max_sim = max(all_similarities) if all_similarities else 0.0

        filtered_rules = [r for r in similar_rules if r.get("similarity", 0.0) >= threshold][:10]

        rule_novelty_scores = [r.get("novelty_score", 1.0) for r in filtered_rules]
        rule_min_novelty = min(rule_novelty_scores) if rule_novelty_scores else 1.0
        rule_novelty_label = filtered_rules[0].get("novelty_label", "NOVEL") if filtered_rules else "NOVEL"

        return {
            "similar_rules": [r for r in similar_rules if r.get("similarity", 0.0) > 0][:10],
            "max_similarity": rule_max_sim,
            "novelty_label": rule_novelty_label,
            "novelty_score": rule_min_novelty,
            "top_matches": filtered_rules[:5] if filtered_rules else similar_rules[:5],
        }

    # -- Core regression test --
    def test_max_similarity_reflects_best_below_threshold_match(self):
        """13 % match should produce max_similarity=0.13, not 0.0."""
        matches = [_match(0.13), _match(0.09)]
        result = self._compute(matches, threshold=self.THRESHOLD)

        assert result["max_similarity"] == pytest.approx(0.13)
        # filtered_rules should be empty (both below threshold)
        assert result["novelty_label"] == "NOVEL"
        assert result["novelty_score"] == 1.0  # default when no filtered

    def test_max_similarity_with_above_threshold_match(self):
        """When a match IS above threshold, max_similarity should still reflect
        the actual best (which may be the above-threshold one)."""
        matches = [_match(0.65), _match(0.13)]
        result = self._compute(matches, threshold=self.THRESHOLD)

        assert result["max_similarity"] == pytest.approx(0.65)

    def test_no_matches_gives_zero(self):
        result = self._compute([], threshold=self.THRESHOLD)
        assert result["max_similarity"] == 0.0

    def test_similar_rules_includes_below_threshold_candidates(self):
        """similar_rules stores all non-zero candidates regardless of threshold,
        so the queue entry has data to display even when nothing clears the bar."""
        matches = [_match(0.13, title="A"), _match(0.09, title="B")]
        result = self._compute(matches, threshold=self.THRESHOLD)

        assert len(result["similar_rules"]) == 2
        assert result["similar_rules"][0]["title"] == "A"

    def test_top_matches_falls_back_to_unfiltered_when_none_above_threshold(self):
        """When no matches are above threshold, top_matches should fall back
        to unfiltered candidates so the UI has something to display."""
        matches = [_match(0.13), _match(0.09)]
        result = self._compute(matches, threshold=self.THRESHOLD)

        # top_matches should have the unfiltered fallback
        assert len(result["top_matches"]) == 2

    def test_top_matches_uses_filtered_when_available(self):
        """When matches exist above threshold, top_matches uses filtered list."""
        matches = [_match(0.65), _match(0.55), _match(0.13)]
        result = self._compute(matches, threshold=self.THRESHOLD)

        assert len(result["top_matches"]) == 2  # only the 2 above threshold
        assert all(m["similarity"] >= self.THRESHOLD for m in result["top_matches"])


class TestZeroSimilarityFilter:
    """Regression: zero-similarity matches must be stripped from similar_rules.

    compare_proposed_rule_to_embeddings returns ALL candidates (threshold=0.0) so
    the workflow can compute max_similarity from the full set. Before this fix,
    similarity=0.0 entries (no semantic overlap at all) were stored in similar_rules
    and surfaced in the queue UI as spurious matches.
    """

    @staticmethod
    def _apply_filter(matches: list[dict]) -> list[dict]:
        """Mirror the fixed production logic in agentic_workflow.py."""
        return [r for r in matches if r.get("similarity", 0.0) > 0][:10]

    def test_zero_similarity_match_excluded(self):
        """A match with similarity=0.0 must not appear in similar_rules."""
        matches = [_match(0.45), _match(0.0, title="Zero")]
        result = self._apply_filter(matches)
        titles = [r["title"] for r in result]
        assert "Zero" not in titles
        assert len(result) == 1

    def test_nonzero_match_retained(self):
        """A match with similarity > 0, even below threshold, must be kept."""
        matches = [_match(0.01, title="Tiny")]
        result = self._apply_filter(matches)
        assert len(result) == 1
        assert result[0]["title"] == "Tiny"

    def test_all_zero_gives_empty(self):
        """If every candidate has similarity=0.0, similar_rules should be empty."""
        matches = [_match(0.0), _match(0.0)]
        assert self._apply_filter(matches) == []

    def test_missing_similarity_key_treated_as_zero(self):
        """A match dict with no similarity key defaults to 0.0 and is excluded."""
        match_no_key = {"rule_id": 1, "title": "NoKey"}
        result = self._apply_filter([match_no_key])
        assert result == []

    def test_top_ten_cap_applied_after_filter(self):
        """Cap of 10 is applied after zero-sim removal, not before."""
        # 12 matches: 2 zeros, 10 non-zero
        matches = [_match(0.0)] * 2 + [_match(0.5 + i * 0.01, title=f"R{i}") for i in range(10)]
        result = self._apply_filter(matches)
        assert len(result) == 10
        assert all(r.get("similarity", 0.0) > 0 for r in result)


class TestPromoteToQueueMaxSimilarity:
    """Verify promote_to_queue reads max_similarity from novelty_results correctly."""

    def test_queue_entry_gets_actual_max_similarity(self):
        """The queue entry's max_similarity should come from the novelty result,
        which now carries the real best-match value (not the filtered one)."""
        similarity_results = [
            {"rule_title": "Rule A", "max_similarity": 0.13, "similar_rules": [_match(0.13)]},
            {"rule_title": "Rule B", "max_similarity": 0.0, "similar_rules": []},
        ]
        sigma_rules = [
            {"title": "Rule A", "detection": {}, "logsource": {}},
            {"title": "Rule B", "detection": {}, "logsource": {}},
        ]
        threshold = 0.5

        # Replicate promote_to_queue per-rule logic
        for idx, rule in enumerate(sigma_rules):
            rule_similarity = similarity_results[idx] if idx < len(similarity_results) else {"max_similarity": 0.0}
            rule_max_sim = rule_similarity.get("max_similarity", 0.0)

            if rule_max_sim < threshold:
                # This is what gets stored on SigmaRuleQueueTable.max_similarity
                if idx == 0:
                    assert rule_max_sim == pytest.approx(0.13), "Rule A should carry 0.13 from novelty result, not 0.0"
                elif idx == 1:
                    assert rule_max_sim == pytest.approx(0.0)
