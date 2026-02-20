"""Export preset as canonical v2: strict schema, no legacy keys, metadata populated."""

# Minimal agent_models so v1→v2 migration produces all enabled agents with non-empty Model (schema invariant).
# OSDetectionFallback is disabled by default and may have empty Model; others need a model when Enabled.
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
    export_preset_as_canonical_v2,
    order_agents_for_export,
)
from src.config.workflow_config_schema import WorkflowConfigV2

# Minimal agent_prompts so migrated config satisfies prompt symmetry (every agent with Model has a prompt block).
_MINIMAL_AGENT_PROMPTS = {
    name: {"prompt": "", "instructions": ""}
    for name in (CORE_AGENTS + EXTRACT_AGENTS + QA_AGENTS + UTILITY_AGENTS)
}


def test_export_is_v2_only():
    """Exported preset has Version 2.0 only; no version 1.0."""
    raw = {
        "version": "1.0",
        "agent_models": dict(_MINIMAL_AGENT_MODELS),
        "qa_enabled": {},
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    out = export_preset_as_canonical_v2(raw)
    assert out.get("Version") == "2.0"
    assert "version" not in out or out.get("version") != "1.0"


def test_no_legacy_keys_present():
    """Exported preset has no legacy flat keys (rank_agent_enabled, osdetection_fallback_enabled in Features)."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "2025-01-01T00:00:00Z", "Description": "Test"},
        "Thresholds": {"MinHuntScore": 97.0, "RankingThreshold": 6.0, "SimilarityThreshold": 0.5, "JunkFilterThreshold": 0.8, "AutoTriggerHuntScoreThreshold": 60.0},
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    out = export_preset_as_canonical_v2(raw)
    features = out.get("Features") or {}
    assert "RankAgentEnabled" not in features
    assert "OsDetectionFallbackEnabled" not in features


def test_no_stray_prompt_keys():
    """Export strips stray prompt key (e.g. ExtractAgentSettings); canonical prompts retained."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "2025-01-01T00:00:00Z", "Description": "Test"},
        "Thresholds": {"MinHuntScore": 97.0, "RankingThreshold": 6.0, "SimilarityThreshold": 0.5, "JunkFilterThreshold": 0.8, "AutoTriggerHuntScoreThreshold": 60.0},
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {
            "RankAgent": {"prompt": "", "instructions": ""},
            "RankAgentQA": {"prompt": "", "instructions": ""},
            "ExtractAgentSettings": {"prompt": "", "instructions": ""},
        },
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    out = export_preset_as_canonical_v2(raw)
    assert "ExtractAgentSettings" not in (out.get("Prompts") or {})


def test_qa_enabled_keys_match_agents():
    """QA.Enabled keys must exist in Agents; export validates and migration aligns OSDetectionAgent -> OSDetectionFallback."""
    raw = {
        "version": "1.0",
        "agent_models": {**_MINIMAL_AGENT_MODELS, "OSDetectionAgent_fallback": "gpt-4"},
        "qa_enabled": {"OSDetectionAgent": True},
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    out = export_preset_as_canonical_v2(raw)
    qa_enabled = (out.get("QA") or {}).get("Enabled") or {}
    agents = out.get("Agents") or {}
    for key in qa_enabled:
        assert key in agents, f"QA.Enabled key {key} must be in Agents"


def test_metadata_not_empty():
    """Exported preset has non-empty Metadata.CreatedAt and Metadata.Description."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "", "Description": ""},
        "Thresholds": {"MinHuntScore": 97.0, "RankingThreshold": 6.0, "SimilarityThreshold": 0.5, "JunkFilterThreshold": 0.8, "AutoTriggerHuntScoreThreshold": 60.0},
        "Agents": {
            "RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
            "RankAgentQA": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True},
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    out = export_preset_as_canonical_v2(raw)
    meta = out.get("Metadata") or {}
    assert meta.get("CreatedAt"), "Metadata.CreatedAt must be populated"
    assert meta.get("Description"), "Metadata.Description must be populated"


def test_export_roundtrip_validates():
    """Exported dict loads and re-validates as WorkflowConfigV2."""
    raw = {
        "version": "1.0",
        "agent_models": dict(_MINIMAL_AGENT_MODELS),
        "qa_enabled": {},
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    out = export_preset_as_canonical_v2(raw)
    config = WorkflowConfigV2.model_validate(out)
    assert config.Version == "2.0"
    assert config.Metadata.CreatedAt
    assert config.Metadata.Description


def test_agent_export_order_is_deterministic():
    """Exported Agents section follows canonical group order; unknown agents last, sorted."""
    raw = {
        "version": "1.0",
        "agent_models": dict(_MINIMAL_AGENT_MODELS),
        "qa_enabled": {},
        "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    }
    out = export_preset_as_canonical_v2(raw)
    order = list(out.get("Agents") or {})
    known = CORE_AGENTS + EXTRACT_AGENTS + QA_AGENTS + UTILITY_AGENTS
    known_present = [n for n in known if n in order]
    unknown = sorted(k for k in order if k not in known)
    assert order == known_present + unknown


def test_order_agents_for_export_unknown_last_sorted():
    """order_agents_for_export puts unknown agents last in alphabetical order."""
    agents = {
        "ZAgent": {"Provider": "x", "Model": "y", "Temperature": 0, "TopP": 0.9, "Enabled": True},
        "RankAgent": {"Provider": "x", "Model": "y", "Temperature": 0, "TopP": 0.9, "Enabled": True},
        "AAgent": {"Provider": "x", "Model": "y", "Temperature": 0, "TopP": 0.9, "Enabled": True},
    }
    ordered = order_agents_for_export(agents)
    order = list(ordered.keys())
    assert order[0] == "RankAgent"
    assert "AAgent" in order and "ZAgent" in order
    assert order.index("AAgent") < order.index("ZAgent")
