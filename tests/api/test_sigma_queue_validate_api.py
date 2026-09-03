"""API tests for SIGMA queue validate endpoint and workflow Sigma agent LLM resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.llm_service import WORKFLOW_PROVIDER_APPSETTING_KEYS


@pytest.mark.api
class TestLoadWorkflowProviderSettings:
    """Test _load_workflow_provider_settings."""

    def test_returns_empty_dict_when_no_rows(self):
        from src.web.routes.sigma_queue import _load_workflow_provider_settings

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        out = _load_workflow_provider_settings(mock_session)
        assert out == {}

    def test_returns_key_value_dict_from_rows(self):
        from src.web.routes.sigma_queue import _load_workflow_provider_settings

        mock_session = MagicMock()
        Row = type("Row", (), {"key": "WORKFLOW_OPENAI_API_KEY", "value": "sk-test"})
        mock_session.query.return_value.filter.return_value.all.return_value = [Row()]
        out = _load_workflow_provider_settings(mock_session)
        assert out == {"WORKFLOW_OPENAI_API_KEY": "sk-test"}

    def test_returns_all_workflow_keys_when_present(self):
        from src.web.routes.sigma_queue import _load_workflow_provider_settings

        mock_session = MagicMock()
        keys = list(WORKFLOW_PROVIDER_APPSETTING_KEYS.values())[:3]
        rows = [type("Row", (), {"key": k, "value": f"val-{k}"})() for k in keys]
        mock_session.query.return_value.filter.return_value.all.return_value = rows
        out = _load_workflow_provider_settings(mock_session)
        assert len(out) == 3
        assert all(k in WORKFLOW_PROVIDER_APPSETTING_KEYS.values() for k in out)


@pytest.mark.api
class TestFirstEnabledProvider:
    """Test _first_enabled_provider."""

    def test_raises_when_no_settings_and_no_env(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        # Clear env so no provider has a key; keep the keyless providers (LMStudio,
        # Codex) explicitly disabled so neither is returned ahead of the key scan.
        env_clear = {
            "WORKFLOW_LMSTUDIO_ENABLED": "false",
            "WORKFLOW_CODEX_ENABLED": "false",
            "OPENAI_API_KEY": "",
            "WORKFLOW_OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "WORKFLOW_ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env_clear, clear=False):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                _first_enabled_provider(mock_session)
            assert exc_info.value.status_code == 400
            assert "No LLM provider configured" in exc_info.value.detail

    def test_returns_openai_when_key_in_settings(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        mock_session = MagicMock()
        key = WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_api_key"]
        Row = type("Row", (), {"key": key, "value": "sk-from-db"})
        mock_session.query.return_value.filter.return_value.all.return_value = [Row()]
        with patch.dict(
            "os.environ",
            {"WORKFLOW_LMSTUDIO_ENABLED": "false", "WORKFLOW_CODEX_ENABLED": "false"},
            clear=False,
        ):
            provider = _first_enabled_provider(mock_session)
        assert provider == "openai"

    def test_returns_openai_when_key_in_env_only(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-from-env",
                "WORKFLOW_LMSTUDIO_ENABLED": "false",
                "WORKFLOW_CODEX_ENABLED": "false",
            },
            clear=False,
        ):
            provider = _first_enabled_provider(mock_session)
        assert provider == "openai"

    def test_returns_lmstudio_when_workflow_lmstudio_enabled_true(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        with patch.dict("os.environ", {"WORKFLOW_LMSTUDIO_ENABLED": "true"}, clear=False):
            provider = _first_enabled_provider(mock_session)
        assert provider == "lmstudio"


@pytest.mark.api
class TestGetSigmaAgentLlmFromWorkflow:
    """Test _get_sigma_agent_llm_from_workflow."""

    def test_raises_when_no_active_config(self):
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _get_sigma_agent_llm_from_workflow(mock_session)
        assert exc_info.value.status_code == 400
        assert "No active workflow config" in exc_info.value.detail or "Sigma agent" in exc_info.value.detail

    def test_raises_when_config_has_no_agent_models(self):
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_config = MagicMock()
        mock_config.agent_models = None
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_config
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _get_sigma_agent_llm_from_workflow(mock_session)
        assert exc_info.value.status_code == 400

    def test_returns_provider_model_apikey_when_config_and_settings_set(self):
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_config = MagicMock()
        mock_config.agent_models = {"SigmaAgent_provider": "openai", "SigmaAgent": "gpt-4o-mini"}
        mock_session = MagicMock()
        # Config query
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_config
        # Settings query (for _load_workflow_provider_settings)
        key = WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_api_key"]
        Row = type("Row", (), {"key": key, "value": "sk-test"})
        mock_session.query.return_value.filter.return_value.all.return_value = [Row()]
        with patch.dict("os.environ", {}, clear=False):
            with patch("src.web.routes.sigma_queue.os.getenv", return_value=None):
                provider, model, api_key = _get_sigma_agent_llm_from_workflow(mock_session)
        assert provider == "openai"
        assert model == "gpt-4o-mini"
        assert api_key == "sk-test"


def _session_with_agent_models(agent_models, settings_rows=None):
    """Build a mock session whose active-config query returns agent_models."""
    mock_config = MagicMock()
    mock_config.agent_models = agent_models
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_config
    mock_session.query.return_value.filter.return_value.all.return_value = settings_rows or []
    return mock_session


@pytest.mark.api
class TestSigmaAgentProviderResolutionDoesNotSubstitute:
    """Regression: an unsupported SigmaAgent_provider must never be silently swapped
    for a different provider while keeping the configured model name.

    The original defect paired the fallback provider (lmstudio, because
    WORKFLOW_LMSTUDIO_ENABLED=true) with the configured codex model 'gpt-5.6-sol',
    producing a provider/model combination that was never configured anywhere and a
    misleading 'model is not loaded' error from LMStudio.
    """

    def test_codex_provider_resolves_to_codex_not_lmstudio_fallback(self):
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_session = _session_with_agent_models({"SigmaAgent_provider": "codex", "SigmaAgent": "gpt-5.6-sol"})
        # Exactly the environment that produced the bug: lmstudio enabled, so the old
        # fallback path resolved to lmstudio while keeping the codex model name.
        env = {"WORKFLOW_LMSTUDIO_ENABLED": "true", "WORKFLOW_CODEX_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=False):
            provider, model, api_key = _get_sigma_agent_llm_from_workflow(mock_session)

        assert provider == "codex", "codex config must not fall back to another provider"
        assert model == "gpt-5.6-sol"
        assert api_key is None, "codex authenticates via subscription, not an API key"

    def test_unknown_provider_raises_instead_of_substituting(self):
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_session = _session_with_agent_models({"SigmaAgent_provider": "gemini", "SigmaAgent": "gemini-3-pro"})
        with patch.dict("os.environ", {"WORKFLOW_LMSTUDIO_ENABLED": "true"}, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                _get_sigma_agent_llm_from_workflow(mock_session)

        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert "gemini" in detail, "the error must name the provider that was actually configured"
        assert "SigmaAgent_provider" in detail

    def test_empty_provider_still_falls_back_to_first_enabled(self):
        """An unset provider is the one case where substitution is correct: the model
        name is defaulted alongside it, so no mismatched pair can be produced."""
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_session = _session_with_agent_models({"SigmaAgent_provider": "", "SigmaAgent": ""})
        with patch.dict(
            "os.environ",
            {"WORKFLOW_LMSTUDIO_ENABLED": "true", "LMSTUDIO_MODEL": "qwen/qwen3-4b-2507"},
            clear=False,
        ):
            provider, model, api_key = _get_sigma_agent_llm_from_workflow(mock_session)

        assert provider == "lmstudio"
        assert model == "qwen/qwen3-4b-2507"
        assert api_key == "not_required"

    def test_codex_disabled_raises_actionable_error(self):
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_session = _session_with_agent_models({"SigmaAgent_provider": "codex", "SigmaAgent": "gpt-5.6-sol"})
        env = {"WORKFLOW_LMSTUDIO_ENABLED": "true", "WORKFLOW_CODEX_ENABLED": "false"}
        with patch.dict("os.environ", env, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                _get_sigma_agent_llm_from_workflow(mock_session)

        assert exc_info.value.status_code == 400
        assert "WORKFLOW_CODEX_ENABLED" in exc_info.value.detail

    def test_codex_enabled_via_appsettings_overrides_env_default(self):
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        key = WORKFLOW_PROVIDER_APPSETTING_KEYS["codex_enabled"]
        Row = type("Row", (), {"key": key, "value": "true"})
        mock_session = _session_with_agent_models(
            {"SigmaAgent_provider": "codex", "SigmaAgent": "gpt-5.6-sol"},
            settings_rows=[Row()],
        )
        with patch.dict("os.environ", {"WORKFLOW_CODEX_ENABLED": "false"}, clear=False):
            provider, model, _ = _get_sigma_agent_llm_from_workflow(mock_session)

        assert provider == "codex"
        assert model == "gpt-5.6-sol"

    def test_codex_without_model_uses_codex_default_not_lmstudio_default(self):
        from src.web.routes.sigma_queue import _get_sigma_agent_llm_from_workflow

        mock_session = _session_with_agent_models({"SigmaAgent_provider": "codex", "SigmaAgent": ""})
        env = {
            "WORKFLOW_CODEX_ENABLED": "true",
            "WORKFLOW_CODEX_MODEL": "gpt-5.6-luna",
            "LMSTUDIO_MODEL": "should-not-be-used",
        }
        with patch.dict("os.environ", env, clear=False):
            provider, model, _ = _get_sigma_agent_llm_from_workflow(mock_session)

        assert provider == "codex"
        assert model == "gpt-5.6-luna"


@pytest.mark.api
class TestValidateRuleEndpoint:
    """Test validate_rule endpoint with use_workflow_sigma_agent."""

    @pytest.mark.asyncio
    async def test_validate_use_workflow_sigma_agent_returns_400_when_no_config(self):
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"use_workflow_sigma_agent": True})
        mock_request.headers = {}

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: x")
            mock_article = MagicMock(content="", title="", canonical_url="")
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
            mock_session.close = MagicMock()

            result = await validate_rule(mock_request, queue_id=1)
            assert result["success"] is False
            assert "workflow config" in result["message"].lower() or "no active" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_use_workflow_sigma_agent_success_when_llm_resolved(self):
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(
            return_value={"use_workflow_sigma_agent": True, "rule_yaml": "title: Test\nlogsource: {}\ndetection: {}"}
        )
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            with patch(
                "src.web.routes.sigma_queue._get_sigma_agent_llm_from_workflow",
                return_value=("openai", "gpt-4o-mini", "sk-test"),
            ):
                # A rule the SigmaHQ blocking layer accepts: id/status/level present and no
                # EventID inside a category-based logsource (sigmahq_category_event_id).
                yaml_response = (
                    "title: Queue validation test rule\n"
                    "id: 3f6a1c2e-8b4d-4e9f-a1b2-c3d4e5f60718\n"
                    "status: experimental\n"
                    "description: A queue validation test rule description\n"
                    "logsource:\n  category: process_creation\n  product: windows\n"
                    "detection:\n  selection:\n    Image|endswith: '\\\\cmd.exe'\n  condition: selection\n"
                    "level: medium"
                )
                with patch(
                    "src.services.openai_chat_client.openai_chat_completions",
                    new_callable=AsyncMock,
                    return_value=yaml_response,
                ):
                    result = await validate_rule(mock_request, queue_id=1)

            assert result.get("success") is True
            assert result.get("validated_yaml") is not None
            assert result.get("attempts", 0) >= 1

    @pytest.mark.asyncio
    async def test_validate_use_workflow_sigma_agent_retries_pysigma_modifier_error(self):
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"use_workflow_sigma_agent": True})
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")
        invalid_yaml = (
            "title: Queue modifier regression rule\ndescription: A queue modifier regression rule description\n"
            "logsource:\n  category: process_creation\n"
            "detection:\n  selection:\n    Image|definitelynotreal: cmd.exe\n  condition: selection\nlevel: medium"
        )

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            with patch(
                "src.web.routes.sigma_queue._get_sigma_agent_llm_from_workflow",
                return_value=("openai", "gpt-4o-mini", "sk-test"),
            ):
                with patch(
                    "src.services.openai_chat_client.openai_chat_completions",
                    new_callable=AsyncMock,
                    return_value=invalid_yaml,
                ) as mock_completion:
                    result = await validate_rule(mock_request, queue_id=1)

        assert result["success"] is False
        assert result["attempts"] == 3
        assert mock_completion.await_count == 3
        assert len(result["validation_results"]) == 3
        assert all(item["errors"][0].startswith("pySigma SigmaModifierError:") for item in result["validation_results"])


# Accepted by pySigma, the Huntable policy pass and the SigmaHQ blocking layer (no EventID
# inside a category logsource; id/status/level present).
VALID_SIGMA_YAML = (
    "title: Queue validation test rule\n"
    "id: 3f6a1c2e-8b4d-4e9f-a1b2-c3d4e5f60718\n"
    "status: experimental\n"
    "description: A queue validation test rule description\n"
    "logsource:\n  category: process_creation\n  product: windows\n"
    "detection:\n  selection:\n    Image|endswith: '\\\\cmd.exe'\n  condition: selection\n"
    "level: medium"
)


@pytest.mark.api
class TestValidateRuleCodexDispatch:
    """The validate/repair loop must be able to drive the codex provider, not just
    openai/anthropic/lmstudio. Before the fix the dispatch rejected codex with a 400,
    so a codex-configured Sigma agent could never validate a rule."""

    @pytest.mark.asyncio
    async def test_codex_routes_to_codex_client_and_validates(self):
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"use_workflow_sigma_agent": True})
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")

        codex_client = MagicMock()
        codex_client.complete = AsyncMock(
            return_value={
                "model": "gpt-5.6-sol",
                "usage": {},
                "choices": [{"message": {"content": VALID_SIGMA_YAML}}],
            }
        )

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            with patch(
                "src.web.routes.sigma_queue._get_sigma_agent_llm_from_workflow",
                return_value=("codex", "gpt-5.6-sol", None),
            ):
                with patch(
                    "src.web.routes.sigma_queue.CodexAppServerClient", return_value=codex_client
                ) as mock_codex_cls:
                    with patch(
                        "src.web.routes.sigma_queue._call_lmstudio_sigma_text", new_callable=AsyncMock
                    ) as mock_lmstudio:
                        result = await validate_rule(mock_request, queue_id=1)

        assert result["success"] is True
        assert result["provider"] == "codex"
        assert result["model"] == "gpt-5.6-sol"
        mock_codex_cls.assert_called_once()
        codex_client.complete.assert_awaited_once()
        mock_lmstudio.assert_not_awaited(), "codex must never be serviced by the LMStudio transport"

    @pytest.mark.asyncio
    async def test_codex_app_server_error_is_reported_not_swallowed(self):
        """A codex transport failure must surface the real codex error against the codex
        provider. Each retry records its own error in the conversation log, which is what
        the Validation Results panel renders."""
        from starlette.requests import Request

        from src.services.codex_app_server_client import CodexAppServerError
        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"use_workflow_sigma_agent": True})
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")

        codex_client = MagicMock()
        codex_client.complete = AsyncMock(side_effect=CodexAppServerError("codex app server unreachable"))

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            with patch(
                "src.web.routes.sigma_queue._get_sigma_agent_llm_from_workflow",
                return_value=("codex", "gpt-5.6-sol", None),
            ):
                with patch("src.web.routes.sigma_queue.CodexAppServerClient", return_value=codex_client):
                    result = await validate_rule(mock_request, queue_id=1)

        assert result["success"] is False
        assert result["provider"] == "codex"
        assert result["model"] == "gpt-5.6-sol"
        # The real transport error is preserved per attempt, attributed to codex --
        # not replaced by a fabricated failure from a substituted provider.
        assert result["attempts"] == 3
        assert len(result["conversation_log"]) == 3
        assert all("codex app server unreachable" in entry["error"] for entry in result["conversation_log"])
        assert codex_client.complete.await_count == 3

    @pytest.mark.asyncio
    async def test_request_supplied_codex_provider_is_accepted(self):
        """The non-workflow path (explicit provider in the request body) must also
        accept codex rather than reporting it as unsupported."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"provider": "codex", "model": "gpt-5.6-sol"})
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")

        codex_client = MagicMock()
        codex_client.complete = AsyncMock(
            return_value={"model": "gpt-5.6-sol", "usage": {}, "choices": [{"message": {"content": VALID_SIGMA_YAML}}]}
        )

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            with patch.dict("os.environ", {"WORKFLOW_CODEX_ENABLED": "true"}, clear=False):
                with patch("src.web.routes.sigma_queue.CodexAppServerClient", return_value=codex_client):
                    result = await validate_rule(mock_request, queue_id=1)

        assert result["success"] is True
        assert result["provider"] == "codex"

    @pytest.mark.asyncio
    async def test_request_supplied_codex_rejected_when_disabled(self):
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"provider": "codex", "model": "gpt-5.6-sol"})
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            with patch.dict("os.environ", {"WORKFLOW_CODEX_ENABLED": "false"}, clear=False):
                result = await validate_rule(mock_request, queue_id=1)

        assert result["success"] is False
        assert "WORKFLOW_CODEX_ENABLED" in result["message"]
        # The failure must name codex, never a substituted provider.
        assert result["provider"] == "codex"

    @pytest.mark.asyncio
    async def test_still_rejects_genuinely_unsupported_provider(self):
        from starlette.requests import Request

        from src.web.routes.sigma_queue import validate_rule

        mock_request = MagicMock(spec=Request)
        mock_request.json = AsyncMock(return_value={"provider": "gemini", "model": "gemini-3-pro"})
        mock_request.headers = {}

        mock_rule = MagicMock(id=1, article_id=1, rule_yaml="title: Test")
        mock_article = MagicMock(id=1, content="", title="", canonical_url="")

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.get_session.return_value = mock_session
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_session.close = MagicMock()

            result = await validate_rule(mock_request, queue_id=1)

        assert result["success"] is False
        assert "gemini" in result["message"]
        assert "codex" in result["errors"][0], "the supported-provider list must advertise codex"


