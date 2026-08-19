"""Regression coverage for the Evals2 pending-record backfill route."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from src.web.routes import evaluation_api

pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_backfill_does_not_import_worker_only_workflow_module():
    """The web image has no LangGraph, so the real shared service must complete the row."""
    pending_record = SimpleNamespace(
        id=7,
        workflow_execution_id=42,
        subagent_name="cmdline",
        expected_count=1,
        expected_items=["whoami /groups"],
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
    execution = SimpleNamespace(
        id=42,
        status="completed",
        config_snapshot={"subagent_eval": "cmdline"},
        extraction_result={
            "subresults": {
                "cmdline": {
                    "items": [{"value": "whoami /groups"}],
                    "count": 1,
                }
            }
        },
    )

    pending_query = MagicMock()
    pending_query.filter.return_value.all.return_value = [pending_record]
    execution_query = MagicMock()
    execution_query.filter.return_value.first.return_value = execution
    eval_record_query = MagicMock()
    eval_record_query.filter.return_value.first.return_value = pending_record

    session = MagicMock()
    session.query.side_effect = [pending_query, execution_query, eval_record_query]

    with (
        patch.dict(sys.modules, {"src.workflows.agentic_workflow": None}),
        patch.object(evaluation_api, "DatabaseManager") as database_manager,
        patch.object(evaluation_api, "_audit_eval"),
    ):
        database_manager.return_value.get_session.return_value = session
        result = await evaluation_api.backfill_eval_records(
            request=MagicMock(spec=Request),
            subagent="cmdline",
        )

    assert result["success"] is True
    assert result["updated_count"] == 1
    assert result["failed_count"] == 0
    assert pending_record.status == "completed"
    assert pending_record.actual_count == 1
    assert pending_record.score == 0
    assert pending_record.matched_count == 1
    assert pending_record.missed_count == 0
    assert pending_record.extra_count == 0
    assert pending_record.completed_at is not None
    assert session.commit.call_count == 2
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_backfill_with_no_pending_records_returns_success():
    """An empty pending set is a successful no-op, not a 500."""
    pending_query = MagicMock()
    pending_query.filter.return_value.all.return_value = []
    session = MagicMock()
    session.query.return_value = pending_query

    with (
        patch.dict(sys.modules, {"src.workflows.agentic_workflow": None}),
        patch.object(evaluation_api, "DatabaseManager") as database_manager,
        patch.object(evaluation_api, "_audit_eval"),
    ):
        database_manager.return_value.get_session.return_value = session
        result = await evaluation_api.backfill_eval_records(
            request=MagicMock(spec=Request),
            subagent="cmdline",
        )

    assert result == {
        "success": True,
        "updated_count": 0,
        "failed_count": 0,
        "subagent": "cmdline",
        "message": "Updated 0 record(s), 0 marked as failed",
    }
    session.close.assert_called_once()
