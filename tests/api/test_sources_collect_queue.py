"""API tests for Collect Now priority queue routing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.audit_service import ACTION_SOURCE_COLLECTION_REQUESTED

pytestmark = pytest.mark.api


def _fake_request():
    return SimpleNamespace(
        state=SimpleNamespace(
            request_id="test-request",
            identity=SimpleNamespace(
                actor_type="human",
                user_id="u1",
                email="operator@example.com",
                roles=("operator",),
                auth_mode="trusted_header",
            ),
        ),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
    )


class TestCollectNowUsesImmediateQueue:
    """Verify api_collect_from_source sends to collection_immediate queue."""

    @pytest.mark.asyncio
    async def test_collect_sends_to_collection_immediate_queue(self):
        """User-initiated Collect Now must route to collection_immediate, not collection."""
        from src.web.routes.sources import api_collect_from_source

        mock_task = MagicMock()
        mock_task.id = "fake-task-id"

        mock_celery = MagicMock()
        mock_celery.send_task.return_value = mock_task

        with (
            patch("src.web.routes.sources.Celery", return_value=mock_celery),
            patch("src.web.routes.sources.async_db_manager"),
            patch(
                "src.web.routes.sources.AsyncAuditService.record_best_effort",
                new_callable=AsyncMock,
            ) as mock_audit,
        ):
            result = await api_collect_from_source(_fake_request(), source_id=1)

        mock_celery.send_task.assert_called_once_with(
            "src.worker.celery_app.collect_from_source",
            args=[1],
            queue="collection_immediate",
        )
        assert result["success"] is True
        assert result["task_id"] == "fake-task-id"
        assert mock_audit.await_count == 1
        assert mock_audit.await_args.args[1].action == ACTION_SOURCE_COLLECTION_REQUESTED
