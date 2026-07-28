"""Status-aware audit emission for privileged backup and model routes.

Backup restore and model rollback drive non-transactional side effects (a
pg_restore subprocess, an is_current flip plus a background re-scoring thread).
Before this coverage they left no durable record of *who* invoked them, so a
successful privileged mutation was unattributable.

These are unit tests that call the route coroutines directly rather than going
through the API client: the assertion here is about which audit events the route
emits, and driving the function directly keeps that independent of whether the
api-marked suite is pointed at an ASGI transport or a live server.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.audit_service import (
    ACTION_BACKUP_RESTORED,
    ACTION_MODEL_ROLLED_BACK,
    STATUS_ATTEMPTED,
    STATUS_FAILURE,
    STATUS_SUCCESS,
    AsyncAuditService,
    AuditEvent,
)
from src.web.routes import backup as backup_routes
from src.web.routes import models as model_routes

pytestmark = pytest.mark.unit


def _fake_request(payload: dict | None = None):
    """Minimal Request stand-in carrying an authenticated admin identity."""
    identity = SimpleNamespace(
        actor_type="user",
        user_id="u-42",
        email="admin@example.com",
        roles=("admin",),
    )
    request = SimpleNamespace(
        state=SimpleNamespace(identity=identity, request_id="req-abc"),
        client=SimpleNamespace(host="10.0.0.9"),
        headers={"user-agent": "pytest"},
    )
    request.json = AsyncMock(return_value=payload or {})
    return request


class _AuditSpy:
    """Collect the AuditEvent objects a route emits."""

    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(event)
        return True

    def by_status(self, status):
        return [e for e in self.events if e.status == status]


# ---------------------------------------------------------------------------
# Backup restore
# ---------------------------------------------------------------------------


class TestBackupRestoreAudit:
    @pytest.mark.asyncio
    async def test_successful_restore_emits_attempt_then_success(self):
        spy = _AuditSpy()
        request = _fake_request({"backup_name": "backup_20260101_120000", "no_snapshot": True})

        with (
            patch.object(backup_routes.AsyncAuditService, "record_out_of_band", spy),
            patch.object(
                backup_routes.subprocess,
                "run",
                return_value=Mock(returncode=0, stdout="restore ok", stderr=""),
            ),
        ):
            result = await backup_routes.api_restore_backup(request)

        assert result["success"] is True

        assert [e.status for e in spy.events] == [STATUS_ATTEMPTED, STATUS_SUCCESS], (
            "restore must record the attempt before the subprocess and the outcome after it"
        )
        assert {e.action for e in spy.events} == {ACTION_BACKUP_RESTORED}

        terminal = spy.by_status(STATUS_SUCCESS)[0]
        assert terminal.target_type == "backup"
        assert terminal.target_id == "backup_20260101_120000"
        # Actor attribution is the whole point of the task.
        assert terminal.actor.actor_id == "u-42"
        assert terminal.actor.actor_email == "admin@example.com"
        assert terminal.actor.request_id == "req-abc"
        assert terminal.actor.source_ip == "10.0.0.9"

    @pytest.mark.asyncio
    async def test_failed_restore_emits_failure_event(self):
        spy = _AuditSpy()
        request = _fake_request({"backup_name": "backup_20260101_120000"})

        with (
            patch.object(backup_routes.AsyncAuditService, "record_out_of_band", spy),
            patch.object(
                backup_routes.subprocess,
                "run",
                return_value=Mock(returncode=1, stdout="", stderr="boom"),
            ),
            pytest.raises(backup_routes.HTTPException),
        ):
            await backup_routes.api_restore_backup(request)

        assert [e.status for e in spy.events] == [STATUS_ATTEMPTED, STATUS_FAILURE]
        assert spy.by_status(STATUS_FAILURE)[0].metadata["returncode"] == 1

    @pytest.mark.asyncio
    async def test_timed_out_restore_still_records_a_terminal_event(self):
        """A restore killed by timeout is exactly the case that must not vanish."""
        spy = _AuditSpy()
        request = _fake_request({"backup_name": "backup_20260101_120000"})

        with (
            patch.object(backup_routes.AsyncAuditService, "record_out_of_band", spy),
            patch.object(
                backup_routes.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd="restore", timeout=600),
            ),
            pytest.raises(backup_routes.HTTPException),
        ):
            await backup_routes.api_restore_backup(request)

        assert [e.status for e in spy.events] == [STATUS_ATTEMPTED, STATUS_FAILURE]
        assert spy.by_status(STATUS_FAILURE)[0].metadata["timeout_seconds"] == 600


# ---------------------------------------------------------------------------
# Model rollback
# ---------------------------------------------------------------------------


def _version_row(version_id=3, version_number=3, is_current=False, path="/app/models/content_filter_v3.pkl"):
    version = Mock()
    version.id = version_id
    version.version_number = version_number
    version.is_current = is_current
    version.model_file_path = path
    return version


class TestModelRollbackAudit:
    @pytest.mark.asyncio
    async def test_successful_rollback_emits_attempt_then_success(self):
        spy = _AuditSpy()
        request = _fake_request()
        version = _version_row()

        manager = AsyncMock()
        manager.get_version_by_id.return_value = version
        manager.activate_version.return_value = True

        with (
            patch.object(model_routes.AsyncAuditService, "record_out_of_band", spy),
            patch("src.utils.model_versioning.MLModelVersionManager", return_value=manager),
            patch("os.path.exists", return_value=True),
            patch("threading.Thread") as thread,
        ):
            thread.return_value.start = Mock()
            result = await model_routes.api_model_rollback(request, version_id=3)

        assert result["success"] is True

        assert [e.status for e in spy.events] == [STATUS_ATTEMPTED, STATUS_SUCCESS]
        assert {e.action for e in spy.events} == {ACTION_MODEL_ROLLED_BACK}

        terminal = spy.by_status(STATUS_SUCCESS)[0]
        assert terminal.target_type == "ml_model"
        assert terminal.target_id == "3"
        assert terminal.metadata["version_number"] == 3
        assert terminal.actor.actor_id == "u-42"
        assert terminal.actor.actor_roles == ("admin",)

    @pytest.mark.asyncio
    async def test_rollback_activation_failure_emits_failure_event(self):
        spy = _AuditSpy()
        request = _fake_request()
        version = _version_row()

        manager = AsyncMock()
        manager.get_version_by_id.return_value = version
        manager.activate_version.side_effect = FileNotFoundError("artifact gone")

        with (
            patch.object(model_routes.AsyncAuditService, "record_out_of_band", spy),
            patch("src.utils.model_versioning.MLModelVersionManager", return_value=manager),
            patch("os.path.exists", return_value=True),
            pytest.raises(model_routes.HTTPException),
        ):
            await model_routes.api_model_rollback(request, version_id=3)

        assert [e.status for e in spy.events] == [STATUS_ATTEMPTED, STATUS_FAILURE]
        assert "artifact gone" in spy.by_status(STATUS_FAILURE)[0].metadata["error"]

    @pytest.mark.asyncio
    async def test_rollback_rejected_before_side_effect_emits_nothing(self):
        """A 404 on an unknown version never touched the live model -- no event."""
        spy = _AuditSpy()
        request = _fake_request()

        manager = AsyncMock()
        manager.get_version_by_id.return_value = None

        with (
            patch.object(model_routes.AsyncAuditService, "record_out_of_band", spy),
            patch("src.utils.model_versioning.MLModelVersionManager", return_value=manager),
            pytest.raises(model_routes.HTTPException),
        ):
            await model_routes.api_model_rollback(request, version_id=9999)

        assert spy.events == []


# ---------------------------------------------------------------------------
# record_out_of_band durability guarantees
# ---------------------------------------------------------------------------


class TestRecordOutOfBand:
    """The sink must never take down the operation it is auditing."""

    def _event(self):
        return AuditEvent(
            action=ACTION_BACKUP_RESTORED,
            target_type="backup",
            target_id="backup_20260101_120000",
            status=STATUS_SUCCESS,
            summary="probe",
            actor=None,
        )

    @pytest.mark.asyncio
    async def test_db_error_is_swallowed_and_reported_as_false(self):
        """A failed audit write must not turn a completed restore into a 500."""
        manager = Mock()
        manager.get_session.side_effect = RuntimeError("connection refused")

        with patch("src.database.async_manager.async_db_manager", manager):
            assert await AsyncAuditService.record_out_of_band(self._event()) is False

    @pytest.mark.asyncio
    async def test_stalled_write_times_out_instead_of_hanging(self):
        """A stalled database must cost an audit row, not a hung request."""
        import asyncio

        class _StalledSession:
            async def __aenter__(self):
                await asyncio.sleep(30)

            async def __aexit__(self, *exc):
                return False

        manager = Mock()
        manager.get_session.return_value = _StalledSession()

        with patch("src.database.async_manager.async_db_manager", manager):
            result = await asyncio.wait_for(
                AsyncAuditService.record_out_of_band(self._event(), timeout=0.05),
                timeout=5,
            )

        assert result is False
