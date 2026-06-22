"""Schema validation tests for workflow config v2."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.workflow_config_schema import (
    AgentConfig,
    WorkflowConfigV2,
)


def test_valid_v2_load():
    """New config load produces valid WorkflowConfigV2."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "", "Description": ""},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"Sigma": "ibm-research/CTI-BERT"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
        },
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    config = WorkflowConfigV2.model_validate(raw)
    assert config.Version == "2.0"
    assert config.Agents["RankAgent"].Model == "gpt-4"
    assert config.Thresholds.MinHuntScore == 97.0


def test_missing_version_fails():
    """Missing Version raises ValidationError."""
    raw = {
        "Metadata": {},
        "Thresholds": {},
        "Agents": {},
        "Embeddings": {},
        "Features": {},
        "Prompts": {},
        "Execution": {},
    }
    with pytest.raises(ValidationError):
        WorkflowConfigV2.model_validate(raw)


def test_invalid_version_fails():
    """Version other than 2.0 fails."""
    raw = {
        "Version": "1.0",
        "Metadata": {},
        "Thresholds": {},
        "Agents": {},
        "Embeddings": {},
        "Features": {},
        "Prompts": {},
        "Execution": {},
    }
    with pytest.raises(ValidationError):
        WorkflowConfigV2.model_validate(raw)


def test_invalid_value_types_fail():
    """Invalid types (e.g. string for float) raise ValidationError."""
    raw = {
        "Version": "2.0",
        "Metadata": {},
        "Thresholds": {
            "MinHuntScore": "not-a-float",
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": {},
        "Embeddings": {},
        "Features": {},
        "Prompts": {},
        "Execution": {},
    }
    with pytest.raises(ValidationError):
        WorkflowConfigV2.model_validate(raw)


def test_agent_config_required_fields():
    """AgentConfig has Provider, Model, Temperature, TopP, Enabled."""
    agent = AgentConfig(Provider="openai", Model="gpt-4", Temperature=0.0, TopP=0.9, Enabled=True)
    assert agent.Provider == "openai"
    assert agent.Model == "gpt-4"
    assert agent.Enabled is True


@pytest.mark.regression
def test_to_legacy_response_dict_includes_extract_agent_settings():
    """Legacy response includes agent_prompts.ExtractAgentSettings.disabled_agents for UI persistence."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "x", "Description": "x"},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "CmdlineExtract": {
                "Provider": "openai",
                "Model": "gpt-4",
                "Temperature": 0.0,
                "TopP": 0.9,
                "Enabled": True,
            },
        },
        "Embeddings": {"Sigma": "bert"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "CmdlineExtract": {"prompt": "", "instructions": ""},
        },
        "Execution": {
            "ExtractAgentSettings": {"DisabledAgents": ["CmdlineExtract", "ProcTreeExtract"]},
            "OsDetectionSelectedOs": ["Windows"],
        },
    }
    config = WorkflowConfigV2.model_validate(raw)
    legacy = config.to_legacy_response_dict(id=1, version=2, is_active=True, created_at="", updated_at="")
    assert "ExtractAgentSettings" in legacy["agent_prompts"]
    assert legacy["agent_prompts"]["ExtractAgentSettings"]["disabled_agents"] == ["CmdlineExtract", "ProcTreeExtract"]


def test_flatten_for_llm_service_keys():
    """flatten_for_llm_service produces expected flat keys."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "x", "Description": "x"},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "CmdlineExtract": {
                "Provider": "openai",
                "Model": "gpt-4",
                "Temperature": 0.0,
                "TopP": 0.9,
                "Enabled": True,
            },
        },
        "Embeddings": {"Sigma": "bert"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "CmdlineExtract": {"prompt": "", "instructions": ""},
        },
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    config = WorkflowConfigV2.model_validate(raw)
    flat = config.flatten_for_llm_service()
    assert flat["RankAgent_provider"] == "openai"
    assert flat["RankAgent"] == "gpt-4"
    assert flat["RankAgent_temperature"] == 0.0
    assert flat["CmdlineExtract_model"] == "gpt-4"
    assert "OSDetectionAgent_embedding" not in flat  # removed 2026-06-22 (entity-driven)
    assert flat["SigmaEmbeddingModel"] == "bert"


_MINIMAL_V2_RAW = {
    "Version": "2.0",
    "Agents": {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    },
    "Prompts": {
        "RankAgent": {"prompt": "", "instructions": ""},
    },
}

_LEGACY_RESPONSE_DICT_KEYS = frozenset(
    {
        "id",
        "min_hunt_score",
        "ranking_threshold",
        "similarity_threshold",
        "junk_filter_threshold",
        "version",
        "is_active",
        "description",
        "agent_prompts",
        "agent_models",
        "sigma_fallback_enabled",
        "rank_agent_enabled",
        "cmdline_attention_preprocessor_enabled",
        "proc_tree_attention_preprocessor_enabled",
        "created_at",
        "updated_at",
    }
)


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.regression
def test_to_legacy_response_dict_key_set_is_stable():
    """to_legacy_response_dict exposes a stable, complete top-level key set.

    Consumers (UI, API routes) rely on every one of these keys being present.
    A removed or renamed key is a silent breaking change.
    """
    config = WorkflowConfigV2.model_validate(_MINIMAL_V2_RAW)
    legacy = config.to_legacy_response_dict()
    assert legacy.keys() == _LEGACY_RESPONSE_DICT_KEYS, (
        f"Key set drift detected.\n"
        f"  Added:   {legacy.keys() - _LEGACY_RESPONSE_DICT_KEYS}\n"
        f"  Removed: {_LEGACY_RESPONSE_DICT_KEYS - legacy.keys()}"
    )


