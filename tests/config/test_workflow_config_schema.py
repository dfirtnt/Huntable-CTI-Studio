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
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "RankAgentQA": {"prompt": "", "instructions": ""},
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
        "QA": {},
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
        "QA": {},
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
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": {},
        "Embeddings": {},
        "QA": {},
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
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "CmdlineExtract": {
                "Provider": "openai",
                "Model": "gpt-4",
                "Temperature": 0.0,
                "TopP": 0.9,
                "Enabled": True,
            },
            "CmdlineQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "RankAgentQA": {"prompt": "", "instructions": ""},
            "CmdlineExtract": {"prompt": "", "instructions": ""},
            "CmdlineQA": {"prompt": "", "instructions": ""},
        },
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    config = WorkflowConfigV2.model_validate(raw)
    flat = config.flatten_for_llm_service()
    assert flat["RankAgent_provider"] == "openai"
    assert flat["RankAgent"] == "gpt-4"
    assert flat["RankAgent_temperature"] == 0.0
    assert flat["CmdlineExtract_model"] == "gpt-4"
    assert flat["OSDetectionAgent_embedding"] == "bert"
    assert flat["SigmaEmbeddingModel"] == "bert"


def test_example_json_valid():
    """Example v2 JSON file validates."""
    path = Path(__file__).resolve().parent.parent.parent / "config" / "schema" / "workflow_config_v2_example.json"
    if not path.exists():
        pytest.skip("Example file not present")
    data = json.loads(path.read_text())
    config = WorkflowConfigV2.model_validate(data)
    assert config.Version == "2.0"
    assert len(config.Agents) >= 10


def test_qa_enabled_orphan_fails():
    """QA.Enabled key not in Agents raises ValidationError."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "x", "Description": "x"},
        "Thresholds": {
            "MinHuntScore": 97.0,
            "RankingThreshold": 6.0,
            "SimilarityThreshold": 0.5,
            "JunkFilterThreshold": 0.8,
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {"UnknownAgent": True}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    with pytest.raises(ValidationError, match="QA.Enabled key .* not in Agents"):
        WorkflowConfigV2.model_validate(raw)


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
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
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
            "AutoTriggerHuntScoreThreshold": 60.0,
        },
        "Agents": agents,
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": prompts if prompts is not None else {},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }


def test_missing_rankagentqa_prompt_raises():
    """Missing prompt block for RankAgentQA raises ValidationError."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Missing prompt block for agent RankAgentQA"):
        WorkflowConfigV2.model_validate(raw)


def test_missing_cmdlineqa_prompt_raises():
    """Missing prompt block for CmdlineQA raises ValidationError."""
    agents = {
        "CmdlineExtract": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "CmdlineQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"CmdlineExtract": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Missing prompt block for agent CmdlineQA"):
        WorkflowConfigV2.model_validate(raw)


def test_missing_required_qa_agent_raises():
    """Missing required QA agent for RankAgent raises ValidationError."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Missing QA agent for RankAgent"):
        WorkflowConfigV2.model_validate(raw)


def test_orphan_qa_agent_raises():
    """Orphan QA agent (RankAgentQA without RankAgent) raises ValidationError."""
    agents = {
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgentQA": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Orphan QA agent RankAgentQA"):
        WorkflowConfigV2.model_validate(raw)


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
        "RankAgentQA": agent_cfg,
        "CmdlineQA": agent_cfg,
        "ProcTreeQA": agent_cfg,
        "HuntQueriesQA": agent_cfg,
        "OSDetectionFallback": {"Provider": "lmstudio", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": False},
    }
    prompts = {name: {"prompt": "", "instructions": ""} for name in agents if name != "OSDetectionFallback"}
    raw = _minimal_v2(agents, prompts)
    config = WorkflowConfigV2.model_validate(raw)
    assert config.Version == "2.0"
    assert len(config.Agents) == 11
    assert len(config.Prompts) == 10


def test_enabled_agent_missing_model_raises():
    """Enabled agent with empty Model raises ValidationError."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Agent 'RankAgent' is Enabled but missing Provider or Model"):
        WorkflowConfigV2.model_validate(raw)


def test_enabled_agent_missing_provider_raises():
    """Enabled agent with empty Provider raises ValidationError."""
    agents = {
        "RankAgent": {"Provider": "", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Agent 'RankAgent' is Enabled but missing Provider or Model"):
        WorkflowConfigV2.model_validate(raw)


def test_disabled_agent_allows_empty_model():
    """Disabled agent with empty Model passes validation."""
    agents = {
        "RankAgent": {"Provider": "openai", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": False},
        "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {"RankAgentQA": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    config = WorkflowConfigV2.model_validate(raw)
    assert config.Agents["RankAgent"].Enabled is False
    assert config.Agents["RankAgent"].Model == ""


def test_os_detection_fallback_disabled_allows_empty_model():
    """OSDetectionFallback disabled with empty Model passes validation."""
    agent_cfg = {"Provider": "lmstudio", "Model": "m", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
    agents = {
        "RankAgent": agent_cfg,
        "RankAgentQA": agent_cfg,
        "OSDetectionFallback": {"Provider": "lmstudio", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": False},
    }
    prompts = {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}}
    raw = _minimal_v2(agents, prompts)
    config = WorkflowConfigV2.model_validate(raw)
    assert config.Agents["OSDetectionFallback"].Enabled is False
    assert config.Agents["OSDetectionFallback"].Model == ""


def test_os_detection_fallback_enabled_requires_model():
    """OSDetectionFallback enabled with empty Model raises ValidationError."""
    agent_cfg = {"Provider": "lmstudio", "Model": "m", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
    agents = {
        "RankAgent": agent_cfg,
        "RankAgentQA": agent_cfg,
        "OSDetectionFallback": {"Provider": "lmstudio", "Model": "", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
    }
    prompts = {
        "RankAgent": {"prompt": "", "instructions": ""},
        "RankAgentQA": {"prompt": "", "instructions": ""},
        "OSDetectionFallback": {"prompt": "", "instructions": ""},
    }
    raw = _minimal_v2(agents, prompts)
    with pytest.raises(ValidationError, match="Agent 'OSDetectionFallback' is Enabled but missing Provider or Model"):
        WorkflowConfigV2.model_validate(raw)
