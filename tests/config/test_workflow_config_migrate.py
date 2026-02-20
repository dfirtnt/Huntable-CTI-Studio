"""Migration tests: v1 to v2 and round-trip accuracy."""

# Minimal agent_models so migrated config has all enabled agents with non-empty Model (schema invariant).
_MINIMAL_AGENT_MODELS = {
    "RankAgent_provider": "openai",
    "RankAgent": "gpt-4",
    "ExtractAgent": "gpt-4",
    "SigmaAgent": "gpt-4",
    "CmdlineExtract_model": "gpt-4",
    "ProcTreeExtract_model": "gpt-4",
    "HuntQueriesExtract_model": "gpt-4",
    "RankAgentQA": "gpt-4",
    "CmdLineQA": "gpt-4",
    "ProcTreeQA": "gpt-4",
    "HuntQueriesQA": "gpt-4",
}

from src.config.workflow_config_loader import (
    CORE_AGENTS,
    EXTRACT_AGENTS,
    QA_AGENTS,
    UTILITY_AGENTS,
)
from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import WorkflowConfigV2

# Minimal agent_prompts so migrated config satisfies prompt symmetry.
_MINIMAL_AGENT_PROMPTS = {
    name: {"prompt": "", "instructions": ""}
    for name in (CORE_AGENTS + EXTRACT_AGENTS + QA_AGENTS + UTILITY_AGENTS)
}


def test_v1_migrates_to_v2():
    """Legacy config load → migration → valid WorkflowConfigV2."""
    raw = {
        "version": "1.0",
        "thresholds": {"ranking_threshold": 6.0, "similarity_threshold": 0.5, "junk_filter_threshold": 0.8},
        "agent_models": {
            **_MINIMAL_AGENT_MODELS,
            "RankAgent_provider": "openai",
            "RankAgent": "gpt-4o-mini",
            "RankAgent_temperature": 0,
            "RankAgent_top_p": 0.9,
        },
        "qa_enabled": {"RankAgent": True},
        "qa_max_retries": 5,
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    migrated = migrate_v1_to_v2(raw)
    assert migrated["Version"] == "2.0"
    assert "Agents" in migrated
    assert "RankAgent" in migrated["Agents"]
    assert migrated["Agents"]["RankAgent"]["Model"] == "gpt-4o-mini"
    assert migrated["Agents"]["RankAgent"]["Provider"] == "openai"
    config = WorkflowConfigV2.model_validate(migrated)
    assert config.Version == "2.0"
    assert config.Agents["RankAgent"].Model == "gpt-4o-mini"


def test_migration_accuracy_roundtrip():
    """v1 → v2 → flatten preserves values for LLMService."""
    raw = {
        "version": "1.0",
        "agent_models": {
            **_MINIMAL_AGENT_MODELS,
            "RankAgent_provider": "anthropic",
            "RankAgent": "claude-sonnet-4-5",
            "RankAgent_temperature": 0.2,
            "RankAgent_top_p": 0.95,
            "CmdlineExtract_provider": "anthropic",
            "CmdlineExtract_model": "claude-sonnet-4-5",
            "OSDetectionAgent_embedding": "nlpaueb/sec-bert-base",
        },
        "qa_enabled": {},
        "sigma_fallback_enabled": True,
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    migrated = migrate_v1_to_v2(raw)
    config = WorkflowConfigV2.model_validate(migrated)
    flat = config.flatten_for_llm_service()
    assert flat["RankAgent_provider"] == "anthropic"
    assert flat["RankAgent"] == "claude-sonnet-4-5"
    assert flat["RankAgent_temperature"] == 0.2
    assert flat["RankAgent_top_p"] == 0.95
    assert flat["CmdlineExtract_model"] == "claude-sonnet-4-5"
    assert flat["OSDetectionAgent_embedding"] == "nlpaueb/sec-bert-base"


def test_cmdline_qa_normalized():
    """Legacy CmdLineQA normalizes to CmdlineQA in v2; flatten emits legacy key CmdLineQA for consumers."""
    raw = {
        "version": "1.0",
        "agent_models": {
            **_MINIMAL_AGENT_MODELS,
            "CmdLineQA_provider": "openai",
            "CmdLineQA": "gpt-4o",
            "CmdLineQA_temperature": 0.1,
            "CmdLineQA_top_p": 0.9,
        },
        "qa_enabled": {},
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    migrated = migrate_v1_to_v2(raw)
    assert "CmdlineQA" in migrated["Agents"]
    assert migrated["Agents"]["CmdlineQA"]["Model"] == "gpt-4o"
    config = WorkflowConfigV2.model_validate(migrated)
    flat = config.flatten_for_llm_service()
    assert flat["CmdLineQA_provider"] == "openai"
    assert flat["CmdLineQA"] == "gpt-4o"


def test_v2_passthrough():
    """If Version is already 2.0, migrate normalizes to strict v2 (no legacy feature keys)."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "x", "Description": "x"},
        "Thresholds": {"MinHuntScore": 97.0, "RankingThreshold": 6.0, "SimilarityThreshold": 0.5, "JunkFilterThreshold": 0.8, "AutoTriggerHuntScoreThreshold": 60.0},
        "Agents": {
            "RankAgent": {"Provider": "lmstudio", "Model": "x", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "lmstudio", "Model": "x", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    result = migrate_v1_to_v2(raw)
    assert result["Version"] == "2.0"
    assert "RankAgentEnabled" not in result.get("Features", {})
    assert "OsDetectionFallbackEnabled" not in result.get("Features", {})


def test_missing_required_sections_get_defaults():
    """Missing sections in v1 get default structure."""
    raw = {
        "version": "1.0",
        "agent_models": dict(_MINIMAL_AGENT_MODELS),
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    migrated = migrate_v1_to_v2(raw)
    assert "Thresholds" in migrated
    assert "Agents" in migrated
    assert migrated["Thresholds"]["MinHuntScore"] == 97.0
    config = WorkflowConfigV2.model_validate(migrated)
    assert len(config.Agents) == 11
