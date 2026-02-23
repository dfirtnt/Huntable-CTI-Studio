"""Export preset as canonical v2: strict schema, no legacy keys, metadata populated."""

from types import SimpleNamespace

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
    UI_ORDERED_TOP_LEVEL_ORDER,
    UTILITY_AGENTS,
    export_preset_as_canonical_v2,
    is_ui_ordered_preset,
    load_workflow_config,
    order_agents_for_export,
)

# Minimal agent_prompts so migrated config satisfies prompt symmetry (every agent with Model has a prompt block).
_MINIMAL_AGENT_PROMPTS = {
    name: {"prompt": "", "instructions": ""} for name in (CORE_AGENTS + EXTRACT_AGENTS + QA_AGENTS + UTILITY_AGENTS)
}

# Full legacy v1 preset (all required keys) so strict import validation passes.
_FULL_LEGACY_V1 = {
    "version": "1.0",
    "thresholds": {},
    "agent_models": dict(_MINIMAL_AGENT_MODELS),
    "agent_prompts": dict(_MINIMAL_AGENT_PROMPTS),
    "qa_enabled": {},
    "qa_max_retries": 5,
    "sigma_fallback_enabled": False,
    "osdetection_fallback_enabled": False,
    "rank_agent_enabled": True,
    "cmdline_attention_preprocessor_enabled": True,
    "extract_agent_settings": {"disabled_agents": []},
    "description": "",
    "created_at": "",
}


def test_export_is_v2_only():
    """Exported preset has Version 2.0 only; no version 1.0."""
    raw = dict(_FULL_LEGACY_V1)
    out = export_preset_as_canonical_v2(raw)
    assert out.get("Version") == "2.0"
    assert "version" not in out or out.get("version") != "1.0"


