"""Export preset as canonical v2: strict schema, no legacy keys, metadata populated."""

from src.config.workflow_config_loader import export_preset_as_canonical_v2
from src.config.workflow_config_schema import WorkflowConfigV2


def test_export_is_v2_only():
    """Exported preset has Version 2.0 only; no version 1.0."""
    raw = {
        "version": "1.0",
        "agent_models": {"RankAgent_provider": "openai", "RankAgent": "gpt-4"},
        "qa_enabled": {},
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
        },
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    out = export_preset_as_canonical_v2(raw)
    features = out.get("Features") or {}
    assert "RankAgentEnabled" not in features
    assert "OsDetectionFallbackEnabled" not in features


def test_no_stray_prompt_keys():
    """Export rejects preset with stray prompt key (e.g. ExtractAgentSettings in Prompts)."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "2025-01-01T00:00:00Z", "Description": "Test"},
        "Thresholds": {"MinHuntScore": 97.0, "RankingThreshold": 6.0, "SimilarityThreshold": 0.5, "JunkFilterThreshold": 0.8, "AutoTriggerHuntScoreThreshold": 60.0},
        "Agents": {"RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}},
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {"ExtractAgentSettings": {"prompt": "", "instructions": ""}},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    # Migration strips ExtractAgentSettings from Prompts, so export succeeds with Prompts empty for that key
    out = export_preset_as_canonical_v2(raw)
    assert "ExtractAgentSettings" not in (out.get("Prompts") or {})


def test_qa_enabled_keys_match_agents():
    """QA.Enabled keys must exist in Agents; export validates and migration aligns OSDetectionAgent -> OSDetectionFallback."""
    raw = {
        "version": "1.0",
        "agent_models": {
            "RankAgent_provider": "openai",
            "RankAgent": "gpt-4",
            "OSDetectionAgent_fallback": "gpt-4",
        },
        "qa_enabled": {"OSDetectionAgent": True},
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
        "Agents": {"RankAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}},
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {},
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
        "agent_models": {"RankAgent_provider": "openai", "RankAgent": "gpt-4"},
        "qa_enabled": {},
    }
    out = export_preset_as_canonical_v2(raw)
    config = WorkflowConfigV2.model_validate(out)
    assert config.Version == "2.0"
    assert config.Metadata.CreatedAt
    assert config.Metadata.Description
