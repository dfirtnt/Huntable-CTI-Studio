"""Regression: subagent eval scoring must hydrate externalized config snapshots.

Since snapshot deduplication (commit 6e851943), a completed eval execution stores
``config_snapshot = {"snapshot_id": N}`` and keeps the real payload -- including
``subagent_eval`` -- in the externalized snapshot record. The completion scorer
must hydrate that reference; reading ``execution.config_snapshot`` raw sees no
``subagent_eval`` and returns early, leaving the evaluation row stuck ``pending``
(the v6887 cmdline symptom).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.services.subagent_eval_service import update_subagent_eval_on_completion

pytestmark = pytest.mark.unit


def _eval_record(expected_count: int = 1):
    return SimpleNamespace(
        id=101,
        subagent_name="cmdline",
        expected_count=expected_count,
        expected_items=None,
        acceptable_items=None,
        actual_count=None,
        actual_items=None,
        matched_count=None,
        missed_count=None,
        extra_count=None,
        neutral_count=None,
        score=None,
        status="pending",
        completed_at=None,
    )


def _session_returning(eval_record):
    session = Mock()
    session.query.return_value.filter.return_value.first.return_value = eval_record
    return session


def test_externalized_snapshot_scores_pending_record_to_completed():
    """A completed execution with an externalized snapshot scores its row."""
    eval_record = _eval_record(expected_count=1)
    execution = SimpleNamespace(
        id=3793,
        # Post-externalization: only the pointer lives on the column.
        config_snapshot={"snapshot_id": 55},
        snapshot_record=SimpleNamespace(payload={"subagent_eval": "cmdline"}),
        extraction_result={"subresults": {"cmdline": {"count": 3, "items": [1, 2, 3]}}},
    )
    session = _session_returning(eval_record)

    update_subagent_eval_on_completion(execution, session)

    assert eval_record.status == "completed"
    assert eval_record.actual_count == 3
    assert eval_record.score == 3 - 1
    assert eval_record.completed_at is not None
    session.commit.assert_called()


def test_pointer_only_snapshot_without_hydration_would_stay_pending():
    """Guard: the raw ``{"snapshot_id": N}`` alone carries no subagent_eval.

    If the scorer ever regresses to reading ``config_snapshot`` raw (no
    ``snapshot_record``), it finds no ``subagent_eval`` and must no-op -- the row
    stays pending rather than being mis-scored. Hydration is what rescues it.
    """
    eval_record = _eval_record()
    execution = SimpleNamespace(
        id=3794,
        config_snapshot={"snapshot_id": 56},
        snapshot_record=None,  # nothing to hydrate -> legacy fallback is pointer-only
        extraction_result={"subresults": {"cmdline": {"count": 3, "items": [1, 2, 3]}}},
    )
    session = _session_returning(eval_record)

    update_subagent_eval_on_completion(execution, session)

    assert eval_record.status == "pending"
    session.commit.assert_not_called()
