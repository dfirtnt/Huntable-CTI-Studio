"""
Load, validate, and migrate workflow config.

Entry point: load_workflow_config(raw) -> WorkflowConfigV2.
Always migrates v1 to v2 at load time. Use flatten_for_llm_service() for legacy consumers.
Export: export_preset_as_canonical_v2() returns strict v2 dict for file download.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import (
    AgentConfig,
    EmbeddingsConfig,
    ExecutionConfig,
    FeatureFlags,
    MetadataConfig,
    PromptConfig,
    QAConfig,
    ThresholdConfig,
    WorkflowConfigV2,
)

logger = logging.getLogger(__name__)


def _normalize_raw_from_db(row: Any) -> dict[str, Any]:
    """Build a v1-style dict from AgenticWorkflowConfigTable row."""
    if row is None:
        return _empty_v1()
    raw: dict[str, Any] = {
        "version": "1.0",
        "min_hunt_score": getattr(row, "min_hunt_score", 97.0),
        "ranking_threshold": getattr(row, "ranking_threshold", 6.0),
        "similarity_threshold": getattr(row, "similarity_threshold", 0.5),
        "junk_filter_threshold": getattr(row, "junk_filter_threshold", 0.8),
        "auto_trigger_hunt_score_threshold": getattr(row, "auto_trigger_hunt_score_threshold", 60.0),
        "agent_models": getattr(row, "agent_models", None) or {},
        "agent_prompts": getattr(row, "agent_prompts", None) or {},
        "qa_enabled": getattr(row, "qa_enabled", None) or {},
        "qa_max_retries": getattr(row, "qa_max_retries", 5),
        "sigma_fallback_enabled": getattr(row, "sigma_fallback_enabled", False),
        "osdetection_fallback_enabled": getattr(row, "osdetection_fallback_enabled", False),
        "rank_agent_enabled": getattr(row, "rank_agent_enabled", True),
        "cmdline_attention_preprocessor_enabled": getattr(row, "cmdline_attention_preprocessor_enabled", True),
        "extract_agent_settings": getattr(row, "extract_agent_settings", None) or {"disabled_agents": []},
        "description": getattr(row, "description", None) or "",
        "created_at": str(getattr(row, "created_at", "")) if getattr(row, "created_at", None) else "",
    }
    if hasattr(row, "agent_models") and row.agent_models:
        raw["agent_models"] = dict(row.agent_models)
        raw["OSDetectionAgent_selected_os"] = (row.agent_models or {}).get("OSDetectionAgent_selected_os")
    return raw


def _empty_v1() -> dict[str, Any]:
    return {
        "version": "1.0",
        "thresholds": {},
        "agent_models": {},
        "agent_prompts": {},
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


def load_workflow_config(raw: dict[str, Any] | Any) -> WorkflowConfigV2:
    """
    Load and validate workflow config. Migrates v1 to v2 automatically.
    raw: either a dict (from JSON/preset or API) or an AgenticWorkflowConfigTable row.
    Raises ValidationError if migrated config is invalid.
    """
    if not isinstance(raw, dict):
        raw = _normalize_raw_from_db(raw)
    migrated = migrate_v1_to_v2(raw)
    return WorkflowConfigV2.model_validate(migrated)


def config_row_to_v2_dict(row: Any) -> dict[str, Any]:
    """
    Convert DB config row to v2 dict (PascalCase) without Pydantic.
    Use when you need a serializable v2 structure for API response.
    """
    raw = _normalize_raw_from_db(row)
    return migrate_v1_to_v2(raw)


def config_row_to_flat_agent_models(row: Any) -> dict[str, Any]:
    """
    Convert DB config row to flat agent_models dict for LLMService and other legacy consumers.
    """
    config = load_workflow_config(row)
    return config.flatten_for_llm_service()


def export_preset_as_canonical_v2(raw: dict[str, Any] | Any) -> dict[str, Any]:
    """
    Load preset (v1 or v2), enforce metadata, re-validate, and return canonical v2 dict for export.
    - Populates Metadata.CreatedAt (UTC ISO8601) if empty
    - Populates Metadata.Description if empty (default "Exported preset")
    - Re-validates with WorkflowConfigV2 after round-trip; aborts (raises ValidationError) if invalid.
    """
    config = load_workflow_config(raw)
    # Populate metadata for export
    if not config.Metadata.CreatedAt:
        config.Metadata.CreatedAt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not config.Metadata.Description:
        config.Metadata.Description = "Exported preset"
    dumped = config.model_dump(mode="json")
    # Integrity check: round-trip must validate
    WorkflowConfigV2.model_validate(dumped)
    return dumped
