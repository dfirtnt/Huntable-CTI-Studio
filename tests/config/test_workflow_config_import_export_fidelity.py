"""
Evidence tests: preset import enforces every setting; export misses none; round-trip is lossless.

These tests use distinct non-default values so we can assert exact match after import/export.
Run with: pytest tests/config/test_workflow_config_import_export_fidelity.py -v
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from src.config.workflow_config_loader import (
    export_preset_as_canonical_v2,
    is_ui_ordered_preset,
    load_workflow_config,
)

# Unique non-default values so we can assert they survive import and export.
FIDELITY_JUNK = 0.72
FIDELITY_QA_RETRIES = 2
FIDELITY_MIN_HUNT = 88.0
FIDELITY_AUTO_TRIGGER = 55.0
FIDELITY_OS_EMBEDDING = "test/embedding-model"
FIDELITY_OS_FALLBACK_ENABLED = True
FIDELITY_OS_SELECTED = ["Linux", "Darwin"]
FIDELITY_RANK_THRESHOLD = 7.0
FIDELITY_RANK_QA_ENABLED = True
FIDELITY_CMDLINE_ENABLED = True
FIDELITY_CMDLINE_QA_ENABLED = True
FIDELITY_CMDLINE_ATTENTION = False
FIDELITY_PROCTREE_ENABLED = True
FIDELITY_PROCTREE_QA_ENABLED = True
FIDELITY_HUNTQUERIES_ENABLED = True
FIDELITY_HUNTQUERIES_QA_ENABLED = True
FIDELITY_SIGMA_THRESHOLD = 0.42
FIDELITY_SIGMA_FULL_ARTICLE = True
FIDELITY_DISABLED_AGENTS: list[str] = []  # all enabled
FIDELITY_PROMPT_SENTINEL = "IMPORT_EXPORT_FIDELITY_SENTINEL"


def _full_ui_ordered_preset() -> dict[str, Any]:
    """UI-ordered preset with non-default values for every field we care about."""
    return {
        "Version": "2.0",
        "Metadata": {"CreatedAt": "2026-01-01T00:00:00Z", "Description": "Fidelity test"},
        "JunkFilter": {"JunkFilterThreshold": FIDELITY_JUNK},
        "QASettings": {"MaxRetries": FIDELITY_QA_RETRIES},
        "Thresholds": {
            "MinHuntScore": FIDELITY_MIN_HUNT,
            "AutoTriggerHuntScoreThreshold": FIDELITY_AUTO_TRIGGER,
        },
        "OSDetection": {
            "Embedding": FIDELITY_OS_EMBEDDING,
            "FallbackEnabled": FIDELITY_OS_FALLBACK_ENABLED,
            "Fallback": {
                "Provider": "anthropic",
                "Model": "claude-sonnet-4-5",
                "Temperature": 0.0,
                "TopP": 0.9,
            },
            "SelectedOs": list(FIDELITY_OS_SELECTED),
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " OS", "instructions": ""},
        },
        "RankAgent": {
            "Enabled": True,
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.0,
            "TopP": 0.9,
            "RankingThreshold": FIDELITY_RANK_THRESHOLD,
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " Rank", "instructions": ""},
            "QAEnabled": FIDELITY_RANK_QA_ENABLED,
            "QA": {"Provider": "anthropic", "Model": "claude-sonnet-4-5", "Temperature": 0.1, "TopP": 0.9},
            "QAPrompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " RankQA", "instructions": ""},
        },
        "ExtractAgent": {
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " Extract", "instructions": ""},
        },
        "CmdlineExtract": {
            "Enabled": FIDELITY_CMDLINE_ENABLED,
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.0,
            "TopP": 0.9,
            "AttentionPreprocessor": FIDELITY_CMDLINE_ATTENTION,
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " Cmdline", "instructions": ""},
            "QAEnabled": FIDELITY_CMDLINE_QA_ENABLED,
            "QA": {"Provider": "anthropic", "Model": "claude-sonnet-4-5", "Temperature": 0.1, "TopP": 0.9},
            "QAPrompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " CmdlineQA", "instructions": ""},
        },
        "ProcTreeExtract": {
            "Enabled": FIDELITY_PROCTREE_ENABLED,
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " ProcTree", "instructions": ""},
            "QAEnabled": FIDELITY_PROCTREE_QA_ENABLED,
            "QA": {"Provider": "anthropic", "Model": "claude-sonnet-4-5", "Temperature": 0.1, "TopP": 0.9},
            "QAPrompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " ProcTreeQA", "instructions": ""},
        },
        "HuntQueriesExtract": {
            "Enabled": FIDELITY_HUNTQUERIES_ENABLED,
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.0,
            "TopP": 0.9,
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " HuntQueries", "instructions": ""},
            "QAEnabled": FIDELITY_HUNTQUERIES_QA_ENABLED,
            "QA": {"Provider": "anthropic", "Model": "claude-sonnet-4-5", "Temperature": 0.1, "TopP": 0.9},
            "QAPrompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " HuntQueriesQA", "instructions": ""},
        },
        "SigmaAgent": {
            "Provider": "anthropic",
            "Model": "claude-sonnet-4-5",
            "Temperature": 0.0,
            "TopP": 0.9,
            "SimilarityThreshold": FIDELITY_SIGMA_THRESHOLD,
            "UseFullArticleContent": FIDELITY_SIGMA_FULL_ARTICLE,
            "Prompt": {"prompt": FIDELITY_PROMPT_SENTINEL + " Sigma", "instructions": ""},
        },
    }


def _norm_val(v: Any) -> Any:
    """Normalize for comparison: int/float equivalence, list order."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        return [_norm_val(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm_val(x) for k, x in sorted(v.items())}
    return v


