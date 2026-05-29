"""LLMService init must unwrap nested agent_models (WorkflowConfigV2 form).

Regression: a nested-format config_models dict made every flat-key lookup miss,
and `_canonicalize_provider("")` silently defaulted every agent to "lmstudio".
"""

import logging
from unittest.mock import patch

import pytest

from src.services.llm_service import LLMService

pytestmark = pytest.mark.unit


def _build(config_models):
    with patch("src.services.llm_service.DatabaseManager") as mock_db:
        mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
        return LLMService(config_models=config_models)


class TestLLMServiceNestedConfigUnwrap:
    def test_nested_config_unwraps_to_correct_providers(self, caplog):
        nested = {
            "RankAgent": {"provider": "openai", "model": "gpt-4o"},
            "ExtractAgent": {"provider": "anthropic", "model": "claude-sonnet-4-5"},
            "SigmaAgent": {"provider": "openai", "model": "gpt-4o-mini"},
            "CmdlineExtract": {"provider": "anthropic", "model": "claude-sonnet-4-5"},
        }
        with caplog.at_level(logging.WARNING, logger="src.services.llm_service"):
            svc = _build(nested)

        # Providers must come through, not default to lmstudio
        assert svc.provider_rank == "openai"
        assert svc.provider_extract == "anthropic"
        assert svc.provider_sigma == "openai"

        # Models must come through (main agents use bare name as model key)
        assert svc.model_rank == "gpt-4o"
        assert svc.model_extract == "claude-sonnet-4-5"
        assert svc.model_sigma == "gpt-4o-mini"

        # Warning surfaces so the underlying save-path bug is observable
        assert any("nested WorkflowConfigV2 format" in rec.message for rec in caplog.records)

    def test_sub_agent_keys_visible_to_runtime(self):
        nested = {
            "RankAgent": {"provider": "openai", "model": "gpt-4o"},
            "ExtractAgent": {"provider": "openai", "model": "gpt-4o"},
            "SigmaAgent": {"provider": "openai", "model": "gpt-4o"},
            "CmdlineExtract": {"provider": "anthropic", "model": "claude-sonnet-4-5"},
        }
        svc = _build(nested)
        # The runtime reads agent_models["CmdlineExtract_provider"] and
        # agent_models["CmdlineExtract_model"]. Without unwrap, both miss.
        assert svc.config_models["CmdlineExtract_provider"] == "anthropic"
        assert svc.config_models["CmdlineExtract_model"] == "claude-sonnet-4-5"

    def test_flat_input_does_not_trigger_warning(self, caplog):
        flat = {
            "RankAgent": "gpt-4o",
            "RankAgent_provider": "openai",
            "ExtractAgent": "gpt-4o",
            "ExtractAgent_provider": "openai",
            "SigmaAgent": "gpt-4o",
            "SigmaAgent_provider": "openai",
        }
        with caplog.at_level(logging.WARNING, logger="src.services.llm_service"):
            svc = _build(flat)
        assert svc.provider_rank == "openai"
        assert not any("nested WorkflowConfigV2 format" in rec.message for rec in caplog.records)