def test_example_json_valid():
    """Example v2 JSON file validates."""
    path = Path(__file__).resolve().parent.parent.parent / "config" / "schema" / "workflow_config_v2_example.json"
    if not path.exists():
        pytest.skip("Example file not present")
    data = json.loads(path.read_text())
    config = WorkflowConfigV2.model_validate(data)
    assert config.Version == "2.0"
    assert len(config.Agents) >= 10


def test_stray_prompt_key_fails():
    """Prompts key that is not a canonical agent name raises ValidationError."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "x", "Description": "x"},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
        },
        "Embeddings": {"Sigma": "bert"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {"ExtractAgentSettings": {"prompt": "", "instructions": ""}},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    with pytest.raises(ValidationError, match="Prompts key .* is not a canonical agent name"):
        WorkflowConfigV2.model_validate(raw)


def _minimal_v2(agents: dict, prompts: dict | None = None) -> dict:
    """Minimal v2 payload with given Agents and Prompts."""
    return {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "x", "Description": "x"},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
        },
        "Agents": agents,
        "Embeddings": {"Sigma": "bert"},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": prompts if prompts is not None else {},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }


def test_valid_config_passes():
    """Full valid v2 config with all agents and prompts passes symmetry validation."""
    agent_cfg = {"Provider": "lmstudio", "Model": "m", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
    agents = {
        "RankAgent": agent_cfg,
        "ExtractAgent": agent_cfg,
        "SigmaAgent": agent_cfg,
        "CmdlineExtract": agent_cfg,
        "ProcTreeExtract": agent_cfg,
        "HuntQueriesExtract": agent_cfg,
    }
    # ExtractAgent is a model/provider fallback key and must NOT appear in Prompts
    prompts = {name: {"prompt": "", "instructions": ""} for name in agents if name != "ExtractAgent"}
    raw = _minimal_v2(agents, prompts)
    config = WorkflowConfigV2.model_validate(raw)
    assert config.Version == "2.0"
    assert len(config.Agents) == 6
    assert len(config.Prompts) == 5


def test_enabled_agent_missing_model_raises():
    """Enabled agent with empty Model raises ValidationError."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Agent 'RankAgent' is Enabled but missing Provider or Model"):
        WorkflowConfigV2.model_validate(raw)


def test_enabled_agent_missing_provider_raises():
    """Enabled agent with empty Provider raises ValidationError."""
    agents = {
        "RankAgent": {"Provider": "", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Agent 'RankAgent' is Enabled but missing Provider or Model"):
        WorkflowConfigV2.model_validate(raw)


def test_disabled_agent_allows_empty_model():
    """Disabled agent with empty Model passes validation."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": False},
    }
    prompts: dict = {}
    raw = _minimal_v2(agents, prompts)
    config = WorkflowConfigV2.model_validate(raw)
    assert config.Agents["RankAgent"].Enabled is False
    assert config.Agents["RankAgent"].Model == ""


# ── Regression: preset import model-key contract ──────────────────────────────
# These tests pin the exact backend contract that applyPreset() in the frontend
# relies on. flatten_for_llm_service() must use "RankAgent" (not "RankAgent_model")
# as the model key.


@pytest.mark.regression
def test_flatten_for_llm_service_returns_rankagent_model_key():
    """flatten_for_llm_service uses bare 'RankAgent' as the model key for main agents.

    The frontend reads agent_models['RankAgent'] to populate the model dropdown.
    If the key changes (e.g. to 'RankAgent_model'), the dropdown shows the placeholder.
    """
    agents = {
        "RankAgent": {
            "Provider": "lmstudio",
            "Model": "qwen/qwen3-8b",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Enabled": True,
        },
    }
    prompts = {
        "RankAgent": {"prompt": "test", "instructions": ""},
    }
    raw = _minimal_v2(agents, prompts)
    config = WorkflowConfigV2.model_validate(raw)
    flat = config.flatten_for_llm_service()

    assert flat["RankAgent"] == "qwen/qwen3-8b", "model key must be bare 'RankAgent', not 'RankAgent_model'"
    assert flat["RankAgent_provider"] == "lmstudio"
    assert "RankAgent_model" not in flat, "sub-agent style key must not appear for main agents"


@pytest.mark.regression
def test_threshold_config_rejects_auto_trigger_hunt_score_threshold():
    """ThresholdConfig (extra=forbid) must reject AutoTriggerHuntScoreThreshold after its removal.

    Guards against accidental re-addition of the field. If a preset or DB record sends
    this key, schema validation must fail loudly rather than silently accept it.
    """
    from src.config.workflow_config_schema import ThresholdConfig

    with pytest.raises(ValidationError):
        ThresholdConfig.model_validate({"AutoTriggerHuntScoreThreshold": 60.0})
