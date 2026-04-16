"""Tests for LMStudio model auto-loading."""

from unittest.mock import patch

import pytest

from src.services.lmstudio_model_loader import auto_load_workflow_models, extract_lmstudio_models

pytestmark = pytest.mark.unit


def test_extract_lmstudio_models_skips_disabled_qa_models():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }

    models = extract_lmstudio_models(agent_models, qa_enabled={})

    assert models == {"cmdline-model"}


def test_auto_load_workflow_models_only_loads_enabled_qa_models():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }

    with (
        patch("src.services.lmstudio_model_loader.find_lms_cli", return_value="lms"),
        patch("src.services.lmstudio_model_loader.check_model_loaded", return_value=False),
        patch("src.services.lmstudio_model_loader.get_model_context_length", side_effect=lambda model: 16384),
        patch("src.services.lmstudio_model_loader.load_model", return_value=(True, None)) as mock_load,
    ):
        result = auto_load_workflow_models(
            agent_models,
            qa_enabled={},
        )

    assert result["success"] is True
    assert result["models_loaded"] == ["cmdline-model"]
    assert mock_load.call_count == 1
    assert mock_load.call_args.args[1] == "cmdline-model"


def test_extract_lmstudio_models_skips_qa_for_disabled_subagent_even_if_flag_true():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }

    models = extract_lmstudio_models(
        agent_models,
        qa_enabled={"CmdlineExtract": True},
        disabled_agents=["CmdlineExtract"],
    )

    assert models == {"cmdline-model"}


def test_auto_load_workflow_models_skips_qa_for_disabled_subagent_even_if_flag_true():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }

    with (
        patch("src.services.lmstudio_model_loader.find_lms_cli", return_value="lms"),
        patch("src.services.lmstudio_model_loader.check_model_loaded", return_value=False),
        patch("src.services.lmstudio_model_loader.get_model_context_length", side_effect=lambda model: 16384),
        patch("src.services.lmstudio_model_loader.load_model", return_value=(True, None)) as mock_load,
    ):
        result = auto_load_workflow_models(
            agent_models,
            qa_enabled={"CmdlineExtract": True},
            disabled_agents=["CmdlineExtract"],
        )

    assert result["success"] is True
    assert result["models_loaded"] == ["cmdline-model"]
    assert mock_load.call_count == 1
    assert mock_load.call_args.args[1] == "cmdline-model"


def test_extract_lmstudio_models_includes_qa_for_enabled_subagent_when_not_disabled():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }

    models = extract_lmstudio_models(
        agent_models,
        qa_enabled={"CmdlineExtract": True},
        disabled_agents=[],
    )

    assert models == {"cmdline-model", "cmdline-qa-model"}
