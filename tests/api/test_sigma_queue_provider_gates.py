"""Provider gates, default models and error mapping for the Sigma queue LLM routes.

Regressions covered:
- B5: enrich, enrichment chat and manual validate billed a provider whose enable flag
  (WORKFLOW_*_ENABLED, AppSettings first) was off; chat replayed the stored provider
  even after it was disabled.
- B3: an empty model became "gpt-4o-mini" for every provider (sent to Anthropic, Codex
  or LMStudio); it must resolve the way the shared LLM client does for that provider.
- B2: an OpenAI 400/404 invalid_request_error was reported as an invalid API key, and
  validate had no insufficient_quota -> 402 mapping.
- A request-header key is the key billed; it is never swapped for the stored key.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.web.routes.sigma_queue import (
    EnrichmentChatTurnRequest,
    EnrichRuleRequest,
    continue_enrichment_chat,
    enrich_rule,
    validate_rule,
)

pytestmark = pytest.mark.api

_FLAG_AND_MODEL_ENV = (
    "WORKFLOW_OPENAI_ENABLED",
    "WORKFLOW_ANTHROPIC_ENABLED",
    "WORKFLOW_LMSTUDIO_ENABLED",
    "WORKFLOW_CODEX_ENABLED",
    "WORKFLOW_OPENAI_MODEL",
    "WORKFLOW_ANTHROPIC_MODEL",
    "WORKFLOW_CODEX_MODEL",
    "LMSTUDIO_MODEL",
)

_QUOTA_ERROR = (
    'OpenAI API error (429): {"error": {"message": "You exceeded your current quota.", '
    '"type": "insufficient_quota", "code": "insufficient_quota"}}'
)
_MODEL_NOT_FOUND_ERROR = (
    'OpenAI API error (404): {"error": {"message": "The model `gpt-nope` does not exist.", '
    '"type": "invalid_request_error", "code": "model_not_found"}}'
)


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch):
    """Start every test with no provider flags or default-model overrides in env."""
    for key in _FLAG_AND_MODEL_ENV:
        monkeypatch.delenv(key, raising=False)


def _request(headers=None, body=None):
    request = MagicMock(spec=Request)
    request.headers = headers or {}
    request.json = AsyncMock(return_value=body or {})
    return request


def _db_with_rule():
    """Patch DatabaseManager so the rule and article lookups succeed."""
    db_patch = patch("src.web.routes.sigma_queue.DatabaseManager")
    mock_db = db_patch.start()
    session = MagicMock()
    mock_db.return_value.get_session.return_value = session
    rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test Rule", rule_origin="generated", attribution=None)
    article = MagicMock(id=1, content="body", title="Article", canonical_url="", article_metadata=None)
    session.query.return_value.filter.return_value.first.side_effect = [rule, article, None, None]
    return db_patch


def _traced(side_effect=None, return_value=None):
    return patch(
        "src.web.routes.sigma_queue._call_traced_sigma_provider",
        AsyncMock(side_effect=side_effect, return_value=return_value),
    )


class _Stop(RuntimeError):
    """Raised by the traced-call stub once its arguments have been captured."""


# --------------------------------------------------------------------------- B5


class TestDisabledProvidersAreNeverCalled:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,flag,headers",
        [
            ("openai", "WORKFLOW_OPENAI_ENABLED", {"X-OpenAI-API-Key": "sk-header"}),
            ("anthropic", "WORKFLOW_ANTHROPIC_ENABLED", {"X-Anthropic-API-Key": "sk-ant-header"}),
            ("lmstudio", "WORKFLOW_LMSTUDIO_ENABLED", {}),
            ("codex", "WORKFLOW_CODEX_ENABLED", {}),
        ],
    )
    async def test_enrich_refuses_disabled_provider(self, monkeypatch, provider, flag, headers):
        monkeypatch.setenv(flag, "false")
        db_patch = _db_with_rule()
        try:
            with _traced(return_value="unused") as traced:
                with pytest.raises(HTTPException) as exc_info:
                    await enrich_rule(
                        _request(headers),
                        queue_id=1,
                        enrich_request=EnrichRuleRequest(provider=provider, model="some-model"),
                    )
        finally:
            db_patch.stop()

        assert exc_info.value.status_code == 400
        assert "disabled" in exc_info.value.detail
        assert flag in exc_info.value.detail
        traced.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enrich_appsettings_flag_wins_over_env(self, monkeypatch):
        """Invariant 5: AppSettings is read first, so an env 'true' cannot re-enable it."""
        monkeypatch.setenv("WORKFLOW_ANTHROPIC_ENABLED", "true")
        db_patch = _db_with_rule()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue._load_workflow_provider_settings",
                    return_value={"WORKFLOW_ANTHROPIC_ENABLED": "false"},
                ),
                _traced(return_value="unused") as traced,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await enrich_rule(
                        _request({"X-Anthropic-API-Key": "sk-ant-header"}),
                        queue_id=1,
                        enrich_request=EnrichRuleRequest(provider="anthropic", model="claude-sonnet-4-5"),
                    )
        finally:
            db_patch.stop()

        assert exc_info.value.status_code == 400
        assert "Anthropic provider is disabled" in exc_info.value.detail
        traced.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unset_flag_with_a_key_is_usable(self):
        """An unset flag follows the key, the same default LLMService applies."""
        db_patch = _db_with_rule()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue.resolve_provider_api_key",
                    AsyncMock(return_value="sk-ant-stored"),
                ),
                _traced(side_effect=_Stop("captured")) as traced,
            ):
                with pytest.raises(HTTPException):
                    await enrich_rule(
                        _request(),
                        queue_id=1,
                        enrich_request=EnrichRuleRequest(provider="anthropic", model="claude-sonnet-4-5"),
                    )
        finally:
            db_patch.stop()

        traced.assert_awaited_once()
        assert traced.await_args.kwargs["api_key"] == "sk-ant-stored"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,settings",
        [
            ("anthropic", {"WORKFLOW_ANTHROPIC_ENABLED": "false", "WORKFLOW_ANTHROPIC_API_KEY": "sk-ant"}),
            ("openai", {"WORKFLOW_OPENAI_ENABLED": "false", "WORKFLOW_OPENAI_API_KEY": "sk-openai"}),
            ("codex", {"WORKFLOW_CODEX_ENABLED": "false"}),
            ("lmstudio", {}),
        ],
    )
    async def test_chat_refuses_a_stored_provider_that_was_disabled_since(self, provider, settings):
        conversation = MagicMock(id=12, provider=provider, model="stored-model")
        conversation.messages = [
            {"role": "system", "content": "bounded system prompt"},
            {"role": "user", "content": "Initial enrichment"},
            {"role": "assistant", "content": "Initial answer"},
        ]
        session = MagicMock()
        session.query.return_value.filter.return_value.first.side_effect = [conversation, MagicMock(article_id=4)]

        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as db_manager,
            patch("src.web.routes.sigma_queue._load_workflow_provider_settings", return_value=settings),
            patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")),
            _traced(return_value="unused") as traced,
        ):
            db_manager.return_value.get_session.return_value = session
            with pytest.raises(HTTPException) as exc_info:
                await continue_enrichment_chat(
                    queue_id=3,
                    conversation_id=12,
                    chat_request=EnrichmentChatTurnRequest(message="And now?"),
                )

        assert exc_info.value.status_code == 400
        assert "disabled" in exc_info.value.detail
        traced.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,flag,headers",
        [
            ("openai", "WORKFLOW_OPENAI_ENABLED", {"X-OpenAI-API-Key": "sk-header"}),
            ("anthropic", "WORKFLOW_ANTHROPIC_ENABLED", {"X-Anthropic-API-Key": "sk-ant-header"}),
            ("lmstudio", "WORKFLOW_LMSTUDIO_ENABLED", {}),
        ],
    )
    async def test_manual_validate_refuses_disabled_provider(self, monkeypatch, provider, flag, headers):
        monkeypatch.setenv(flag, "false")
        db_patch = _db_with_rule()
        try:
            with _traced(return_value="unused") as traced:
                result = await validate_rule(
                    _request(headers, {"provider": provider, "model": "some-model"}),
                    queue_id=1,
                )
        finally:
            db_patch.stop()

        assert result["success"] is False
        assert result["attempts"] == 0
        assert flag in result["message"]
        assert result["provider"] == provider
        traced.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_manual_validate_missing_key_is_reported_without_a_call(self):
        db_patch = _db_with_rule()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value=None)),
                _traced(return_value="unused") as traced,
            ):
                result = await validate_rule(_request(body={"provider": "openai", "model": "gpt-4o-mini"}), 1)
        finally:
            db_patch.stop()

        assert result["success"] is False
        assert "No OpenAI API key is configured" in result["errors"][0]
        traced.assert_not_awaited()


# ----------------------------------------------------------------- header keys


class TestHeaderKeyIsTheKeyBilled:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,header",
        [("openai", "X-OpenAI-API-Key"), ("anthropic", "X-Anthropic-API-Key")],
    )
    async def test_enrich_passes_the_header_key_not_the_stored_one(self, provider, header):
        db_patch = _db_with_rule()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")
                ) as resolver,
                _traced(side_effect=_Stop("captured")) as traced,
            ):
                with pytest.raises(HTTPException):
                    await enrich_rule(
                        _request({header: "sk-from-header"}),
                        queue_id=1,
                        enrich_request=EnrichRuleRequest(provider=provider, model="m"),
                    )
        finally:
            db_patch.stop()

        resolver.assert_not_awaited()
        assert traced.await_args.kwargs["api_key"] == "sk-from-header"

    @pytest.mark.asyncio
    async def test_manual_validate_passes_the_header_key(self):
        db_patch = _db_with_rule()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")
                ) as resolver,
                _traced(side_effect=_Stop("captured")) as traced,
            ):
                await validate_rule(
                    _request({"X-Anthropic-API-Key": "sk-from-header"}, {"provider": "anthropic", "model": "m"}),
                    queue_id=1,
                )
        finally:
            db_patch.stop()

        resolver.assert_not_awaited()
        assert all(call.kwargs["api_key"] == "sk-from-header" for call in traced.await_args_list)


# --------------------------------------------------------------------------- B3


class TestEmptyModelResolvesPerProvider:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider,env,expected",
        [
            ("anthropic", {}, "claude-sonnet-4-5"),
            ("anthropic", {"WORKFLOW_ANTHROPIC_MODEL": "claude-opus-4-7"}, "claude-opus-4-7"),
            ("openai", {}, "gpt-4o-mini"),
            ("openai", {"WORKFLOW_OPENAI_MODEL": "gpt-4.1-mini"}, "gpt-4.1-mini"),
            ("codex", {"WORKFLOW_CODEX_ENABLED": "true"}, "gpt-5.6-luna"),
            ("lmstudio", {"WORKFLOW_LMSTUDIO_ENABLED": "true", "LMSTUDIO_MODEL": "qwen/qwen3-4b"}, "qwen/qwen3-4b"),
            ("lmstudio", {"WORKFLOW_LMSTUDIO_ENABLED": "true"}, "mistralai/mistral-7b-instruct-v0.3"),
        ],
    )
    async def test_enrich_default_model_matches_shared_client(self, monkeypatch, provider, env, expected):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        db_patch = _db_with_rule()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-stored")),
                _traced(side_effect=_Stop("captured")) as traced,
            ):
                with pytest.raises(HTTPException):
                    await enrich_rule(_request(), queue_id=1, enrich_request=EnrichRuleRequest(provider=provider))
        finally:
            db_patch.stop()

        assert traced.await_args.kwargs["model"] == expected

    @pytest.mark.asyncio
    async def test_enrich_lmstudio_default_reads_appsettings_first(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_LMSTUDIO_ENABLED", "true")
        monkeypatch.setenv("LMSTUDIO_MODEL", "env-model")
        db_patch = _db_with_rule()
        try:
            with (
                patch(
                    "src.web.routes.sigma_queue._load_lmstudio_settings",
                    return_value={"LMSTUDIO_MODEL": "appsettings-model"},
                ),
                _traced(side_effect=_Stop("captured")) as traced,
            ):
                with pytest.raises(HTTPException):
                    await enrich_rule(_request(), queue_id=1, enrich_request=EnrichRuleRequest(provider="lmstudio"))
        finally:
            db_patch.stop()

        assert traced.await_args.kwargs["model"] == "appsettings-model"

    @pytest.mark.asyncio
    async def test_manual_validate_default_model_is_provider_aware(self):
        db_patch = _db_with_rule()
        try:
            with (
                patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock(return_value="sk-ant")),
                _traced(side_effect=_Stop("captured")) as traced,
            ):
                result = await validate_rule(_request(body={"provider": "anthropic"}), queue_id=1)
        finally:
            db_patch.stop()

        assert traced.await_args.kwargs["model"] == "claude-sonnet-4-5"
        assert result["model"] == "claude-sonnet-4-5"


# --------------------------------------------------------------------------- B2


class TestRouteErrorMapping:
    @pytest.mark.asyncio
    async def test_enrich_model_not_found_is_400_not_bad_key(self):
        db_patch = _db_with_rule()
        try:
            with _traced(side_effect=RuntimeError(_MODEL_NOT_FOUND_ERROR)):
                with pytest.raises(HTTPException) as exc_info:
                    await enrich_rule(
                        _request({"X-OpenAI-API-Key": "sk-header"}),
                        queue_id=1,
                        enrich_request=EnrichRuleRequest(provider="openai", model="gpt-nope"),
                    )
        finally:
            db_patch.stop()

        assert exc_info.value.status_code == 400
        assert "API key" not in exc_info.value.detail
        assert "gpt-nope" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_enrich_quota_is_402(self):
        db_patch = _db_with_rule()
        try:
            with _traced(side_effect=RuntimeError(_QUOTA_ERROR)):
                with pytest.raises(HTTPException) as exc_info:
                    await enrich_rule(
                        _request({"X-OpenAI-API-Key": "sk-header"}),
                        queue_id=1,
                        enrich_request=EnrichRuleRequest(provider="openai", model="gpt-4o-mini"),
                    )
        finally:
            db_patch.stop()

        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_validate_quota_is_reported_as_quota_not_generic_failure(self):
        db_patch = _db_with_rule()
        try:
            with _traced(side_effect=RuntimeError(_QUOTA_ERROR)) as traced:
                result = await validate_rule(
                    _request({"X-OpenAI-API-Key": "sk-header"}, {"provider": "openai", "model": "gpt-4o-mini"}),
                    queue_id=1,
                )
        finally:
            db_patch.stop()

        assert result["success"] is False
        assert traced.await_count == 3
        assert all("quota exceeded" in entry["error"] for entry in result["conversation_log"])

    @pytest.mark.asyncio
    async def test_validate_model_not_found_is_not_reported_as_bad_key(self):
        db_patch = _db_with_rule()
        try:
            with _traced(side_effect=RuntimeError(_MODEL_NOT_FOUND_ERROR)):
                result = await validate_rule(
                    _request({"X-OpenAI-API-Key": "sk-header"}, {"provider": "openai", "model": "gpt-nope"}),
                    queue_id=1,
                )
        finally:
            db_patch.stop()

        errors = [entry["error"] for entry in result["conversation_log"]]
        assert errors and all("rejected the request" in error for error in errors)
        assert not any("invalid or expired" in error for error in errors)
