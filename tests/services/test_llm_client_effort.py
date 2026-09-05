"""Reasoning effort is sent under each provider's own field, only when the model lists it.

Also covers the capability-drift alarm: when config/model_capabilities.json claims a
model takes temperature and the provider rejects it, the retry logs a WARNING naming
the model so the stale value gets fixed.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.llm_service import LLMService

pytestmark = pytest.mark.unit


@pytest.fixture
def llm_service():
    with patch("src.services.llm_service.DatabaseManager") as mock_db:
        mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
        svc = LLMService(
            config_models={
                "RankAgent": "gpt-5.6-luna",
                "RankAgent_provider": "openai",
                "RankAgent_effort": "xhigh",
                "ExtractAgent": "gpt-4o-mini",
                "ExtractAgent_provider": "openai",
                "ExtractAgent_effort": "low",
                "CmdlineExtract_model": "claude-opus-5",
                "CmdlineExtract_provider": "anthropic",
                "CmdlineExtract_effort": " High ",
                "SigmaAgent": "gpt-5.6-luna",
                "SigmaAgent_provider": "openai",
            }
        )
        svc.openai_api_key = "test-key"
        svc.anthropic_api_key = "test-anthropic-key"
        svc.workflow_openai_enabled = True
        svc.workflow_anthropic_enabled = True
        return svc


def _ok_response(body: dict) -> Mock:
    resp = Mock()
    resp.status_code = 200
    resp.text = "ok"
    resp.json.return_value = body
    return resp


def _openai_client(responses):
    client = AsyncMock()
    client.post = AsyncMock(side_effect=responses)
    ctx = Mock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return client, ctx


class TestLLMServiceResolvesEffortFromConfig:
    def test_main_agents_read_their_own_key(self, llm_service):
        assert llm_service.effort_rank == "xhigh"
        assert llm_service.effort_sigma is None

    def test_extractor_falls_back_to_extract_agent(self, llm_service):
        assert llm_service.resolve_extract_effort("CmdlineExtract") == "high"
        assert llm_service.resolve_extract_effort("ProcTreeExtract") == "low"

    def test_blank_and_non_string_values_mean_provider_default(self):
        assert LLMService._config_effort("RankAgent", {"RankAgent_effort": ""}) is None
        assert LLMService._config_effort("RankAgent", {"RankAgent_effort": 3}) is None
        assert LLMService._config_effort("RankAgent", None) is None


class TestOpenAIEffort:
    @pytest.mark.asyncio
    async def test_reasoning_effort_sent_when_model_lists_the_tier(self, llm_service):
        client, ctx = _openai_client([_ok_response({"choices": [{"message": {"content": "x"}}]})])
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-5.6-luna",
                temperature=0.2,
                max_tokens=100,
                timeout=30.0,
                effort="xhigh",
            )
        payload = client.post.await_args.kwargs["json"]
        assert payload["reasoning_effort"] == "xhigh"
        assert "temperature" not in payload  # reasoning model: sampling omitted
        assert result["_provider_payload"] == payload

    @pytest.mark.asyncio
    async def test_effort_omitted_when_model_has_no_tiers(self, llm_service):
        client, ctx = _openai_client([_ok_response({"choices": [{"message": {"content": "x"}}]})])
        with patch("httpx.AsyncClient", return_value=ctx):
            await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-4o",
                temperature=0.2,
                max_tokens=100,
                timeout=30.0,
                effort="high",
            )
        payload = client.post.await_args.kwargs["json"]
        assert "reasoning_effort" not in payload
        assert payload["temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_unlisted_tier_is_not_sent(self, llm_service):
        client, ctx = _openai_client([_ok_response({"choices": [{"message": {"content": "x"}}]})])
        with patch("httpx.AsyncClient", return_value=ctx):
            await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-5.1",  # none/low/medium/high only
                temperature=0.0,
                max_tokens=100,
                timeout=30.0,
                effort="max",
            )
        assert "reasoning_effort" not in client.post.await_args.kwargs["json"]

    @pytest.mark.asyncio
    async def test_no_effort_means_no_key(self, llm_service):
        client, ctx = _openai_client([_ok_response({"choices": [{"message": {"content": "x"}}]})])
        with patch("httpx.AsyncClient", return_value=ctx):
            await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-5.6-luna",
                temperature=0.0,
                max_tokens=100,
                timeout=30.0,
            )
        assert "reasoning_effort" not in client.post.await_args.kwargs["json"]

    @pytest.mark.asyncio
    async def test_rejected_temperature_on_a_catalogued_model_logs_drift_warning(self, llm_service, caplog):
        rejected = Mock()
        rejected.status_code = 400
        rejected.text = (
            '{"error": {"code": "unsupported_value", "param": "temperature", '
            '"message": "Unsupported value: temperature does not support 0.2 with this model. '
            'Only the default (1) value is supported."}}'
        )
        client, ctx = _openai_client([rejected, _ok_response({"choices": [{"message": {"content": "x"}}]})])
        with (
            patch("httpx.AsyncClient", return_value=ctx),
            caplog.at_level(logging.WARNING, logger="src.services.llm_client"),
        ):
            result = await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-4o",  # catalog: supports_temperature=true
                temperature=0.2,
                max_tokens=100,
                timeout=30.0,
            )
        drift = [r.getMessage() for r in caplog.records if "CAPABILITY DRIFT" in r.getMessage()]
        assert drift and "gpt-4o" in drift[0] and "model_capabilities.json" in drift[0]
        assert "temperature" not in result["_provider_payload"]
        assert client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_rejected_temperature_on_an_unknown_model_does_not_claim_drift(self, llm_service, caplog):
        rejected = Mock()
        rejected.status_code = 400
        rejected.text = '{"error": {"code": "unsupported_value", "param": "temperature", "message": "temperature: Only the default (1) value is supported."}}'
        client, ctx = _openai_client([rejected, _ok_response({"choices": [{"message": {"content": "x"}}]})])
        with (
            patch("httpx.AsyncClient", return_value=ctx),
            caplog.at_level(logging.WARNING, logger="src.services.llm_client"),
        ):
            await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-4-unlisted-preview",  # fallback path, no catalog claim
                temperature=0.2,
                max_tokens=100,
                timeout=30.0,
            )
        assert not [r for r in caplog.records if "CAPABILITY DRIFT" in r.getMessage()]


class TestAnthropicEffort:
    async def _call(self, llm_service, model, effort=None, temperature=0.3):
        body = {"content": [{"type": "text", "text": "ok"}], "usage": {}, "stop_reason": "end_turn"}
        with patch.object(
            llm_service, "_call_anthropic_with_retry", new_callable=AsyncMock, return_value=_ok_response(body)
        ) as post:
            result = await llm_service._call_anthropic_chat(
                messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                model_name=model,
                temperature=temperature,
                max_tokens=100,
                timeout=30.0,
                effort=effort,
            )
        return post.await_args.kwargs["payload"], result

    @pytest.mark.asyncio
    async def test_output_config_effort_and_no_temperature_on_opus_5(self, llm_service):
        payload, result = await self._call(llm_service, "claude-opus-5", effort="xhigh")
        assert payload["output_config"] == {"effort": "xhigh"}
        assert "temperature" not in payload
        assert result["_provider_payload"] is payload

    @pytest.mark.asyncio
    async def test_sonnet_4_6_keeps_temperature_and_drops_unlisted_tier(self, llm_service):
        payload, _ = await self._call(llm_service, "claude-sonnet-4-6", effort="xhigh")
        assert payload["temperature"] == 0.3
        assert "output_config" not in payload

    @pytest.mark.asyncio
    async def test_sonnet_4_6_listed_tier_is_sent(self, llm_service):
        payload, _ = await self._call(llm_service, "claude-sonnet-4-6", effort="max")
        assert payload["output_config"] == {"effort": "max"}

    @pytest.mark.asyncio
    async def test_no_effort_means_no_output_config(self, llm_service):
        payload, _ = await self._call(llm_service, "claude-sonnet-4-5")
        assert "output_config" not in payload
        assert payload["temperature"] == 0.3


class TestCodexEffort:
    @pytest.mark.asyncio
    async def test_configured_tier_is_forwarded_to_the_adapter(self, llm_service):
        with patch("src.services.llm_client.CodexAppServerClient") as client_cls:
            client_cls.return_value.complete = AsyncMock(return_value={"choices": []})
            await llm_service._call_codex_chat(
                messages=[{"role": "user", "content": "hi"}],
                model_name="gpt-5.6-luna",
                max_tokens=100,
                timeout=30.0,
                effort="ultra",
            )
        assert client_cls.return_value.complete.await_args.kwargs["effort"] == "ultra"


class TestRequestChatThreadsEffort:
    @pytest.mark.asyncio
    async def test_effort_is_normalized_and_passed_through(self, llm_service):
        with patch.object(llm_service, "_call_openai_chat", new_callable=AsyncMock, return_value={}) as call:
            await llm_service.request_chat(
                provider="openai",
                model_name="gpt-5.6-luna",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                temperature=0.0,
                timeout=10.0,
                failure_context="t",
                effort=" High ",
            )
        assert call.await_args.kwargs["effort"] == "high"

    @pytest.mark.asyncio
    async def test_blank_effort_becomes_none(self, llm_service):
        with patch.object(llm_service, "_call_openai_chat", new_callable=AsyncMock, return_value={}) as call:
            await llm_service.request_chat(
                provider="openai",
                model_name="gpt-5.6-luna",
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                temperature=0.0,
                timeout=10.0,
                failure_context="t",
                effort="",
            )
        assert call.await_args.kwargs["effort"] is None
