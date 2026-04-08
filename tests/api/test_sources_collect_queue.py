"""API tests for Collect Now priority queue routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.api


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

        with patch("src.web.routes.sources.Celery", return_value=mock_celery):
            result = await api_collect_from_source(source_id=1)

        mock_celery.send_task.assert_called_once_with(
            "src.worker.celery_app.collect_from_source",
            args=[1],
            queue="collection_immediate",
        )
        assert result["success"] is True
        assert result["task_id"] == "fake-task-id"
