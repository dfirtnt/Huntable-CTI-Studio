"""Mandatory-audit migration contract tests for high-risk route families (Chunk C Task 4).

These prove the enterprise contract per migrated handler:
- success path records exactly one AuditEventTable row with the right action, then commits;
- audit-write failure rolls the mutation back (no commit) and surfaces a 500.

Handlers are exercised directly with a mocked session (mirroring tests/api/test_settings_api.py),
so they assert the transaction contract without seeding the database.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
