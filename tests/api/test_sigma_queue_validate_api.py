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
        # Clear env so no provider has a key; keep WORKFLOW_LMSTUDIO_ENABLED falsy so we don't return lmstudio
        env_clear = {
            "WORKFLOW_LMSTUDIO_ENABLED": "false",
            "OPENAI_API_KEY": "",
            "WORKFLOW_OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "WORKFLOW_ANTHROPIC_API_KEY": "",
            "GEMINI_API_KEY": "",
            "WORKFLOW_GEMINI_API_KEY": "",
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
        with patch.dict("os.environ", {"WORKFLOW_LMSTUDIO_ENABLED": "false"}, clear=False):
            provider = _first_enabled_provider(mock_session)
        assert provider == "openai"

    def test_returns_openai_when_key_in_env_only(self):
        from src.web.routes.sigma_queue import _first_enabled_provider

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        with patch.dict(
            "os.environ", {"OPENAI_API_KEY": "sk-from-env", "WORKFLOW_LMSTUDIO_ENABLED": "false"}, clear=False
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
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await validate_rule(mock_request, queue_id=1)
            assert exc_info.value.status_code == 400

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
                yaml_response = (
                    "title: Test\nlogsource:\n  category: process_creation\n  product: windows\n"
                    "detection:\n  selection:\n    EventID: 1\n  condition: selection"
                )
                with patch(
                    "src.services.openai_chat_client.openai_chat_completions",
                    new_callable=AsyncMock,
                    return_value=yaml_response,
                ):
                    with patch("src.web.routes.sigma_queue.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = MagicMock(valid=True, errors=[])
                        result = await validate_rule(mock_request, queue_id=1)

            assert result.get("success") is True
            assert result.get("validated_yaml") is not None
            assert result.get("attempts", 0) >= 1
