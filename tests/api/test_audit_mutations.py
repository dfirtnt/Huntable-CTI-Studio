"""Mandatory-audit migration contract tests for high-risk route families (Chunk C Task 4).

These prove the enterprise contract per migrated handler:
- success path records exactly one AuditEventTable row with the right action, then commits;
- audit-write failure rolls the mutation back (no commit) and surfaces a 500.

Handlers are exercised directly with a mocked session (mirroring tests/api/test_settings_api.py),
so they assert the transaction contract without seeding the database.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.database.models import AuditEventTable
from src.services import audit_service

pytestmark = pytest.mark.api


def _fake_request():
    return SimpleNamespace(
        state=SimpleNamespace(
            request_id="test-request",
            identity=SimpleNamespace(
                actor_type="human",
                user_id="u1",
                email="reviewer@example.com",
                roles=("rule_reviewer",),
            ),
        ),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
    )


def _audit_rows(mock_session) -> list[AuditEventTable]:
    return [c.args[0] for c in mock_session.add.call_args_list if isinstance(c.args[0], AuditEventTable)]


def _session_with_rule(rule) -> MagicMock:
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = rule
    return session


def _chaining_session(all_rows=None, first_row=None) -> MagicMock:
    """Session whose query().filter()...filter().all()/.first() resolve regardless of filter depth."""
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = all_rows or []
    query.first.return_value = first_row
    session.query.return_value = query
    return session


class _AsyncCtx:
    """Minimal async context manager yielding a fixed session (for async route handlers)."""

    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _async_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# sigma_queue family
# ---------------------------------------------------------------------------


class TestSigmaQueueAudit:
    def test_approve_records_audit_and_commits(self):
        from src.web.routes.sigma_queue import QueueUpdateRequest, approve_queued_rule

        rule = MagicMock()
        rule.status = "pending"
        session = _session_with_rule(rule)

        with patch("src.web.routes.sigma_queue.DatabaseManager") as MockDM:
            MockDM.return_value.get_session.return_value = session
            result = approve_queued_rule(_fake_request(), 7, QueueUpdateRequest())

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SIGMA_QUEUE_RULE_APPROVED
        assert rows[0].actor_id == "u1"
        assert rows[0].target_id == "7"
        session.commit.assert_called_once()

    def test_approve_rolls_back_when_audit_fails(self):
        from src.web.routes.sigma_queue import QueueUpdateRequest, approve_queued_rule

        rule = MagicMock()
        rule.status = "pending"
        session = _session_with_rule(rule)

        with patch("src.web.routes.sigma_queue.DatabaseManager") as MockDM:
            MockDM.return_value.get_session.return_value = session
            with patch(
                "src.web.routes.sigma_queue.AuditService.record_mandatory",
                side_effect=RuntimeError("audit write failed"),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    approve_queued_rule(_fake_request(), 7, QueueUpdateRequest())

        assert exc_info.value.status_code == 500
        session.commit.assert_not_called()

    def test_reject_records_audit_and_commits(self):
        from src.web.routes.sigma_queue import reject_queued_rule

        rule = MagicMock()
        session = _session_with_rule(rule)

        # reject is async and reads request.json(); give it an awaitable returning {}
        async def _json():
            return {}

        request = _fake_request()
        request.json = _json
        request.query_params = {}

        import asyncio

        with patch("src.web.routes.sigma_queue.DatabaseManager") as MockDM:
            MockDM.return_value.get_session.return_value = session
            result = asyncio.run(reject_queued_rule(request, 9))

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SIGMA_QUEUE_RULE_REJECTED
        session.commit.assert_called_once()

    def test_delete_records_audit_and_commits(self):
        from src.web.routes.sigma_queue import delete_queued_rule

        rule = MagicMock()
        rule.status = "approved"
        session = _session_with_rule(rule)

        with patch("src.web.routes.sigma_queue.DatabaseManager") as MockDM:
            MockDM.return_value.get_session.return_value = session
            result = delete_queued_rule(_fake_request(), 3)

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SIGMA_QUEUE_RULE_DELETED
        session.delete.assert_called_once_with(rule)
        session.commit.assert_called_once()

    def test_yaml_update_records_audit_and_commits(self):
        from src.web.routes.sigma_queue import RuleYamlUpdateRequest, update_rule_yaml

        rule = MagicMock()
        rule.rule_yaml = "title: old"
        session = _session_with_rule(rule)

        with patch("src.web.routes.sigma_queue.DatabaseManager") as MockDM:
            MockDM.return_value.get_session.return_value = session
            result = update_rule_yaml(_fake_request(), 4, RuleYamlUpdateRequest(rule_yaml="title: new"))

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SIGMA_QUEUE_RULE_EDITED
        session.commit.assert_called_once()

    def test_bulk_records_single_audit_and_commits(self):
        from src.web.routes.sigma_queue import BulkActionRequest, bulk_action_queued_rules

        rule1, rule2 = MagicMock(), MagicMock()
        rule1.id, rule2.id = 1, 2
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [rule1, rule2]
        # _sigma_author_from_db uses .first()
        session.query.return_value.filter.return_value.first.return_value = MagicMock(value="Author")

        with patch("src.web.routes.sigma_queue.DatabaseManager") as MockDM:
            MockDM.return_value.get_session.return_value = session
            result = bulk_action_queued_rules(_fake_request(), BulkActionRequest(ids=[1, 2], action="approve"))

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SIGMA_QUEUE_BULK_ACTION
        assert rows[0].event_metadata["count"] == 2
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# workflow family
# ---------------------------------------------------------------------------


class TestWorkflowAudit:
    def test_cancel_records_audit_and_commits(self):
        import asyncio

        from src.web.routes.workflow_executions import cancel_workflow_execution

        execution = MagicMock()
        execution.id = 11
        execution.status = "running"
        session = _chaining_session(first_row=execution)

        with patch("src.web.routes.workflow_executions.get_db_manager") as mock_get:
            mock_get.return_value.get_session.return_value = session
            result = asyncio.run(cancel_workflow_execution(_fake_request(), 11))

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_WORKFLOW_CANCELLED
        assert rows[0].target_id == "11"
        session.commit.assert_called_once()

    def test_cancel_rolls_back_when_audit_fails(self):
        import asyncio

        from src.web.routes.workflow_executions import cancel_workflow_execution

        execution = MagicMock()
        execution.id = 11
        execution.status = "running"
        session = _chaining_session(first_row=execution)

        with patch("src.web.routes.workflow_executions.get_db_manager") as mock_get:
            mock_get.return_value.get_session.return_value = session
            with patch(
                "src.web.routes.workflow_executions.AuditService.record_mandatory",
                side_effect=RuntimeError("audit write failed"),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(cancel_workflow_execution(_fake_request(), 11))

        assert exc_info.value.status_code == 500
        session.commit.assert_not_called()

    def test_cancel_all_records_single_bulk_audit(self):
        import asyncio

        from src.web.routes.workflow_executions import cancel_all_running_executions

        e1, e2 = MagicMock(), MagicMock()
        e1.id, e2.id = 1, 2
        e1.status, e2.status = "running", "pending"
        session = _chaining_session(all_rows=[e1, e2])

        with patch("src.web.routes.workflow_executions.get_db_manager") as mock_get:
            mock_get.return_value.get_session.return_value = session
            result = asyncio.run(cancel_all_running_executions(_fake_request()))

        assert result["count"] == 2
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_WORKFLOW_CANCELLED
        assert rows[0].event_metadata["bulk"] is True
        session.commit.assert_called_once()

    def test_cleanup_stale_records_audit_and_commits(self):
        from src.web.routes.workflow_executions import cleanup_stale_executions

        e1 = MagicMock()
        e1.id = 5
        e1.status = "running"
        e1.error_message = None
        session = _chaining_session(all_rows=[e1])

        with patch("src.web.routes.workflow_executions.get_db_manager") as mock_get:
            mock_get.return_value.get_session.return_value = session
            result = cleanup_stale_executions(_fake_request(), max_age_hours=1.0)

        assert result["count"] == 1
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_WORKFLOW_STALE_CLEANUP_REQUESTED
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# sources family
# ---------------------------------------------------------------------------


class TestSourcesAudit:
    def test_toggle_records_audit_and_commits(self):
        import asyncio

        from src.web.routes.sources import api_toggle_source_status

        session = _async_session()
        with patch("src.web.routes.sources.async_db_manager") as mgr:
            mgr.get_session.return_value = _AsyncCtx(session)
            mgr.toggle_source_status = AsyncMock(
                return_value={
                    "source_id": 1,
                    "source_name": "X",
                    "old_status": False,
                    "new_status": True,
                    "success": True,
                }
            )
            result = asyncio.run(api_toggle_source_status(_fake_request(), 1))

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SOURCE_TOGGLED
        assert rows[0].target_id == "1"
        session.commit.assert_awaited_once()

    def test_toggle_rolls_back_when_audit_fails(self):
        import asyncio

        from src.web.routes.sources import api_toggle_source_status

        session = _async_session()
        with patch("src.web.routes.sources.async_db_manager") as mgr:
            mgr.get_session.return_value = _AsyncCtx(session)
            mgr.toggle_source_status = AsyncMock(
                return_value={
                    "source_id": 1,
                    "source_name": "X",
                    "old_status": False,
                    "new_status": True,
                    "success": True,
                }
            )
            with patch(
                "src.web.routes.sources.AsyncAuditService.record_mandatory",
                AsyncMock(side_effect=RuntimeError("audit write failed")),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    asyncio.run(api_toggle_source_status(_fake_request(), 1))

        assert exc_info.value.status_code == 500
        session.commit.assert_not_awaited()

    def test_check_frequency_records_audit_and_commits(self):
        import asyncio

        from src.web.routes.sources import api_update_source_check_frequency

        session = _async_session()
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute = AsyncMock(return_value=exec_result)
        with patch("src.web.routes.sources.async_db_manager") as mgr:
            mgr.get_session.return_value = _AsyncCtx(session)
            result = asyncio.run(api_update_source_check_frequency(_fake_request(), 2, {"check_frequency": 300}))

        assert result["success"] is True
        rows = _audit_rows(session)
        assert len(rows) == 1
        assert rows[0].action == audit_service.ACTION_SOURCE_UPDATED
        session.commit.assert_awaited_once()

    def test_image_ocr_protected_source_is_not_audited(self):
        import asyncio

        from src.web.routes.sources import api_update_source_image_ocr

        session = _async_session()
        with patch("src.web.routes.sources.async_db_manager") as mgr:
            mgr.get_session.return_value = _AsyncCtx(session)
            mgr.update_source_image_ocr_override = AsyncMock(
                return_value={"success": False, "protected": True, "message": "nope"}
            )
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(api_update_source_image_ocr(_fake_request(), 3, {"image_ocr_enabled": True}))

        assert exc_info.value.status_code == 400
        assert _audit_rows(session) == []
        session.commit.assert_not_awaited()

    def test_collect_records_best_effort_audit(self):
        import asyncio

        from src.web.routes import sources as sources_routes

        session = _async_session()
        fake_task = SimpleNamespace(id="task-123")
        fake_celery = MagicMock()
        fake_celery.send_task.return_value = fake_task

        with patch("src.web.routes.sources.async_db_manager") as mgr:
            mgr.get_session.return_value = _AsyncCtx(session)
            with patch.object(sources_routes, "Celery", return_value=fake_celery):
                recorded = {}

                async def _capture(sess, event):
                    recorded["event"] = event

                with patch.object(
                    sources_routes.AsyncAuditService, "record_best_effort", AsyncMock(side_effect=_capture)
                ):
                    result = asyncio.run(sources_routes.api_collect_from_source(_fake_request(), 4))

        assert result["task_id"] == "task-123"
        assert recorded["event"].action == audit_service.ACTION_SOURCE_COLLECTION_REQUESTED
        assert recorded["event"].target_id == "4"
