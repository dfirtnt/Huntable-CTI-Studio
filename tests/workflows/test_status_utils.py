"""Characterization tests for workflow status utility helpers."""

from unittest.mock import Mock

import pytest

from src.workflows.status_utils import (
    extract_termination_info,
    mark_execution_completed,
)

pytestmark = pytest.mark.unit


def test_mark_execution_completed_sets_status_and_merges_termination_payload():
    execution = Mock()
    execution.status = "running"
    execution.current_step = "extract"
    execution.completed_at = None
    execution.error_message = "old"
    execution.error_log = {"qa_results": {"CmdLineQA": {"verdict": "pass"}}}

    db_session = Mock()
    mark_execution_completed(
        execution=execution,
        step="rank_article",
        db_session=db_session,
        reason="rank_below_threshold",
        details={"score": 12.5, "threshold": 20.0},
        commit=True,
    )

    assert execution.status == "completed"
    assert execution.current_step == "rank_article"
    assert execution.error_message is None
    assert isinstance(execution.completed_at, object)
    assert "qa_results" in execution.error_log
    assert execution.error_log["termination"]["reason"] == "rank_below_threshold"
    assert execution.error_log["termination"]["step"] == "rank_article"
    assert execution.error_log["termination"]["details"]["threshold"] == 20.0
    db_session.commit.assert_called_once()


def test_mark_execution_completed_handles_invalid_existing_error_log():
    execution = Mock()
    execution.error_log = "not-a-dict"

    mark_execution_completed(
        execution=execution,
        step="done",
        reason="no_sigma_rules_generated",
        details=None,
    )

    assert isinstance(execution.error_log, dict)
    assert execution.error_log["termination"]["reason"] == "no_sigma_rules_generated"


def test_extract_termination_info_handles_missing_or_invalid_payload():
    assert extract_termination_info(None) == (None, None)
    assert extract_termination_info({"termination": "invalid"}) == (None, None)

    reason, payload = extract_termination_info(
        {"termination": {"reason": "non_windows_os_detected", "step": "os_detection"}}
    )
    assert reason == "non_windows_os_detected"
    assert payload["step"] == "os_detection"
