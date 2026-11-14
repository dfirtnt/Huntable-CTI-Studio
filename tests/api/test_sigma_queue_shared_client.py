"""Sigma queue routes call providers through the shared LLM client (LLMService.request_chat).

Regressions covered:
- B1: Anthropic models with supports_temperature=false (config/model_capabilities.json)
  always returned 400 because the route sent temperature unconditionally; it also
  ignored ANTHROPIC_API_URL and read only the first content block.
- B4: workflow-SigmaAgent validation dropped SigmaAgent effort/temperature/top_p and
  used env LMSTUDIO_MODEL instead of LLMService's LMSTUDIO_MODEL_SIGMA -> AppSettings
  LMSTUDIO_MODEL chain for a blank lmstudio model.
- A request-header key overrides the stored key on the shared client, so it is the
  key actually sent to the provider.

No test reaches a provider: every transport (httpx, Anthropic retry helper, LMStudio
client, Codex app-server client) is replaced.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.services.llm_client import ProviderUnavailableError
from src.services.llm_service import LLMService
from src.web.routes.sigma_queue import (
    EnrichRuleRequest,
    SigmaAgentLLM,
    _call_traced_sigma_provider,
    _get_sigma_agent_llm_from_workflow,
    _sigma_llm_service,
    enrich_rule,
    validate_rule,
)

pytestmark = pytest.mark.api

_ENV = (
    "WORKFLOW_OPENAI_ENABLED",
    "WORKFLOW_ANTHROPIC_ENABLED",
    "WORKFLOW_LMSTUDIO_ENABLED",
    "WORKFLOW_CODEX_ENABLED",
    "WORKFLOW_OPENAI_API_KEY",
    "OPENAI_API_KEY",
    "WORKFLOW_ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_URL",
    "WORKFLOW_OPENAI_MODEL",
    "WORKFLOW_ANTHROPIC_MODEL",
    "WORKFLOW_CODEX_MODEL",
    "LMSTUDIO_MODEL",
    "LMSTUDIO_MODEL_SIGMA",
    "LMSTUDIO_TEMPERATURE",
    "LMSTUDIO_TOP_P",
)

_ENRICHED_YAML = "title: Shared client rule\ndetection:\n  selection:\n    Image: x\n  condition: selection"


@pytest.fixture(autouse=True)
def _isolated_provider_config(monkeypatch):
    """No provider config from the environment or the live test DB."""
    for key in _ENV:
        monkeypatch.delenv(key, raising=False)
    with (
        patch.object(LLMService, "_load_workflow_provider_settings", return_value={}),
        patch.object(LLMService, "_load_lmstudio_settings", return_value={}),
    ):
        yield


def _request(headers=None, body=None):
    request = MagicMock(spec=Request)
    request.headers = headers or {}
    request.json = AsyncMock(return_value=body or {})
    return request


def _patched_db():
    db_patch = patch("src.web.routes.sigma_queue.DatabaseManager")
    mock_db = db_patch.start()
    session = MagicMock()
    mock_db.return_value.get_session.return_value = session
    rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test Rule", rule_origin="generated", attribution=None)
    article = MagicMock(id=1, content="body", title="Article", canonical_url="", article_metadata=None)
    session.query.return_value.filter.return_value.first.side_effect = [rule, article, None, None]
    return db_patch


def _anthropic_response(*texts):
    response = MagicMock()
    response.json.return_value = {
        "content": [{"type": "text", "text": t} for t in texts],
        "usage": {"input_tokens": 5, "output_tokens": 7},
        "model": "claude-opus-4-7",
        "stop_reason": "end_turn",
    }
    return response


async def _traced(provider, model, service, **overrides):
    kwargs = {
        "agent_name": "sigma_enrichment",
        "provider": provider,
        "model": model,
        "llm_service": service,
        "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "enrich"}],
        "queue_id": 1,
        "article_id": None,
        "attempt": 1,
        "max_tokens": 4000,
        "temperature": 0.2,
        "timeout": 120.0,
        "failure_context": "test",
    }
    kwargs.update(overrides)
    return await _call_traced_sigma_provider(**kwargs)


# --------------------------------------------------------------------------- B1


class TestAnthropicGoesThroughTheSharedClient:
    @pytest.mark.asyncio
    async def test_no_temperature_for_a_model_that_rejects_it(self):
        service = await _sigma_llm_service("anthropic", "sk-ant-header")
        with patch.object(
            LLMService, "_call_anthropic_with_retry", AsyncMock(return_value=_anthropic_response("ok"))
        ) as post:
            await _traced("anthropic", "claude-opus-4-7", service)

        payload = post.await_args.kwargs["payload"]
        assert payload["model"] == "claude-opus-4-7"
        assert "temperature" not in payload, "claude-opus-4-7 has supports_temperature=false"
        assert payload["system"] == "sys"
        assert payload["messages"] == [{"role": "user", "content": "enrich"}]

    @pytest.mark.asyncio
    async def test_temperature_still_sent_where_supported(self):
        service = await _sigma_llm_service("anthropic", "sk-ant-header")
        with patch.object(
            LLMService, "_call_anthropic_with_retry", AsyncMock(return_value=_anthropic_response("ok"))
        ) as post:
            await _traced("anthropic", "claude-sonnet-4-5", service)

        assert post.await_args.kwargs["payload"]["temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_all_text_blocks_and_the_configured_url_are_used(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_URL", "https://anthropic.proxy.test/v1/messages")
        service = await _sigma_llm_service("anthropic", "sk-ant-header")
        with patch.object(
            LLMService,
            "_call_anthropic_with_retry",
            AsyncMock(return_value=_anthropic_response("title: a\n", "level: low")),
        ) as post:
            text = await _traced("anthropic", "claude-sonnet-4-5", service)

        assert text == "title: a\nlevel: low"
        assert post.await_args.kwargs["anthropic_api_url"] == "https://anthropic.proxy.test/v1/messages"
        assert post.await_args.kwargs["api_key"] == "sk-ant-header"

    @pytest.mark.asyncio
    async def test_enrich_route_with_opus_omits_temperature_and_succeeds(self):
        db_patch = _patched_db()
        envelope = json.dumps({"status": "pass", "updated_sigma_yaml": _ENRICHED_YAML})
        try:
            with patch.object(
                LLMService, "_call_anthropic_with_retry", AsyncMock(return_value=_anthropic_response(envelope))
            ) as post:
                result = await enrich_rule(
                    _request({"X-Anthropic-API-Key": "sk-ant-header"}),
                    queue_id=1,
                    enrich_request=EnrichRuleRequest(provider="anthropic", model="claude-opus-4-7"),
                )
        finally:
            db_patch.stop()

        assert result["success"] is True
        assert "temperature" not in post.await_args.kwargs["payload"]
        assert post.await_args.kwargs["api_key"] == "sk-ant-header"


# ----------------------------------------------------------------- header keys


class _FakeOpenAIClient:
    """Stands in for httpx.AsyncClient inside the shared OpenAI client."""

    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeOpenAIClient.calls.append({"url": url, "headers": headers, "json": json})
        response = MagicMock(status_code=200, text="")
        content = '{"status": "pass", "updated_sigma_yaml": "title: T\\ndetection:\\n  s:\\n    a: b\\n  condition: s"}'
        response.json.return_value = {"choices": [{"message": {"content": content}}], "usage": {}, "model": "gpt"}
        return response


class TestHeaderKeyReachesTheSharedClient:
    @pytest.mark.asyncio
    async def test_enrich_sends_the_header_key_not_the_stored_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-stored")  # what LLMService would load on its own
        _FakeOpenAIClient.calls = []
        db_patch = _patched_db()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")),
                patch("src.services.llm_client.httpx.AsyncClient", _FakeOpenAIClient),
            ):
                result = await enrich_rule(
                    _request({"X-OpenAI-API-Key": "sk-from-header"}),
                    queue_id=1,
                    enrich_request=EnrichRuleRequest(provider="openai", model="gpt-4o-mini"),
                )
        finally:
            db_patch.stop()

        assert result["success"] is True
        assert len(_FakeOpenAIClient.calls) == 1
        assert _FakeOpenAIClient.calls[0]["headers"]["Authorization"] == "Bearer sk-from-header"

    @pytest.mark.asyncio
    async def test_stored_key_is_used_when_no_header_is_sent(self):
        _FakeOpenAIClient.calls = []
        db_patch = _patched_db()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")),
                patch("src.services.llm_client.httpx.AsyncClient", _FakeOpenAIClient),
            ):
                await enrich_rule(
                    _request(),
                    queue_id=1,
                    enrich_request=EnrichRuleRequest(provider="openai", model="gpt-4o-mini"),
                )
        finally:
            db_patch.stop()

        assert _FakeOpenAIClient.calls[0]["headers"]["Authorization"] == "Bearer sk-stored"

    @pytest.mark.asyncio
    async def test_override_does_not_re_enable_an_explicitly_disabled_provider(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_OPENAI_ENABLED", "false")
        service = await _sigma_llm_service("openai", "sk-from-header")

        assert service.openai_api_key == "sk-from-header"
        with pytest.raises(ProviderUnavailableError, match="disabled"):
            await service.request_chat(
                provider="openai",
                model_name="gpt-4o-mini",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10,
                temperature=0.2,
                timeout=5.0,
                failure_context="test",
            )

    @pytest.mark.asyncio
    async def test_override_enables_a_provider_whose_flag_is_unset(self):
        service = await _sigma_llm_service("anthropic", "sk-ant-header")

        assert service.anthropic_api_key == "sk-ant-header"
        assert service.workflow_anthropic_enabled is True


# --------------------------------------------------------------------------- B4


def _workflow_session(agent_models, settings_rows=()):
    config = MagicMock()
    config.agent_models = agent_models
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.first.return_value = config
    session.query.return_value.filter.return_value.all.return_value = list(settings_rows)
    return session


def _row(key, value):
    return type("Row", (), {"key": key, "value": value})()


class TestWorkflowSigmaAgentResolution:
    def test_sigma_agent_effort_temperature_and_top_p_are_carried(self):
        session = _workflow_session(
            {
                "SigmaAgent_provider": "openai",
                "SigmaAgent": "gpt-5.2",
                "SigmaAgent_effort": " High ",
                "SigmaAgent_temperature": "0.7",
                "SigmaAgent_top_p": "0.5",
            },
            [_row("WORKFLOW_OPENAI_API_KEY", "sk-stored")],
        )

        resolved = _get_sigma_agent_llm_from_workflow(session)

        assert resolved == SigmaAgentLLM("openai", "gpt-5.2", "sk-stored", 0.7, 0.5, "high")

    def test_unset_sampling_falls_back_like_llm_service(self):
        session = _workflow_session(
            {"SigmaAgent_provider": "openai", "SigmaAgent": "gpt-4o-mini"},
            [_row("WORKFLOW_OPENAI_API_KEY", "sk-stored"), _row("LMSTUDIO_TEMPERATURE", "0.3")],
        )

        resolved = _get_sigma_agent_llm_from_workflow(session)

        assert (resolved.temperature, resolved.top_p, resolved.effort) == (0.3, 0.9, None)

    def test_blank_lmstudio_model_uses_lmstudio_model_sigma_first(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_LMSTUDIO_ENABLED", "true")
        monkeypatch.setenv("LMSTUDIO_MODEL_SIGMA", "qwen/sigma-model")
        monkeypatch.setenv("LMSTUDIO_MODEL", "generic-model")
        session = _workflow_session({"SigmaAgent_provider": "lmstudio", "SigmaAgent": ""})

        assert _get_sigma_agent_llm_from_workflow(session).model == "qwen/sigma-model"

    def test_blank_lmstudio_model_prefers_appsettings_over_env(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_LMSTUDIO_ENABLED", "true")
        monkeypatch.setenv("LMSTUDIO_MODEL", "env-model")
        session = _workflow_session(
            {"SigmaAgent_provider": "lmstudio", "SigmaAgent": ""},
            [_row("LMSTUDIO_MODEL", "appsettings-model")],
        )

        assert _get_sigma_agent_llm_from_workflow(session).model == "appsettings-model"

    @pytest.mark.parametrize(
        "provider,env,expected",
        [
            ("openai", {"WORKFLOW_OPENAI_MODEL": "gpt-4.1-mini"}, "gpt-4.1-mini"),
            ("anthropic", {}, "claude-sonnet-4-5"),
            ("codex", {"WORKFLOW_CODEX_ENABLED": "true"}, "gpt-5.6-luna"),
        ],
    )
    def test_blank_cloud_model_uses_provider_defaults(self, monkeypatch, provider, env, expected):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        session = _workflow_session(
            {"SigmaAgent_provider": provider, "SigmaAgent": ""},
            [_row("WORKFLOW_OPENAI_API_KEY", "sk"), _row("WORKFLOW_ANTHROPIC_API_KEY", "sk-ant")],
        )

        assert _get_sigma_agent_llm_from_workflow(session).model == expected

    def test_explicitly_disabled_cloud_provider_is_refused(self):
        session = _workflow_session(
            {"SigmaAgent_provider": "anthropic", "SigmaAgent": "claude-sonnet-4-5"},
            [_row("WORKFLOW_ANTHROPIC_API_KEY", "sk-ant"), _row("WORKFLOW_ANTHROPIC_ENABLED", "false")],
        )

        with pytest.raises(HTTPException) as exc_info:
            _get_sigma_agent_llm_from_workflow(session)
        assert "WORKFLOW_ANTHROPIC_ENABLED" in exc_info.value.detail


class TestValidatePassesSigmaAgentSettings:
    @pytest.mark.asyncio
    async def test_workflow_validate_sends_sigma_agent_effort_and_sampling(self):
        db_patch = _patched_db()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue._get_sigma_agent_llm_from_workflow",
                    return_value=SigmaAgentLLM("openai", "gpt-5.2", "sk-stored", 0.7, 0.5, "high"),
                ),
                patch.object(
                    LLMService, "request_chat", AsyncMock(side_effect=RuntimeError("stop after capture"))
                ) as chat,
            ):
                await validate_rule(_request(body={"use_workflow_sigma_agent": True}), queue_id=1)
        finally:
            db_patch.stop()

        kwargs = chat.await_args.kwargs
        assert kwargs["provider"] == "openai"
        assert kwargs["model_name"] == "gpt-5.2"
        assert (kwargs["effort"], kwargs["temperature"], kwargs["top_p"]) == ("high", 0.7, 0.5)

    @pytest.mark.asyncio
    async def test_workflow_codex_effort_reaches_the_codex_client(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_CODEX_ENABLED", "true")
        codex_client = MagicMock()
        codex_client.complete = AsyncMock(side_effect=RuntimeError("stop after capture"))
        db_patch = _patched_db()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue._get_sigma_agent_llm_from_workflow",
                    return_value=SigmaAgentLLM("codex", "gpt-5.6-sol", None, 0.0, 0.9, "high"),
                ),
                patch("src.services.llm_client.CodexAppServerClient", return_value=codex_client),
            ):
                await validate_rule(_request(body={"use_workflow_sigma_agent": True}), queue_id=1)
        finally:
            db_patch.stop()

        assert codex_client.complete.await_args.kwargs["effort"] == "high"
        assert codex_client.complete.await_args.kwargs["model_name"] == "gpt-5.6-sol"

    @pytest.mark.asyncio
    async def test_manual_validate_uses_provider_default_effort(self):
        db_patch = _patched_db()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")),
                patch.object(
                    LLMService, "request_chat", AsyncMock(side_effect=RuntimeError("stop after capture"))
                ) as chat,
            ):
                await validate_rule(_request(body={"provider": "openai", "model": "gpt-5.2"}), queue_id=1)
        finally:
            db_patch.stop()

        kwargs = chat.await_args.kwargs
        assert (kwargs["effort"], kwargs["temperature"], kwargs["top_p"]) == (None, 0.2, None)

    @pytest.mark.asyncio
    async def test_enrich_uses_provider_default_effort(self):
        db_patch = _patched_db()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")),
                patch.object(
                    LLMService, "request_chat", AsyncMock(side_effect=RuntimeError("stop after capture"))
                ) as chat,
            ):
                with pytest.raises(HTTPException):
                    await enrich_rule(
                        _request(), queue_id=1, enrich_request=EnrichRuleRequest(provider="openai", model="gpt-5.2")
                    )
        finally:
            db_patch.stop()

        assert chat.await_args.kwargs["effort"] is None


# ---------------------------------------------------------------------- lmstudio


class TestLmstudioGoesThroughTheSharedClient:
    @pytest.mark.asyncio
    async def test_lmstudio_model_date_suffix_is_normalized(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_LMSTUDIO_ENABLED", "true")
        service = await _sigma_llm_service("lmstudio", "not_required")
        lmstudio_post = AsyncMock(return_value={"choices": [{"message": {"content": "title: x"}}]})
        with patch.object(LLMService, "_post_lmstudio_chat", lmstudio_post):
            text = await _traced("lmstudio", "qwen/qwen3-4b-2507", service, timeout=180.0)

        assert text == "title: x"
        assert lmstudio_post.await_args.args[0]["model"] == "qwen/qwen3-4b"
        assert lmstudio_post.await_args.kwargs["timeout"] == 180.0

    @pytest.mark.asyncio
    async def test_lmstudio_empty_reply_is_a_503_with_finish_reason(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_LMSTUDIO_ENABLED", "true")
        service = await _sigma_llm_service("lmstudio", "not_required")
        empty = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        with patch.object(LLMService, "_post_lmstudio_chat", AsyncMock(return_value=empty)):
            with pytest.raises(HTTPException) as exc_info:
                await _traced("lmstudio", "qwen/qwen3-4b", service)

        assert exc_info.value.status_code == 503
        assert "finish_reason: length" in exc_info.value.detail
