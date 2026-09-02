"""RED: queue promotion must be a per-rule decision, never a batch-wide one.

``queue_sigma_rules`` computed a batch aggregate
(``max_similarity = max(per-rule scores)``) and, when that aggregate cleared the
threshold, discarded the WHOLE batch before the per-rule loop ever ran:

    if max_similarity >= similarity_threshold:
        queued_rules = []          # every rule dropped, including novel ones

So a single near-duplicate suppressed its novel batch siblings. The rules were
lost silently -- nothing in the queue or the UI recorded why.

``select_queueable_rule_indices`` is the single source of truth for the
decision: each rule is judged on its own score only.

Inconclusive comparisons (``max_similarity=None`` + ``comparator_inconclusive``)
are promoted and routed to needs_review -- fail open, matching the pre-existing
per-rule guard.
"""

import pytest

from src.workflows.agentic_workflow import select_queueable_rule_indices

pytestmark = pytest.mark.unit


def test_near_duplicate_does_not_suppress_novel_batch_siblings():
    """A 0.9 rule must not drop the 0.1 rule generated alongside it."""
    results = [
        {"max_similarity": 0.9, "comparator_inconclusive": False},
        {"max_similarity": 0.1, "comparator_inconclusive": False},
    ]

    assert select_queueable_rule_indices(results, 0.5) == [1]


def test_all_novel_rules_are_queued():
    results = [
        {"max_similarity": 0.0, "comparator_inconclusive": False},
        {"max_similarity": 0.2, "comparator_inconclusive": False},
    ]

    assert select_queueable_rule_indices(results, 0.5) == [0, 1]


def test_all_duplicate_rules_are_suppressed():
    results = [
        {"max_similarity": 0.8, "comparator_inconclusive": False},
        {"max_similarity": 0.95, "comparator_inconclusive": False},
    ]

    assert select_queueable_rule_indices(results, 0.5) == []


def test_score_equal_to_threshold_is_suppressed():
    """The boundary is inclusive: >= threshold is a near-duplicate."""
    results = [{"max_similarity": 0.5, "comparator_inconclusive": False}]

    assert select_queueable_rule_indices(results, 0.5) == []


def test_inconclusive_rule_is_queued_regardless_of_batch():
    """Fail open: an unassessable rule is promoted for human review."""
    results = [
        {"max_similarity": 0.99, "comparator_inconclusive": False},
        {"max_similarity": None, "comparator_inconclusive": True},
    ]

    assert select_queueable_rule_indices(results, 0.5) == [1]


def test_unscored_but_not_inconclusive_rule_is_suppressed():
    """max_similarity=None without the inconclusive flag stays suppressed."""
    results = [{"max_similarity": None, "comparator_inconclusive": False}]

    assert select_queueable_rule_indices(results, 0.5) == []


def test_empty_results_queue_nothing():
    assert select_queueable_rule_indices([], 0.5) == []