def test_no_legacy_keys_present():
    """Exported preset is UI-ordered; no top-level Features with legacy keys."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "2025-01-01T00:00:00Z", "Description": "Test"},
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
        "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
        "QA": {"Enabled": {}, "MaxRetries": 5},
        "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
        "Prompts": {"RankAgent": {"prompt": "", "instructions": ""}, "RankAgentQA": {"prompt": "", "instructions": ""}},
        "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
    }
    out = export_preset_as_canonical_v2(raw)
    assert is_ui_ordered_preset(out)
    assert "Features" not in out
    assert "RankAgent" in out
    assert "Enabled" in out["RankAgent"]
    assert "OSDetection" in out
    assert "FallbackEnabled" in out["OSDetection"]


def test_no_stray_prompt_keys():
    """Export is UI-ordered; RankAgent has Prompt; no ExtractAgentSettings section."""
    raw = {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "2025-01-01T00:00:00Z", "Description": "Test"},
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
    assert "Prompts" not in out
    assert "Prompt" in out.get("RankAgent", {})
    assert "ExtractAgentSettings" not in out


def test_qa_enabled_keys_match_agents():
    """Exported UI-ordered preset loads; config has QA.Enabled keys in Agents."""
    raw = {
        **_FULL_LEGACY_V1,
        "agent_models": {**_MINIMAL_AGENT_MODELS, "OSDetectionAgent_fallback": "gpt-4"},
        "qa_enabled": {"OSDetectionAgent": True},
    }
    out = export_preset_as_canonical_v2(raw)
    config = load_workflow_config(out)
    qa_enabled = config.QA.Enabled
    agents = config.Agents
    for key in qa_enabled:
        assert key in agents, f"QA.Enabled key {key} must be in Agents"


def test_metadata_not_empty():
    """Exported preset has non-empty Metadata.CreatedAt and Metadata.Description."""
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
    """Exported UI-ordered dict loads via load_workflow_config and validates as WorkflowConfigV2."""
    raw = dict(_FULL_LEGACY_V1)
    out = export_preset_as_canonical_v2(raw)
    config = load_workflow_config(out)
    assert config.Version == "2.0"
    assert config.Metadata.CreatedAt
    assert config.Metadata.Description


def test_order_agents_for_export_unknown_last_sorted():
    """order_agents_for_export uses UI order; unknown agents last in alphabetical order."""
    agents = {
        "ZAgent": {"Provider": "x", "Model": "y", "Temperature": 0, "TopP": 0.9, "Enabled": True},
        "RankAgent": {"Provider": "x", "Model": "y", "Temperature": 0, "TopP": 0.9, "Enabled": True},
        "AAgent": {"Provider": "x", "Model": "y", "Temperature": 0, "TopP": 0.9, "Enabled": True},
    }
    ordered = order_agents_for_export(agents)
    order = list(ordered.keys())
    assert order[0] == "RankAgent"  # first in AGENTS_ORDER_UI among present
    assert "AAgent" in order and "ZAgent" in order
    assert order.index("AAgent") < order.index("ZAgent")


def test_export_ui_ordered_top_level_order():
    """Exported preset has top-level keys in UI order: Version, Metadata, JunkFilter, QASettings, OSDetection, RankAgent, …."""
    raw = dict(_FULL_LEGACY_V1)
    out = export_preset_as_canonical_v2(raw)
    order = list(out.keys())
    for i, key in enumerate(UI_ORDERED_TOP_LEVEL_ORDER):
        if key in out:
            assert order.index(key) == i, f"Expected {key} at index {i}, got order {order}"


def test_export_junk_and_per_agent_thresholds():
    """Exported preset has JunkFilter block and per-section thresholds (RankAgent.RankingThreshold, SigmaAgent.SimilarityThreshold)."""
    raw = dict(_FULL_LEGACY_V1)
    out = export_preset_as_canonical_v2(raw)
    assert "JunkFilter" in out
    assert "JunkFilterThreshold" in out["JunkFilter"]
    assert "RankAgent" in out
    assert "RankingThreshold" in out["RankAgent"]
    assert "SigmaAgent" in out
    assert "SimilarityThreshold" in out["SigmaAgent"]


def test_export_includes_os_detection_selected_os_when_sent():
    """Exported UI-ordered preset includes OSDetection.SelectedOs when client sends agent_models[OSDetectionAgent_selected_os]."""
    raw = {
        **_FULL_LEGACY_V1,
        "agent_models": {
            **_MINIMAL_AGENT_MODELS,
            "OSDetectionAgent_selected_os": ["Windows", "Linux"],
        },
    }
    out = export_preset_as_canonical_v2(raw)
    osd = out.get("OSDetection") or {}
    assert osd.get("SelectedOs") == ["Windows", "Linux"]


def test_ui_ordered_export_roundtrip_preserves_values():
    """Export (UI-ordered) then load_workflow_config preserves thresholds, SelectedOs, and agent settings."""
    raw = {
        **_FULL_LEGACY_V1,
        "agent_models": {**_MINIMAL_AGENT_MODELS, "OSDetectionAgent_selected_os": ["Linux"]},
        "qa_enabled": {"RankAgent": True},
    }
    exported = export_preset_as_canonical_v2(raw)
    assert is_ui_ordered_preset(exported)
    config = load_workflow_config(exported)
    assert config.Thresholds.RankingThreshold == 6.0
    assert config.Thresholds.JunkFilterThreshold == 0.8
    assert config.Execution.OsDetectionSelectedOs == ["Linux"]
    assert config.QA.Enabled.get("RankAgent") is True
    assert config.Agents["RankAgent"].Model
    assert config.Agents["RankAgentQA"].Model


def test_ui_ordered_to_legacy_includes_min_hunt_and_auto_trigger():
    """UI-ordered preset → load_workflow_config → to_legacy has min_hunt_score and auto_trigger_hunt_score_threshold so they are not silently dropped."""
    ui_ordered = {
        "Version": "2.0",
        "Metadata": {},
        "JunkFilter": {"JunkFilterThreshold": 0.8},
        "QASettings": {"MaxRetries": 3},
        "Thresholds": {"MinHuntScore": 85.0, "AutoTriggerHuntScoreThreshold": 50.0},
        "OSDetection": {
            "Embedding": "bert",
            "FallbackEnabled": False,
            "Fallback": {},
            "SelectedOs": ["Windows"],
            "Prompt": {},
        },
        "RankAgent": {
            "Enabled": True,
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "RankingThreshold": 6.0,
            "Prompt": {},
            "QAEnabled": False,
            "QA": {},
            "QAPrompt": {},
        },
        "ExtractAgent": {"Provider": "openai", "Model": "gpt-4", "Temperature": 0, "TopP": 0.9, "Prompt": {}},
        "CmdlineExtract": {
            "Enabled": True,
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "Prompt": {},
            "QAEnabled": False,
            "QA": {},
            "QAPrompt": {},
            "AttentionPreprocessor": True,
        },
        "ProcTreeExtract": {
            "Enabled": True,
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "Prompt": {},
            "QAEnabled": False,
            "QA": {},
            "QAPrompt": {},
        },
        "HuntQueriesExtract": {
            "Enabled": True,
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "Prompt": {},
            "QAEnabled": False,
            "QA": {},
            "QAPrompt": {},
        },
        "SigmaAgent": {
            "Provider": "openai",
            "Model": "gpt-4",
            "Temperature": 0,
            "TopP": 0.9,
            "SimilarityThreshold": 0.5,
            "UseFullArticleContent": False,
            "Prompt": {},
        },
    }
    config = load_workflow_config(ui_ordered)
    legacy = config.to_legacy_response_dict()
    assert legacy["min_hunt_score"] == 85.0
    assert legacy["auto_trigger_hunt_score_threshold"] == 50.0


def test_config_row_to_preset_dict_includes_disabled_agents_from_agent_prompts():
    """_config_row_to_preset_dict derives extract_agent_settings.disabled_agents from config.agent_prompts.ExtractAgentSettings."""
    from src.web.routes.workflow_config import _config_row_to_preset_dict

    row = SimpleNamespace(
        junk_filter_threshold=0.8,
        ranking_threshold=6.0,
        similarity_threshold=0.5,
        agent_models={"RankAgent": "gpt-4"},
        qa_enabled={},
        sigma_fallback_enabled=False,
        osdetection_fallback_enabled=False,
        rank_agent_enabled=True,
        qa_max_retries=5,
        cmdline_attention_preprocessor_enabled=True,
        agent_prompts={
            "ExtractAgentSettings": {"disabled_agents": ["CmdlineExtract"]},
            "RankAgent": {"prompt": "", "instructions": ""},
        },
    )
    out = _config_row_to_preset_dict(row)
    assert out.get("extract_agent_settings") == {"disabled_agents": ["CmdlineExtract"]}
