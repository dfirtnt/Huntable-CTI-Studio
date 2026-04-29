"""Tests for POST /api/vision/extract.

Guards the server-side Vision LLM proxy endpoint that was added to eliminate
API key storage in the browser extension popup. All cloud API calls are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from src.web.routes.scrape import _call_anthropic_vision, api_vision_extract

pytestmark = pytest.mark.api


def _db_with_key(key_value: str | None) -> MagicMock:
    """DatabaseManager mock whose session returns an AppSettings row (or None)."""
    row = MagicMock(value=key_value) if key_value else None
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = row
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=None)
    db = MagicMock()
    db.get_session.return_value = session
    return db


# ---------------------------------------------------------------------------
# Input validation -- caught before DB or provider is touched
# ---------------------------------------------------------------------------


async def test_vision_extract_missing_image_data_url_returns_400():
    """Absent imageDataUrl must return 400 immediately."""
    with pytest.raises(HTTPException) as exc_info:
        await api_vision_extract({"provider": "openai"})
    assert exc_info.value.status_code == 400
    assert "imageDataUrl" in exc_info.value.detail


async def test_vision_extract_empty_image_data_url_returns_400():
    """Empty-string imageDataUrl must also return 400."""
    with pytest.raises(HTTPException) as exc_info:
        await api_vision_extract({"imageDataUrl": "", "provider": "openai"})
    assert exc_info.value.status_code == 400


async def test_vision_extract_unknown_provider_returns_400():
    """Provider not in (openai, anthropic) must return 400 with the bad provider name."""
    with pytest.raises(HTTPException) as exc_info:
        await api_vision_extract({"imageDataUrl": "data:image/png;base64,abc", "provider": "gemini"})
    assert exc_info.value.status_code == 400
    assert "gemini" in exc_info.value.detail


# ---------------------------------------------------------------------------
# API key resolution
# ---------------------------------------------------------------------------


async def test_vision_extract_no_api_key_returns_503():
    """When no key exists in DB and env vars are absent, must return 503."""
    fake_db = _db_with_key(None)
    with (
        patch("src.database.manager.DatabaseManager", return_value=fake_db),
        patch("os.getenv", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await api_vision_extract({"imageDataUrl": "data:image/png;base64,abc", "provider": "openai"})
    assert exc_info.value.status_code == 503
    assert "openai" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# OpenAI success path
# ---------------------------------------------------------------------------


async def test_vision_extract_openai_success_returns_text():
    """OpenAI provider: choices[0].message.content must be returned as {text: ...}."""
    fake_db = _db_with_key("sk-test-key")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "  Extracted image text  "}}]}

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_acm = MagicMock()
    mock_acm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_acm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("src.database.manager.DatabaseManager", return_value=fake_db),
        patch("src.web.routes.scrape.httpx.AsyncClient", return_value=mock_acm),
    ):
        result = await api_vision_extract(
            {
                "imageDataUrl": "data:image/png;base64,abc",
                "provider": "openai",
            }
        )

    assert result == {"text": "Extracted image text"}


# ---------------------------------------------------------------------------
# Anthropic data URL validation
# ---------------------------------------------------------------------------


async def test_anthropic_vision_rejects_plain_https_url():
    """_call_anthropic_vision must raise HTTPException(400) for non-data: URLs."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_anthropic_vision("https://example.com/img.png", "any-key")
    assert exc_info.value.status_code == 400
    assert "base64 data URL" in exc_info.value.detail


async def test_anthropic_vision_rejects_svg_data_url():
    """SVG URLs (data:image/svg+xml) don't match the accepted pattern and must return 400."""
    with pytest.raises(HTTPException) as exc_info:
        await _call_anthropic_vision("data:image/svg+xml;base64,PHN2Zy8+", "any-key")
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Upstream error handling
# ---------------------------------------------------------------------------


async def test_vision_extract_upstream_api_error_returns_502():
    """An HTTP error from the upstream provider must surface as 502, not 500."""
    fake_db = _db_with_key("sk-test-key")

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    upstream_resp = httpx.Response(401, request=request, content=b"Unauthorized")

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError("401", request=request, response=upstream_resp))
    mock_acm = MagicMock()
    mock_acm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_acm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("src.database.manager.DatabaseManager", return_value=fake_db),
        patch("src.web.routes.scrape.httpx.AsyncClient", return_value=mock_acm),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await api_vision_extract(
                {
                    "imageDataUrl": "data:image/png;base64,abc",
                    "provider": "openai",
                }
            )

    assert exc_info.value.status_code == 502
