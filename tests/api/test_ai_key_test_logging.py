"""
Regression tests guarding the secret-logging fix in src/web/routes/ai.py.

Prior to the fix, api_test_openai_key / api_test_hf_key / api_generate_sigma
logged partial API key/token material (first 8 + last 4 chars, e.g.
"starts_with=sk-abcd12..., ends_with=...wxyz"). These tests assert the safe,
presence/length-only log format is used and that the submitted secret never
appears in any log record emitted by these routes.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.web.routes.ai import api_generate_sigma, api_test_hf_key, api_test_openai_key

pytestmark = pytest.mark.api


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


def _mock_async_client(*, method: str, status_code: int, json_body: dict | None = None, text: str = ""):
    """Build a mock httpx.AsyncClient class whose *method* call returns a canned response."""
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.json = Mock(return_value=json_body or {})
    mock_response.text = text

    mock_client = AsyncMock()
    setattr(mock_client, method, AsyncMock(return_value=mock_response))
    mock_client.aclose = AsyncMock()

    mock_client_class = Mock()
    mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_client_class


def _assert_secret_not_logged(caplog, secret: str):
    for record in caplog.records:
        message = record.getMessage()
        assert secret not in message, f"raw secret leaked in log: {message!r}"
        assert secret[:8] not in message, f"secret prefix leaked in log: {message!r}"
        assert secret[-4:] not in message, f"secret suffix leaked in log: {message!r}"


class TestOpenAiKeyTestLogging:
    """POST /api/test-openai-key must never log key material."""

    @pytest.mark.asyncio
    async def test_no_key_material_logged_on_invalid_key(self, caplog):
        fake_key = "sk-" + "a" * 30
        mock_client_class = _mock_async_client(
            method="post",
            status_code=401,
            json_body={"error": {"message": "Invalid API key"}},
        )

        with patch("httpx.AsyncClient", mock_client_class), caplog.at_level("INFO"):
            result = await api_test_openai_key(_make_request({"api_key": fake_key}))

        assert result["valid"] is False
        _assert_secret_not_logged(caplog, fake_key)
        assert any(
            "Testing OpenAI API key: present=yes, source=request, length=" in r.getMessage() for r in caplog.records
        ), "expected safe presence/length-only log line, not found"


class TestHuggingFaceKeyTestLogging:
    """POST /api/test-hf-key must never log token material."""

    @pytest.mark.asyncio
    async def test_no_token_material_logged_on_rejected_token(self, caplog):
        fake_token = "hf_" + "b" * 30

        mock_client_class = _mock_async_client(method="get", status_code=401)

        with (
            patch("httpx.AsyncClient", mock_client_class),
            caplog.at_level("INFO"),
            pytest.raises(HTTPException) as exc_info,
        ):
            await api_test_hf_key(_make_request({"api_key": fake_token}))

        assert exc_info.value.status_code == 401
        _assert_secret_not_logged(caplog, fake_token)
        assert any("Testing Hugging Face token: present=yes, length=" in r.getMessage() for r in caplog.records), (
            "expected safe presence/length-only log line, not found"
        )


class TestGenerateSigmaKeyLogging:
    """POST /api/articles/{id}/generate-sigma must never log key material."""

    @pytest.mark.asyncio
    async def test_no_key_material_logged_when_cached(self, caplog):
        fake_key = "sk-" + "c" * 30
        article = SimpleNamespace(
            id=42,
            content="some article content",
            article_metadata={"sigma_rules": {"rules": [{"title": "cached rule"}], "metadata": {}}},
            source_id=1,
        )

        with (
            patch("src.web.routes.ai.async_db_manager.get_article", AsyncMock(return_value=article)),
            caplog.at_level("INFO"),
        ):
            result = await api_generate_sigma(
                42,
                _make_request({"ai_model": "chatgpt", "api_key": fake_key, "skip_matching": True}),
            )

        # Cached-rules short-circuit: confirms the log line ran before any generation work.
        assert result["cached"] is True
        _assert_secret_not_logged(caplog, fake_key)
        assert any(
            "SIGMA generation requested with ai_model='chatgpt', api_key present: True" in r.getMessage()
            for r in caplog.records
        ), "expected safe presence-only log line, not found"


@pytest.mark.api
class TestStoredKeyFallback:
    """An empty api_key means "test whatever is already configured".

    Settings stopped returning credential values to the browser, so the page can
    no longer resend the key it is asking about. These routes resolve it instead.
    Before this, an empty field produced "API key is required" -- which read as
    "you have not configured a key" even when one was configured.
    """

    STORED = "sk-storedKeyResolvedServerSide0123456789"

    @pytest.mark.asyncio
    async def test_openai_falls_back_to_the_stored_key(self, caplog):
        client_class = _mock_async_client(method="post", status_code=200, json_body={"choices": []})

        with patch("src.web.routes.ai.resolve_provider_api_key", AsyncMock(return_value=self.STORED)):
            with patch("httpx.AsyncClient", client_class):
                result = await api_test_openai_key(_make_request({}))

        assert result["valid"] is True
        # Same guarantee the rest of this module enforces, on the new path.
        _assert_secret_not_logged(caplog, self.STORED)

    @pytest.mark.asyncio
    async def test_openai_prefers_an_explicitly_submitted_key(self):
        """A freshly typed key must win over whatever is stored."""
        typed = "sk-typedByTheOperatorRightNow0123456789"
        client_class = _mock_async_client(method="post", status_code=200, json_body={"choices": []})
        resolver = AsyncMock(return_value=self.STORED)

        with patch("src.web.routes.ai.resolve_provider_api_key", resolver):
            with patch("httpx.AsyncClient", client_class):
                await api_test_openai_key(_make_request({"api_key": typed}))

        resolver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_openai_reports_nothing_configured_rather_than_key_required(self):
        with patch("src.web.routes.ai.resolve_provider_api_key", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await api_test_openai_key(_make_request({}))

        assert exc_info.value.status_code == 400
        assert "none is configured" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_anthropic_falls_back_to_the_stored_key(self):
        from src.web.routes.ai import api_test_anthropic_key

        client_class = _mock_async_client(method="post", status_code=200, json_body={"content": []})

        with patch("src.web.routes.ai.resolve_provider_api_key", AsyncMock(return_value="sk-ant-stored")):
            with patch("httpx.AsyncClient", client_class):
                result = await api_test_anthropic_key(_make_request({}))

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_anthropic_reports_nothing_configured(self):
        from src.web.routes.ai import api_test_anthropic_key

        with patch("src.web.routes.ai.resolve_provider_api_key", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await api_test_anthropic_key(_make_request({}))

        assert exc_info.value.status_code == 400
        assert "none is configured" in exc_info.value.detail.lower()
