"""Tests for shared LLM provider HTTP clients."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.services.llm_provider_clients import (
    LMStudioChatClient,
    LMStudioChatError,
    parse_retry_after,
    post_anthropic_with_retry,
)


class TestParseRetryAfter:
    def test_parse_retry_after_seconds(self):
        assert parse_retry_after("2.5") == 2.5

    def test_parse_retry_after_http_date(self):
        retry_date = datetime.now(UTC) + timedelta(seconds=30)

        parsed = parse_retry_after(format_datetime(retry_date))

        assert 0 <= parsed <= 31

    def test_parse_retry_after_invalid_defaults_to_30(self):
        assert parse_retry_after("not-a-date") == 30.0


class TestAnthropicRetryClient:
    @pytest.mark.asyncio
    async def test_non_retryable_4xx_fails_fast(self):
        resp = Mock(status_code=401, text="unauthorized", headers={})
        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=resp)

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return mock_client

            async def __aexit__(self, exc_type, exc, tb):
                return None

        from src.services import llm_provider_clients

        original = llm_provider_clients.httpx.AsyncClient
        llm_provider_clients.httpx.AsyncClient = FakeAsyncClient
        try:
            with pytest.raises(RuntimeError, match=r"Anthropic API error \(401\)"):
                await post_anthropic_with_retry(
                    api_key="test-key",
                    payload={"model": "claude-sonnet-4-5"},
                    anthropic_api_url="https://api.anthropic.com/v1/messages",
                    base_delay=0.001,
                )
        finally:
            llm_provider_clients.httpx.AsyncClient = original

        assert mock_client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_transient_transport_error_retries(self):
        ok = Mock(status_code=200, text="ok", headers={})
        calls = [httpx.ConnectError("connection reset"), ok]
        mock_client = Mock()

        async def post(*args, **kwargs):
            result = calls.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        mock_client.post = post

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return mock_client

            async def __aexit__(self, exc_type, exc, tb):
                return None

        from src.services import llm_provider_clients

        original = llm_provider_clients.httpx.AsyncClient
        llm_provider_clients.httpx.AsyncClient = FakeAsyncClient
        try:
            result = await post_anthropic_with_retry(
                api_key="test-key",
                payload={"model": "claude-sonnet-4-5"},
                anthropic_api_url="https://api.anthropic.com/v1/messages",
                base_delay=0.001,
            )
        finally:
            llm_provider_clients.httpx.AsyncClient = original

        assert result is ok
        assert calls == []


class TestLMStudioChatClient:
    @pytest.mark.asyncio
    async def test_falls_back_to_next_url_and_stamps_provider_metadata(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}], "model": "loaded-model"}
        calls: list[str] = []

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def post(self, url, **kwargs):
                calls.append(url)
                if len(calls) == 1:
                    raise httpx.ConnectError("refused")
                return response

            async def aclose(self):
                return None

        from src.services import llm_provider_clients

        original = llm_provider_clients.httpx.AsyncClient
        llm_provider_clients.httpx.AsyncClient = FakeAsyncClient
        try:
            result = await LMStudioChatClient(url_candidates=["http://bad.local/v1", "http://good.local/v1"]).post_chat(
                {"model": "qwen/qwen3-8b", "messages": [{"role": "user", "content": "ping"}]},
                model_name="qwen/qwen3-8b",
                timeout=5.0,
                failure_context="test",
            )
        finally:
            llm_provider_clients.httpx.AsyncClient = original

        assert calls == ["http://bad.local/v1/chat/completions", "http://good.local/v1/chat/completions"]
        assert result["_provider_url"] == "http://good.local/v1/chat/completions"
        assert result["_provider_payload"]["model"] == "qwen/qwen3-8b"

    @pytest.mark.asyncio
    async def test_malformed_success_response_raises_client_error(self):
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("not json")

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def post(self, url, **kwargs):
                return response

            async def aclose(self):
                return None

        from src.services import llm_provider_clients

        original = llm_provider_clients.httpx.AsyncClient
        llm_provider_clients.httpx.AsyncClient = FakeAsyncClient
        try:
            with pytest.raises(LMStudioChatError, match="Failed to parse LMStudio response") as exc_info:
                await LMStudioChatClient(url_candidates=["http://bad-json.local/v1"]).post_chat(
                    {"model": "qwen/qwen3-8b", "messages": [{"role": "user", "content": "ping"}]},
                    model_name="qwen/qwen3-8b",
                    timeout=5.0,
                    failure_context="test",
                )
        finally:
            llm_provider_clients.httpx.AsyncClient = original

        assert exc_info.value.status_code == 500