@pytest.mark.api
class TestFirstEnabledProviderKnowsCodex:
    """_first_enabled_provider is the last substitution path in the module. It must be
    able to name codex, which is keyless and therefore invisible to the API-key scan."""

    def _empty_settings_session(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        return mock_session

    def test_returns_codex_when_only_codex_enabled(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        env = {
            "WORKFLOW_LMSTUDIO_ENABLED": "false",
            "WORKFLOW_CODEX_ENABLED": "true",
            "OPENAI_API_KEY": "",
            "WORKFLOW_OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "WORKFLOW_ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env, clear=False):
            assert _first_enabled_provider(self._empty_settings_session()) == "codex"

    def test_codex_enabled_via_appsettings_is_discovered(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        key = WORKFLOW_PROVIDER_APPSETTING_KEYS["codex_enabled"]
        Row = type("Row", (), {"key": key, "value": "true"})
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [Row()]
        env = {
            "WORKFLOW_LMSTUDIO_ENABLED": "false",
            "WORKFLOW_CODEX_ENABLED": "false",
            "OPENAI_API_KEY": "",
            "WORKFLOW_OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "WORKFLOW_ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env, clear=False):
            assert _first_enabled_provider(mock_session) == "codex"

    def test_lmstudio_still_wins_when_both_enabled(self):
        """Preserves the pre-existing precedence; codex is an added fallback, not a
        reordering of what already worked."""
        from src.web.routes.sigma_queue import _first_enabled_provider

        env = {"WORKFLOW_LMSTUDIO_ENABLED": "true", "WORKFLOW_CODEX_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=False):
            assert _first_enabled_provider(self._empty_settings_session()) == "lmstudio"

    def test_still_raises_when_nothing_is_enabled(self):
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import _first_enabled_provider

        env = {
            "WORKFLOW_LMSTUDIO_ENABLED": "false",
            "WORKFLOW_CODEX_ENABLED": "false",
            "OPENAI_API_KEY": "",
            "WORKFLOW_OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "WORKFLOW_ANTHROPIC_API_KEY": "",
        }
        with patch.dict("os.environ", env, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                _first_enabled_provider(self._empty_settings_session())
        assert exc_info.value.status_code == 400
        assert "WORKFLOW_CODEX_ENABLED" in exc_info.value.detail