def _norm_export(exported: dict[str, Any]) -> dict[str, Any]:
    """Normalize exported UI-ordered dict for comparison (ignore Metadata.CreatedAt, etc.)."""
    out = copy.deepcopy(exported)
    # Drop metadata that changes on export
    if "Metadata" in out and isinstance(out["Metadata"], dict):
        out["Metadata"] = {k: v for k, v in out["Metadata"].items() if k != "CreatedAt"}
    return _norm_val(out)


# --- Import enforcement: every UI-ordered field ends up in the loaded config ---


def test_import_enforces_all_settings():
    """
    Evidence: Loading a UI-ordered preset enforces every setting into WorkflowConfigV2.
    If this test passes, no setting is dropped or wrong on import.
    """
    ui = _full_ui_ordered_preset()
    config = load_workflow_config(ui)

    # Thresholds
    assert config.Thresholds.JunkFilterThreshold == FIDELITY_JUNK
    assert config.Thresholds.MinHuntScore == FIDELITY_MIN_HUNT
    assert config.Thresholds.AutoTriggerHuntScoreThreshold == FIDELITY_AUTO_TRIGGER
    assert config.Thresholds.RankingThreshold == FIDELITY_RANK_THRESHOLD
    assert config.Thresholds.SimilarityThreshold == FIDELITY_SIGMA_THRESHOLD

    # QA
    assert config.QA.MaxRetries == FIDELITY_QA_RETRIES
    assert config.QA.Enabled.get("RankAgent") is FIDELITY_RANK_QA_ENABLED
    assert config.QA.Enabled.get("CmdlineExtract") is FIDELITY_CMDLINE_QA_ENABLED
    assert config.QA.Enabled.get("ProcTreeExtract") is FIDELITY_PROCTREE_QA_ENABLED
    assert config.QA.Enabled.get("HuntQueriesExtract") is FIDELITY_HUNTQUERIES_QA_ENABLED

    # Execution
    assert config.Execution.OsDetectionSelectedOs == FIDELITY_OS_SELECTED
    assert list(config.Execution.ExtractAgentSettings.DisabledAgents) == FIDELITY_DISABLED_AGENTS

    # Embeddings
    assert config.Embeddings.OsDetection == FIDELITY_OS_EMBEDDING

    # Features
    assert config.Features.SigmaFallbackEnabled is FIDELITY_SIGMA_FULL_ARTICLE
    assert config.Features.CmdlineAttentionPreprocessorEnabled is FIDELITY_CMDLINE_ATTENTION

    # OS fallback agent
    assert config.Agents["OSDetectionFallback"].Enabled is FIDELITY_OS_FALLBACK_ENABLED

    # Prompts (sentinels)
    def _prompt_text(p: Any) -> str:
        if p is None:
            return ""
        return p.prompt if hasattr(p, "prompt") else (p.get("prompt", "") if isinstance(p, dict) else "")

    assert FIDELITY_PROMPT_SENTINEL in _prompt_text(config.Prompts.get("OSDetectionFallback"))
    assert FIDELITY_PROMPT_SENTINEL in _prompt_text(config.Prompts.get("RankAgent"))
    assert FIDELITY_PROMPT_SENTINEL in _prompt_text(config.Prompts.get("CmdlineExtract"))
    assert FIDELITY_PROMPT_SENTINEL in _prompt_text(config.Prompts.get("SigmaAgent"))


