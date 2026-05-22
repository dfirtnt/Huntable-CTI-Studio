"""
API tests for POST /api/articles/{article_id}/detect-os.

Covers the junk-filter gate introduced to prevent sending non-huntable
content to LLMs.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.web.routes.ai import api_detect_os

pytestmark = pytest.mark.api

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_article(**kwargs):
    defaults = dict(
        id=42,
        content="PowerShell execution via rundll32.dll spawned from winword.exe",
        article_metadata={"threat_hunting_score": 80},
        source_id=1,
        canonical_url="https://example.com/article",
        title="Test Article",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_request(body: dict | None = None) -> Request:
    """Build a minimal Starlette Request whose .json() returns *body*."""
    payload = json.dumps(body or {}).encode()
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [(b"content-type", b"application/json")],
    }
    req = Request(scope)
    req._body = payload
    return req


def _make_filter_result(*, is_huntable: bool, confidence: float = 0.9, filtered_content: str = "filtered"):
    r = Mock()
    r.is_huntable = is_huntable
    r.confidence = confidence
    r.filtered_content = filtered_content if is_huntable else ""
    r.removed_chunks = [] if is_huntable else [{"text": "junk"}]
    r.chunks_removed = 0 if is_huntable else 1
    r.chunks_kept = 1 if is_huntable else 0
    return r


def _base_patches(filter_result, article=None):
    """Return the standard set of patches needed by most tests.

    DatabaseManager / WorkflowTriggerService / ContentFilter / OSDetectionService
    are imported *inside* the function body, so we patch their source modules.
    """
    if article is None:
        article = _make_article()

    mock_session = Mock()
    mock_session.close = Mock()

    mock_config = Mock()
    mock_config.agent_models = {}
    mock_config.junk_filter_threshold = 0.8

    mock_trigger_service = Mock()
    mock_trigger_service.get_active_config.return_value = mock_config

    mock_db_manager = Mock()
    mock_db_manager.get_session.return_value = mock_session

    return {
        "src.web.routes.ai.async_db_manager.get_article": AsyncMock(return_value=article),
        "src.database.manager.DatabaseManager": Mock(return_value=mock_db_manager),
        "src.services.workflow_trigger_service.WorkflowTriggerService": Mock(return_value=mock_trigger_service),
        "src.utils.content_filter.ContentFilter": Mock(
            return_value=Mock(filter_content=Mock(return_value=filter_result))
        ),
    }


# ---------------------------------------------------------------------------
# Junk filter gate — 422 path
# ---------------------------------------------------------------------------


class TestDetectOsJunkFilterGate:
    """Verify the junk filter blocks the LLM when no huntable content found."""

    @pytest.mark.asyncio
    async def test_returns_422_when_no_huntable_content(self):
        """422 is raised when filter marks article as not huntable."""
        filter_result = _make_filter_result(is_huntable=False, confidence=0.1)
        patches = _base_patches(filter_result)

        with (
            patch(
                "src.web.routes.ai.async_db_manager.get_article",
                patches["src.web.routes.ai.async_db_manager.get_article"],
            ),
            patch("src.database.manager.DatabaseManager", patches["src.database.manager.DatabaseManager"]),
            patch(
                "src.services.workflow_trigger_service.WorkflowTriggerService",
                patches["src.services.workflow_trigger_service.WorkflowTriggerService"],
            ),
            patch("src.utils.content_filter.ContentFilter", patches["src.utils.content_filter.ContentFilter"]),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await api_detect_os(42, _make_request({"use_junk_filter": True, "junk_filter_threshold": 0.8}))

        exc = exc_info.value
        assert exc.status_code == 422
        assert exc.detail["error"] == "no_huntable_content"
        assert exc.detail["threshold"] == 0.8
        assert exc.detail["confidence"] == pytest.approx(0.1)
        assert "message" in exc.detail

    @pytest.mark.asyncio
    async def test_422_detail_contains_message_string(self):
        """detail.message must be a string so the frontend can display it."""
        filter_result = _make_filter_result(is_huntable=False, confidence=0.05)
        patches = _base_patches(filter_result)

        with (
            patch(
                "src.web.routes.ai.async_db_manager.get_article",
                patches["src.web.routes.ai.async_db_manager.get_article"],
            ),
            patch("src.database.manager.DatabaseManager", patches["src.database.manager.DatabaseManager"]),
            patch(
                "src.services.workflow_trigger_service.WorkflowTriggerService",
                patches["src.services.workflow_trigger_service.WorkflowTriggerService"],
            ),
            patch("src.utils.content_filter.ContentFilter", patches["src.utils.content_filter.ContentFilter"]),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await api_detect_os(42, _make_request({"use_junk_filter": True}))

        assert isinstance(exc_info.value.detail["message"], str)
        assert len(exc_info.value.detail["message"]) > 0

    @pytest.mark.asyncio
    async def test_os_detection_not_called_when_junk(self):
        """OSDetectionService must not be instantiated when content is junk."""
        filter_result = _make_filter_result(is_huntable=False, confidence=0.2)
        patches = _base_patches(filter_result)
        mock_os_service_cls = Mock()

        with (
            patch(
                "src.web.routes.ai.async_db_manager.get_article",
                patches["src.web.routes.ai.async_db_manager.get_article"],
            ),
            patch("src.database.manager.DatabaseManager", patches["src.database.manager.DatabaseManager"]),
            patch(
                "src.services.workflow_trigger_service.WorkflowTriggerService",
                patches["src.services.workflow_trigger_service.WorkflowTriggerService"],
            ),
            patch("src.utils.content_filter.ContentFilter", patches["src.utils.content_filter.ContentFilter"]),
            patch("src.services.os_detection_service.OSDetectionService", mock_os_service_cls),
        ):
            with pytest.raises(HTTPException):
                await api_detect_os(42, _make_request({"use_junk_filter": True}))

        mock_os_service_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_junk_filter_bypassed_when_disabled(self):
        """When use_junk_filter=False, ContentFilter is not called."""
        filter_result = _make_filter_result(is_huntable=True)
        patches = _base_patches(filter_result)
        mock_content_filter_cls = Mock()  # separate instance to verify not called

        mock_os_service = Mock()
        mock_os_service.detect_os = AsyncMock(
            return_value={
                "operating_system": "Windows",
                "method": "embedding",
                "confidence": "high",
                "similarities": {},
                "max_similarity": 0.9,
            }
        )

        with (
            patch(
                "src.web.routes.ai.async_db_manager.get_article",
                patches["src.web.routes.ai.async_db_manager.get_article"],
            ),
            patch("src.database.manager.DatabaseManager", patches["src.database.manager.DatabaseManager"]),
            patch(
                "src.services.workflow_trigger_service.WorkflowTriggerService",
                patches["src.services.workflow_trigger_service.WorkflowTriggerService"],
            ),
            patch("src.utils.content_filter.ContentFilter", mock_content_filter_cls),
            patch("src.services.os_detection_service.OSDetectionService", Mock(return_value=mock_os_service)),
        ):
            # Should not raise — OS detection proceeds with raw content
            await api_detect_os(42, _make_request({"use_junk_filter": False}))

        mock_content_filter_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_threshold_passed_to_filter(self):
        """The junk_filter_threshold from the request body is forwarded to ContentFilter."""
        filter_result = _make_filter_result(is_huntable=False, confidence=0.3)
        mock_content_filter_instance = Mock()
        mock_content_filter_instance.filter_content.return_value = filter_result
        mock_content_filter_cls = Mock(return_value=mock_content_filter_instance)
        patches = _base_patches(filter_result)

        with (
            patch(
                "src.web.routes.ai.async_db_manager.get_article",
                patches["src.web.routes.ai.async_db_manager.get_article"],
            ),
            patch("src.database.manager.DatabaseManager", patches["src.database.manager.DatabaseManager"]),
            patch(
                "src.services.workflow_trigger_service.WorkflowTriggerService",
                patches["src.services.workflow_trigger_service.WorkflowTriggerService"],
            ),
            patch("src.utils.content_filter.ContentFilter", mock_content_filter_cls),
        ):
            with pytest.raises(HTTPException):
                await api_detect_os(42, _make_request({"use_junk_filter": True, "junk_filter_threshold": 0.65}))

        call_kwargs = mock_content_filter_instance.filter_content.call_args
        assert call_kwargs.kwargs.get("min_confidence") == pytest.approx(0.65)

    @pytest.mark.asyncio
    async def test_404_when_article_not_found(self):
        """Returns 404 when the article doesn't exist."""
        with patch("src.web.routes.ai.async_db_manager.get_article", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await api_detect_os(999, _make_request())

        assert exc_info.value.status_code == 404
