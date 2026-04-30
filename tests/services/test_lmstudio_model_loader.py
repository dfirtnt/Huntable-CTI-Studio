"""Tests for LMStudio model auto-loading (REST API)."""

from unittest.mock import patch

import pytest

from src.services.lmstudio_model_loader import auto_load_workflow_models, extract_lmstudio_models

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper: build a fake /api/v1/models response
# ---------------------------------------------------------------------------


def _models_response(models, loaded_map=None):
    """Build a list[dict] mimicking GET /api/v1/models data.

    Args:
        models: list of model id strings that are downloaded.
        loaded_map: dict mapping model_id -> list of context lengths for
                    loaded instances.  Omit for no loaded instances.
    """
    loaded_map = loaded_map or {}
    data = []
    for model_id in models:
        entry = {"id": model_id, "path": f"/models/{model_id}"}
        instances = []
        for ctx in loaded_map.get(model_id, []):
            instances.append({"config": {"context_length": ctx}})
        if instances:
            entry["loaded_instances"] = instances
        data.append(entry)
    return data


# ---------------------------------------------------------------------------
# extract_lmstudio_models (pure logic -- no HTTP)
# ---------------------------------------------------------------------------


def test_extract_lmstudio_models_skips_disabled_qa_models():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }

    models = extract_lmstudio_models(agent_models, qa_enabled={})

    assert models == {"cmdline-model"}


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


# ---------------------------------------------------------------------------
# auto_load_workflow_models (REST API path)
# ---------------------------------------------------------------------------


def _patch_api(models_data, load_ok=True, load_error=None):
    """Return context-manager patches that mock _fetch_models and _load_model_via_api."""
    return (
        patch(
            "src.services.lmstudio_model_loader._fetch_models",
            return_value=models_data,
        ),
        patch(
            "src.services.lmstudio_model_loader._load_model_via_api",
            return_value=(load_ok, load_error),
        ),
    )


def test_auto_load_loads_model_via_rest_api():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
    }
    models_data = _models_response(["cmdline-model"])

    p_fetch, p_load = _patch_api(models_data)
    with p_fetch, p_load as mock_load:
        result = auto_load_workflow_models(agent_models, qa_enabled={})

    assert result["success"] is True
    assert result["models_loaded"] == ["cmdline-model"]
    assert result["lmstudio_available"] is True
    assert result["lmstudio_cli_available"] is True  # backward compat
    assert mock_load.call_count == 1


def test_auto_load_skips_already_loaded_model_with_sufficient_context():
    agent_models = {
        "CmdlineExtract_model": "cmdline-8b-model",
        "CmdlineExtract_provider": "lmstudio",
    }
    # Model already loaded with 16384 context (meets WORKFLOW_MIN_CONTEXT)
    models_data = _models_response(["cmdline-8b-model"], {"cmdline-8b-model": [16384]})

    p_fetch, p_load = _patch_api(models_data)
    with p_fetch, p_load as mock_load:
        result = auto_load_workflow_models(agent_models, qa_enabled={})

    assert result["success"] is True
    assert result["models_skipped"] == ["cmdline-8b-model"]
    assert result["models_loaded"] == []
    assert mock_load.call_count == 0


def test_auto_load_fails_when_model_not_downloaded():
    agent_models = {
        "CmdlineExtract_model": "missing-model",
        "CmdlineExtract_provider": "lmstudio",
    }
    # Empty models list -- model not downloaded
    models_data = _models_response([])

    p_fetch, p_load = _patch_api(models_data)
    with p_fetch, p_load as mock_load:
        result = auto_load_workflow_models(agent_models, qa_enabled={})

    assert result["success"] is False
    assert len(result["models_failed"]) == 1
    assert "not found" in result["models_failed"][0][1].lower()
    assert mock_load.call_count == 0


def test_auto_load_returns_not_available_when_api_unreachable():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
    }

    with patch("src.services.lmstudio_model_loader._fetch_models", return_value=None):
        result = auto_load_workflow_models(agent_models, qa_enabled={})

    assert result["success"] is False
    assert result["lmstudio_available"] is False
    assert result["lmstudio_cli_available"] is False


def test_auto_load_only_loads_enabled_qa_models():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }
    models_data = _models_response(["cmdline-model"])

    p_fetch, p_load = _patch_api(models_data)
    with p_fetch, p_load as mock_load:
        result = auto_load_workflow_models(agent_models, qa_enabled={})

    assert result["success"] is True
    assert result["models_loaded"] == ["cmdline-model"]
    assert mock_load.call_count == 1


def test_auto_load_skips_qa_for_disabled_subagent_even_if_flag_true():
    agent_models = {
        "CmdlineExtract_model": "cmdline-model",
        "CmdlineExtract_provider": "lmstudio",
        "CmdLineQA": "cmdline-qa-model",
        "CmdLineQA_provider": "lmstudio",
    }
    models_data = _models_response(["cmdline-model"])

    p_fetch, p_load = _patch_api(models_data)
    with p_fetch, p_load as mock_load:
        result = auto_load_workflow_models(
            agent_models,
            qa_enabled={"CmdlineExtract": True},
            disabled_agents=["CmdlineExtract"],
        )

    assert result["success"] is True
    assert result["models_loaded"] == ["cmdline-model"]
    assert mock_load.call_count == 1