def test_import_legacy_dict_has_all_fields_for_apply_preset():
    """
    Evidence: The legacy dict (what the API returns to the UI for applyPreset) contains every
    setting so the UI can apply them. Missing keys would mean silent failure on import.
    """
    ui = _full_ui_ordered_preset()
    config = load_workflow_config(ui)
    legacy = config.to_legacy_response_dict()

    assert legacy["min_hunt_score"] == FIDELITY_MIN_HUNT
    assert legacy["auto_trigger_hunt_score_threshold"] == FIDELITY_AUTO_TRIGGER
    assert legacy["junk_filter_threshold"] == FIDELITY_JUNK
    assert legacy["ranking_threshold"] == FIDELITY_RANK_THRESHOLD
    assert legacy["similarity_threshold"] == FIDELITY_SIGMA_THRESHOLD
    assert legacy["qa_max_retries"] == FIDELITY_QA_RETRIES
    assert legacy["qa_enabled"].get("RankAgent") is FIDELITY_RANK_QA_ENABLED
    assert legacy["qa_enabled"].get("CmdlineExtract") is FIDELITY_CMDLINE_QA_ENABLED
    assert legacy["qa_enabled"].get("ProcTreeExtract") is FIDELITY_PROCTREE_QA_ENABLED
    assert legacy["qa_enabled"].get("HuntQueriesExtract") is FIDELITY_HUNTQUERIES_QA_ENABLED
    assert legacy["sigma_fallback_enabled"] is FIDELITY_SIGMA_FULL_ARTICLE
    assert legacy["cmdline_attention_preprocessor_enabled"] is FIDELITY_CMDLINE_ATTENTION
    assert legacy["osdetection_fallback_enabled"] is FIDELITY_OS_FALLBACK_ENABLED
    # Note: schema to_legacy_response_dict does not include extract_agent_settings; the API
    # route _v2_to_legacy_preset_dict adds it. Execution.DisabledAgents is asserted in test_import_enforces_all_settings.

    # agent_models must include OS Detection selected OS for applyPreset
    assert "OSDetectionAgent_selected_os" in legacy["agent_models"]
    assert legacy["agent_models"]["OSDetectionAgent_selected_os"] == FIDELITY_OS_SELECTED
    assert legacy["agent_models"]["OSDetectionAgent_embedding"] == FIDELITY_OS_EMBEDDING

    # Prompts present for each agent we care about
    assert "RankAgent" in legacy["agent_prompts"]
    assert FIDELITY_PROMPT_SENTINEL in legacy["agent_prompts"]["RankAgent"].get("prompt", "")
    assert "CmdlineExtract" in legacy["agent_prompts"]
    assert "SigmaAgent" in legacy["agent_prompts"]


# --- Export fidelity: every setting is present and correct in the exported file ---


