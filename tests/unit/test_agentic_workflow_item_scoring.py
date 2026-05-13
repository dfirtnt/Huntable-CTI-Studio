"""Regression tests for item-level scoring wire-up in agentic_workflow.

Covers the bug where _update_single_eval_record would skip the scorer entirely
when the model returned zero items (because _extract_actual_items returns None
to signal 'no items field present', conflating it with 'agent emitted nothing').
The fix coerces actual_items=None to [] before scoring so zero-extraction runs
still get matched/missed/extra populated.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.workflows.agentic_workflow import _update_single_eval_record


def _make_eval_record(expected_items: list[str], subagent_name: str = "cmdline"):
    """Build a stand-in for SubagentEvaluationTable that we can assert against."""
    rec = SimpleNamespace()
    rec.id = 1234
    rec.subagent_name = subagent_name
    rec.expected_count = len(expected_items)
    rec.expected_items = expected_items
    rec.actual_count = None
    rec.actual_items = None
    rec.matched_count = None
    rec.missed_count = None
    rec.extra_count = None
    rec.score = None
    rec.status = "pending"
    rec.completed_at = None
    return rec


def _make_execution(extraction_result: dict):
    return SimpleNamespace(id=42, extraction_result=extraction_result)


@pytest.mark.unit
def test_zero_items_extracted_still_populates_item_metrics():
    """REGRESSION: when expected_items is set and the model returns 0 items,
    the eval record should still have matched_count=0, missed_count=N, extra_count=0
    rather than leaving them as None (which renders as 'count only' on the UI)."""
    expected = ["nltest /dclist:", "whoami /groups", "net group \"domain admins\" /domain"]
    eval_record = _make_eval_record(expected)
    # Simulate "agent ran, returned zero items": subresults has the agent key but
    # no items (or items is empty). _extract_actual_count returns 0 either way.
    extraction_result = {"subresults": {"cmdline": {"items": [], "count": 0}}}
    execution = _make_execution(extraction_result)
    db_session = MagicMock()

    _update_single_eval_record(eval_record, execution, db_session)

    assert eval_record.actual_count == 0
    assert eval_record.status == "completed"
    # The bug we're regressing against: these were None before the fix.
    assert eval_record.matched_count == 0
    assert eval_record.missed_count == len(expected)
    assert eval_record.extra_count == 0
    assert eval_record.actual_items == []
    db_session.commit.assert_called()


@pytest.mark.unit
def test_partial_match_populates_item_metrics():
    """Sanity check the happy path: model emits some items, scorer runs end-to-end."""
    expected = ["whoami /groups", "ipconfig /all", "net user"]
    eval_record = _make_eval_record(expected)
    extraction_result = {
        "subresults": {
            "cmdline": {
                "items": [
                    {"value": "whoami /groups"},  # match
                    {"value": "tasklist /svc"},  # extra
                ],
                "count": 2,
            }
        }
    }
    execution = _make_execution(extraction_result)
    db_session = MagicMock()

    _update_single_eval_record(eval_record, execution, db_session)

    assert eval_record.actual_count == 2
    assert eval_record.matched_count == 1
    assert eval_record.missed_count == 2  # ipconfig /all + net user
    assert eval_record.extra_count == 1  # tasklist /svc


@pytest.mark.unit
def test_no_expected_items_skips_item_scoring():
    """When the article has no ground truth, item-level fields stay None
    (count-only mode -- this is the documented fallback)."""
    eval_record = _make_eval_record([])  # empty expected_items
    eval_record.expected_items = None  # mimic missing ground truth
    eval_record.expected_count = 5
    extraction_result = {
        "subresults": {"cmdline": {"items": [{"value": "whoami /groups"}], "count": 1}}
    }
    execution = _make_execution(extraction_result)
    db_session = MagicMock()

    _update_single_eval_record(eval_record, execution, db_session)

    assert eval_record.actual_count == 1
    assert eval_record.matched_count is None
    assert eval_record.missed_count is None
    assert eval_record.extra_count is None
    assert eval_record.actual_items is None