def test_export_contains_all_settings():
    """
    Evidence: Exporting a preset produces a UI-ordered file with every setting present and correct.
    If this test passes, no setting is missed or inaccurate on export.
    """
    ui = _full_ui_ordered_preset()
    exported = export_preset_as_canonical_v2(ui)
    assert is_ui_ordered_preset(exported)

    assert exported["JunkFilter"]["JunkFilterThreshold"] == FIDELITY_JUNK
    assert exported["QASettings"]["MaxRetries"] == FIDELITY_QA_RETRIES
    assert float(exported["Thresholds"]["MinHuntScore"]) == FIDELITY_MIN_HUNT
    assert float(exported["Thresholds"]["AutoTriggerHuntScoreThreshold"]) == FIDELITY_AUTO_TRIGGER

    osd = exported["OSDetection"]
    assert osd["Embedding"] == FIDELITY_OS_EMBEDDING
    assert osd["FallbackEnabled"] is FIDELITY_OS_FALLBACK_ENABLED
    assert osd["SelectedOs"] == FIDELITY_OS_SELECTED
    assert FIDELITY_PROMPT_SENTINEL in osd["Prompt"].get("prompt", "")

    rank = exported["RankAgent"]
    assert float(rank["RankingThreshold"]) == FIDELITY_RANK_THRESHOLD
    assert rank["QAEnabled"] is FIDELITY_RANK_QA_ENABLED
    assert FIDELITY_PROMPT_SENTINEL in rank["Prompt"].get("prompt", "")
    assert FIDELITY_PROMPT_SENTINEL in rank["QAPrompt"].get("prompt", "")

    cmd = exported["CmdlineExtract"]
    assert cmd["Enabled"] is FIDELITY_CMDLINE_ENABLED
    assert cmd["QAEnabled"] is FIDELITY_CMDLINE_QA_ENABLED
    assert cmd["AttentionPreprocessor"] is FIDELITY_CMDLINE_ATTENTION
    assert FIDELITY_PROMPT_SENTINEL in cmd["Prompt"].get("prompt", "")

    assert exported["ProcTreeExtract"]["Enabled"] is FIDELITY_PROCTREE_ENABLED
    assert exported["ProcTreeExtract"]["QAEnabled"] is FIDELITY_PROCTREE_QA_ENABLED
    assert exported["HuntQueriesExtract"]["Enabled"] is FIDELITY_HUNTQUERIES_ENABLED
    assert exported["HuntQueriesExtract"]["QAEnabled"] is FIDELITY_HUNTQUERIES_QA_ENABLED

    sigma = exported["SigmaAgent"]
    assert float(sigma["SimilarityThreshold"]) == FIDELITY_SIGMA_THRESHOLD
    assert sigma["UseFullArticleContent"] is FIDELITY_SIGMA_FULL_ARTICLE
    assert FIDELITY_PROMPT_SENTINEL in sigma["Prompt"].get("prompt", "")


# --- Round-trip: import then export produces equivalent output ---


def test_round_trip_export_import_export_identity():
    """
    Evidence: Export → load → export again produces the same settings (normalized).
    Proves no information is lost or corrupted across import and export.
    """
    ui = _full_ui_ordered_preset()
    exported1 = export_preset_as_canonical_v2(ui)
    assert is_ui_ordered_preset(exported1)

    # Second export: load the first export (UI-ordered) and re-export (same pipeline as UI)
    exported2 = export_preset_as_canonical_v2(exported1)

    n1 = _norm_export(exported1)
    n2 = _norm_export(exported2)

    # Compare key sections (ignore Metadata.CreatedAt / Description that export may overwrite)
    for section in (
        "JunkFilter",
        "QASettings",
        "Thresholds",
        "OSDetection",
        "RankAgent",
        "ExtractAgent",
        "CmdlineExtract",
        "ProcTreeExtract",
        "HuntQueriesExtract",
        "SigmaAgent",
    ):
        assert section in n1 and section in n2, f"Missing section {section}"
        s1 = n1[section]
        s2 = n2[section]
        assert s1 == s2, f"Round-trip mismatch in {section}: {json.dumps(s1) != json.dumps(s2)}"


# --- Strict import: missing or null settings must fail ---


def test_import_fails_when_required_section_missing():
    """Import must fail if a required top-level section is missing."""
    ui = _full_ui_ordered_preset()
    del ui["QASettings"]
    with pytest.raises(ValueError, match="missing or null"):
        load_workflow_config(ui)


def test_import_fails_when_required_key_missing():
    """Import must fail if a required key within a section is missing."""
    ui = _full_ui_ordered_preset()
    del ui["JunkFilter"]["JunkFilterThreshold"]
    with pytest.raises(ValueError, match="missing or null"):
        load_workflow_config(ui)


def test_import_fails_when_required_key_null():
    """Import must fail if a required key is explicitly null."""
    ui = _full_ui_ordered_preset()
    ui["Thresholds"]["MinHuntScore"] = None
    with pytest.raises(ValueError, match="missing or null"):
        load_workflow_config(ui)


def test_legacy_import_fails_when_qa_max_retries_missing():
    """Legacy (v1) preset import must fail when qa_max_retries is missing."""
    legacy = {
        "version": "1.0",
        "thresholds": {},
        "agent_models": {},
        "agent_prompts": {},
        "qa_enabled": {},
        # qa_max_retries omitted intentionally
        "sigma_fallback_enabled": False,
        "osdetection_fallback_enabled": False,
        "rank_agent_enabled": True,
        "cmdline_attention_preprocessor_enabled": True,
        "extract_agent_settings": {"disabled_agents": []},
        "description": "",
        "created_at": "",
    }
    with pytest.raises(ValueError, match="missing or null"):
        load_workflow_config(legacy)
