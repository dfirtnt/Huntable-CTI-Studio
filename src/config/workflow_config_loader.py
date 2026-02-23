"""
Load, validate, and migrate workflow config.

Entry point: load_workflow_config(raw) -> WorkflowConfigV2.
Always migrates v1 to v2 at load time. Use flatten_for_llm_service() for legacy consumers.
Export: export_preset_as_canonical_v2() returns strict v2 dict for file download.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import (
    WorkflowConfigV2,
)

logger = logging.getLogger(__name__)

# Canonical agent group order (for tests and other consumers that expect group ordering).
CORE_AGENTS = ["RankAgent", "ExtractAgent", "SigmaAgent"]
EXTRACT_AGENTS = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract"]
QA_AGENTS = ["RankAgentQA", "CmdlineQA", "ProcTreeQA", "HuntQueriesQA"]
UTILITY_AGENTS = ["OSDetectionFallback"]

# UI top-to-bottom order for export: each agent grouped with its QA agent (e.g. RankAgent then RankAgentQA).
# So sections read as: OS Detection → Rank (agent + QA) → Extract fallback → CmdlineExtract + QA → ProcTree + QA → HuntQueries + QA → Sigma.
AGENTS_ORDER_UI = [
    "OSDetectionFallback",
    "RankAgent",
    "RankAgentQA",
    "ExtractAgent",
    "CmdlineExtract",
    "CmdlineQA",
    "ProcTreeExtract",
    "ProcTreeQA",
    "HuntQueriesExtract",
    "HuntQueriesQA",
    "SigmaAgent",
]

# V2 top-level section order for export (matches UI flow).
V2_TOP_LEVEL_ORDER = [
    "Version",
    "Metadata",
    "Thresholds",
    "QA",
    "Execution",
    "Embeddings",
    "Agents",
    "Features",
    "Prompts",
]

# Thresholds key order: Junk first (UI), then ranking/similarity, then hunt score fields.
THRESHOLDS_ORDER_UI = [
    "JunkFilterThreshold",
    "RankingThreshold",
    "SimilarityThreshold",
    "MinHuntScore",
    "AutoTriggerHuntScoreThreshold",
]

# UI-ordered export: one block per UI section, top-to-bottom order of configurable elements.
# Each block contains that section's settings + prompt + QA (where applicable).
UI_ORDERED_TOP_LEVEL_ORDER = [
    "Version",
    "Metadata",
    "JunkFilter",
    "QASettings",
    "Thresholds",  # only MinHuntScore, AutoTriggerHuntScoreThreshold (not per-panel)
    "OSDetection",
    "RankAgent",
    "ExtractAgent",
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "SigmaAgent",
]

# Required top-level keys for legacy (v1) preset import. Import fails if any are missing or null.
_LEGACY_REQUIRED_KEYS = [
    "version",
    "thresholds",
    "agent_models",
    "agent_prompts",
    "qa_enabled",
    "qa_max_retries",
    "sigma_fallback_enabled",
    "osdetection_fallback_enabled",
    "rank_agent_enabled",
    "cmdline_attention_preprocessor_enabled",
    "extract_agent_settings",
    "description",
    "created_at",
]

# Required sections and keys for UI-ordered preset import. Import fails if any are missing or null.
_UI_ORDERED_REQUIRED: list[tuple[str, list[str]]] = [
    ("JunkFilter", ["JunkFilterThreshold"]),
    ("QASettings", ["MaxRetries"]),
    ("Thresholds", ["MinHuntScore", "AutoTriggerHuntScoreThreshold"]),
    ("OSDetection", ["Embedding", "FallbackEnabled", "Fallback", "SelectedOs", "Prompt"]),
    (
        "RankAgent",
        [
            "Enabled",
            "Provider",
            "Model",
            "Temperature",
            "TopP",
            "RankingThreshold",
            "Prompt",
            "QAEnabled",
            "QA",
            "QAPrompt",
        ],
    ),
    ("ExtractAgent", ["Provider", "Model", "Temperature", "TopP", "Prompt"]),
    (
        "CmdlineExtract",
        [
            "Enabled",
            "Provider",
            "Model",
            "Temperature",
            "TopP",
            "Prompt",
            "QAEnabled",
            "QA",
            "QAPrompt",
            "AttentionPreprocessor",
        ],
    ),
    (
        "ProcTreeExtract",
        ["Enabled", "Provider", "Model", "Temperature", "TopP", "Prompt", "QAEnabled", "QA", "QAPrompt"],
    ),
    (
        "HuntQueriesExtract",
        ["Enabled", "Provider", "Model", "Temperature", "TopP", "Prompt", "QAEnabled", "QA", "QAPrompt"],
    ),
    (
        "SigmaAgent",
        ["Provider", "Model", "Temperature", "TopP", "SimilarityThreshold", "UseFullArticleContent", "Prompt"],
    ),
]


def _agent_cfg(agents: dict, name: str) -> dict[str, Any]:
    a = (agents or {}).get(name) or {}
    if not isinstance(a, dict):
        a = {}
    return {
        "Provider": a.get("Provider", "lmstudio"),
        "Model": a.get("Model", ""),
        "Temperature": float(a.get("Temperature", 0.0)),
        "TopP": float(a.get("TopP", 0.9)),
        "Enabled": bool(a.get("Enabled", True)),
    }


def _prompt_cfg(prompts: dict, name: str) -> dict[str, Any]:
    p = (prompts or {}).get(name) or {}
    if not isinstance(p, dict):
        p = {}
    return {"prompt": p.get("prompt", ""), "instructions": p.get("instructions", "")}


def v2_to_ui_ordered_export(v2: dict[str, Any]) -> dict[str, Any]:
    """
    Convert v2 dict to UI-ordered export: one block per UI section so JSON order
    matches the workflow config page (Junk → QA Settings → OS Detection → Rank → Extract → Cmdline → ProcTree → HuntQueries → Sigma).
    Each block contains that section's settings, prompt, and QA where applicable.
    """
    th = v2.get("Thresholds") or {}
    qa = v2.get("QA") or {}
    qa_enabled = qa.get("Enabled") or {}
    agents = v2.get("Agents") or {}
    prompts = v2.get("Prompts") or {}
    emb = v2.get("Embeddings") or {}
    exe = v2.get("Execution") or {}
    exe_extract = exe.get("ExtractAgentSettings") or {}
    disabled = exe_extract.get("DisabledAgents") or []
    features = v2.get("Features") or {}

    out: dict[str, Any] = {}
    if "Version" in v2:
        out["Version"] = v2["Version"]
    if "Metadata" in v2:
        out["Metadata"] = v2["Metadata"]

    out["JunkFilter"] = {"JunkFilterThreshold": float(th.get("JunkFilterThreshold", 0.8))}
    out["QASettings"] = {"MaxRetries": int(qa.get("MaxRetries", 5))}
    out["Thresholds"] = {
        "MinHuntScore": float(th.get("MinHuntScore", 97.0)),
        "AutoTriggerHuntScoreThreshold": float(th.get("AutoTriggerHuntScoreThreshold", 60.0)),
    }

    os_fb = _agent_cfg(agents, "OSDetectionFallback")
    out["OSDetection"] = {
        "Embedding": emb.get("OsDetection", "ibm-research/CTI-BERT"),
        "FallbackEnabled": os_fb["Enabled"],
        "Fallback": {
            "Provider": os_fb["Provider"],
            "Model": os_fb["Model"],
            "Temperature": os_fb["Temperature"],
            "TopP": os_fb["TopP"],
        },
        "SelectedOs": exe.get("OsDetectionSelectedOs") or ["Windows"],
        "Prompt": _prompt_cfg(prompts, "OSDetectionFallback"),
    }

    rank = _agent_cfg(agents, "RankAgent")
    rank_qa = _agent_cfg(agents, "RankAgentQA")
    out["RankAgent"] = {
        "Enabled": rank["Enabled"],
        "Provider": rank["Provider"],
        "Model": rank["Model"],
        "Temperature": rank["Temperature"],
        "TopP": rank["TopP"],
        "RankingThreshold": float(th.get("RankingThreshold", 6.0)),
        "Prompt": _prompt_cfg(prompts, "RankAgent"),
        "QAEnabled": qa_enabled.get("RankAgent", False),
        "QA": {
            "Provider": rank_qa["Provider"],
            "Model": rank_qa["Model"],
            "Temperature": rank_qa["Temperature"],
            "TopP": rank_qa["TopP"],
        },
        "QAPrompt": _prompt_cfg(prompts, "RankAgentQA"),
    }

    extract = _agent_cfg(agents, "ExtractAgent")
    out["ExtractAgent"] = {
        "Provider": extract["Provider"],
        "Model": extract["Model"],
        "Temperature": extract["Temperature"],
        "TopP": extract["TopP"],
        "Prompt": _prompt_cfg(prompts, "ExtractAgent"),
    }

    for base, qa_name in [
        ("CmdlineExtract", "CmdlineQA"),
        ("ProcTreeExtract", "ProcTreeQA"),
        ("HuntQueriesExtract", "HuntQueriesQA"),
    ]:
        cfg = _agent_cfg(agents, base)
        qa_cfg = _agent_cfg(agents, qa_name)
        enabled = base not in disabled
        block_dict: dict[str, Any] = {
            "Enabled": enabled,
            "Provider": cfg["Provider"],
            "Model": cfg["Model"],
            "Temperature": cfg["Temperature"],
            "TopP": cfg["TopP"],
            "Prompt": _prompt_cfg(prompts, base),
            "QAEnabled": qa_enabled.get(base, False),
            "QA": {
                "Provider": qa_cfg["Provider"],
                "Model": qa_cfg["Model"],
                "Temperature": qa_cfg["Temperature"],
                "TopP": qa_cfg["TopP"],
            },
            "QAPrompt": _prompt_cfg(prompts, qa_name),
        }
        if base == "CmdlineExtract":
            block_dict["AttentionPreprocessor"] = features.get("CmdlineAttentionPreprocessorEnabled", True)
        out[base] = block_dict

    sigma = _agent_cfg(agents, "SigmaAgent")
    out["SigmaAgent"] = {
        "Provider": sigma["Provider"],
        "Model": sigma["Model"],
        "Temperature": sigma["Temperature"],
        "TopP": sigma["TopP"],
        "SimilarityThreshold": float(th.get("SimilarityThreshold", 0.5)),
        "UseFullArticleContent": features.get("SigmaFallbackEnabled", False),
        "Prompt": _prompt_cfg(prompts, "SigmaAgent"),
    }

    # Emit keys in UI order
    ordered: dict[str, Any] = {}
    for k in UI_ORDERED_TOP_LEVEL_ORDER:
        if k in out:
            ordered[k] = out[k]
    for k, v in out.items():
        if k not in ordered:
            ordered[k] = v
    return ordered


def is_ui_ordered_preset(preset: dict[str, Any]) -> bool:
    """True if preset is in UI-ordered export format (per-section blocks)."""
    if not isinstance(preset, dict):
        return False
    if "RankAgent" in preset and isinstance(preset.get("RankAgent"), dict):
        r = preset["RankAgent"]
        if "RankingThreshold" in r and "Prompt" in r and ("Provider" in r or "Model" in r):
            return True
    if "JunkFilter" in preset and "QASettings" in preset and "OSDetection" in preset:
        return True
    return False


def _is_legacy_v1_shape(raw: dict[str, Any]) -> bool:
    """True if preset looks like legacy v1 (snake_case keys like agent_models, qa_max_retries)."""
    if raw.get("Version") == "2.0" and "Agents" in raw and "Thresholds" in raw:
        return False
    return (
        raw.get("version") == "1.0" or raw.get("Version") == "1.0" or "agent_models" in raw or "qa_max_retries" in raw
    )


def validate_legacy_preset_strict(raw: dict[str, Any]) -> None:
    """
    Require all legacy (v1) preset keys to be present and non-null.
    Raises ValueError if any required key is missing or value is None.
    """
    if not isinstance(raw, dict):
        raise ValueError("Preset must be a JSON object")
    missing: list[str] = []
    for key in _LEGACY_REQUIRED_KEYS:
        if key == "version":
            if raw.get("version") is None and raw.get("Version") is None:
                missing.append("version")
            continue
        if key not in raw:
            missing.append(key)
        elif raw[key] is None:
            missing.append(f"{key} (null)")
    if missing:
        raise ValueError("Preset import requires every setting to be set; missing or null: " + ", ".join(missing))


def validate_ui_ordered_preset_strict(ui: dict[str, Any]) -> None:
    """
    Require all UI-ordered sections and their required keys to be present and non-null.
    Raises ValueError if any section or key is missing or value is None.
    """
    if not isinstance(ui, dict):
        raise ValueError("Preset must be a JSON object")
    missing: list[str] = []
    for section, keys in _UI_ORDERED_REQUIRED:
        block = ui.get(section)
        if block is None:
            missing.append(section)
            continue
        if not isinstance(block, dict):
            missing.append(f"{section} (not an object)")
            continue
        for key in keys:
            if key not in block:
                missing.append(f"{section}.{key}")
            elif block[key] is None:
                missing.append(f"{section}.{key} (null)")
    if missing:
        raise ValueError("Preset import requires every setting to be set; missing or null: " + ", ".join(missing))


def _default_agent(provider: str = "lmstudio", model: str = "", enabled: bool = False) -> dict[str, Any]:
    return {"Provider": provider, "Model": model, "Temperature": 0.0, "TopP": 0.9, "Enabled": enabled}


def ui_ordered_to_v2(ui: dict[str, Any]) -> dict[str, Any]:
    """Convert UI-ordered export back to v2 for load_workflow_config."""
    th_extra = ui.get("Thresholds") or {}
    junk = ui.get("JunkFilter") or {}
    qas = ui.get("QASettings") or {}
    osd = ui.get("OSDetection") or {}
    rank = ui.get("RankAgent") or {}
    extract = ui.get("ExtractAgent") or {}
    sigma = ui.get("SigmaAgent") or {}

    agents: dict[str, Any] = {}
    prompts: dict[str, Any] = {}
    qa_enabled: dict[str, bool] = {}
    disabled_agents: list[str] = []

    def add_agent(
        name: str,
        cfg: dict,
        prompt: dict | None = None,
        qa_name: str | None = None,
        qa_cfg: dict | None = None,
        qa_prompt: dict | None = None,
    ):
        agents[name] = {
            "Provider": cfg.get("Provider", "lmstudio"),
            "Model": cfg.get("Model", ""),
            "Temperature": float(cfg.get("Temperature", 0.0)),
            "TopP": float(cfg.get("TopP", 0.9)),
            "Enabled": bool(cfg.get("Enabled", True)),
        }
        if prompt is not None:
            prompts[name] = prompt
        if qa_name and qa_cfg is not None:
            agents[qa_name] = {
                "Provider": qa_cfg.get("Provider", "lmstudio"),
                "Model": qa_cfg.get("Model", ""),
                "Temperature": float(qa_cfg.get("Temperature", 0.0)),
                "TopP": float(qa_cfg.get("TopP", 0.9)),
                "Enabled": True,
            }
            if qa_prompt is not None:
                prompts[qa_name] = qa_prompt

    fallback = osd.get("Fallback") or {}
    agents["OSDetectionFallback"] = {
        "Provider": fallback.get("Provider", "lmstudio"),
        "Model": fallback.get("Model", ""),
        "Temperature": float(fallback.get("Temperature", 0.0)),
        "TopP": float(fallback.get("TopP", 0.9)),
        "Enabled": bool(osd.get("FallbackEnabled", False)),
    }
    prompts["OSDetectionFallback"] = osd.get("Prompt") or {"prompt": "", "instructions": ""}

    add_agent("RankAgent", rank, rank.get("Prompt"), "RankAgentQA", rank.get("QA"), rank.get("QAPrompt"))
    qa_enabled["RankAgent"] = bool(rank.get("QAEnabled", False))

    add_agent("ExtractAgent", extract, extract.get("Prompt") or {"prompt": "", "instructions": ""})

    for base, qa_name in [
        ("CmdlineExtract", "CmdlineQA"),
        ("ProcTreeExtract", "ProcTreeQA"),
        ("HuntQueriesExtract", "HuntQueriesQA"),
    ]:
        block = ui.get(base) or {}
        if not block:
            agents[base] = _default_agent(enabled=False)
            agents[qa_name] = _default_agent(enabled=True)
            prompts[base] = {"prompt": "", "instructions": ""}
            prompts[qa_name] = {"prompt": "", "instructions": ""}
            qa_enabled[base] = False
            continue
        enabled = block.get("Enabled", True)
        if not enabled:
            disabled_agents.append(base)
        add_agent(base, block, block.get("Prompt"), qa_name, block.get("QA"), block.get("QAPrompt"))
        qa_enabled[base] = bool(block.get("QAEnabled", False))

    add_agent("SigmaAgent", sigma, sigma.get("Prompt") or {"prompt": "", "instructions": ""})

    thresholds = {
        "JunkFilterThreshold": junk.get("JunkFilterThreshold", 0.8),
        "RankingThreshold": rank.get("RankingThreshold", 6.0),
        "SimilarityThreshold": sigma.get("SimilarityThreshold", 0.5),
        "MinHuntScore": th_extra.get("MinHuntScore", 97.0),
        "AutoTriggerHuntScoreThreshold": th_extra.get("AutoTriggerHuntScoreThreshold", 60.0),
    }
    embeddings = {
        "OsDetection": osd.get("Embedding", "ibm-research/CTI-BERT"),
        "Sigma": (ui.get("Embeddings") or {}).get("Sigma", "ibm-research/CTI-BERT"),
    }
    if "Embeddings" not in ui and "SigmaAgent" in ui:
        embeddings["Sigma"] = "ibm-research/CTI-BERT"

    return {
        "Version": ui.get("Version", "2.0"),
        "Metadata": ui.get("Metadata", {}),
        "Thresholds": thresholds,
        "QA": {"Enabled": qa_enabled, "MaxRetries": qas.get("MaxRetries", 5)},
        "Execution": {
            "ExtractAgentSettings": {"DisabledAgents": disabled_agents},
            "OsDetectionSelectedOs": osd.get("SelectedOs") or ["Windows"],
        },
        "Embeddings": embeddings,
        "Agents": agents,
        "Features": {
            "SigmaFallbackEnabled": sigma.get("UseFullArticleContent", False),
            "CmdlineAttentionPreprocessorEnabled": (ui.get("CmdlineExtract") or {}).get("AttentionPreprocessor", True),
        },
        "Prompts": prompts,
    }


def order_agents_for_export(agents_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Return a new dict with agents ordered to match UI top-to-bottom.
    Uses AGENTS_ORDER_UI; unknown agents are appended last in sorted order.
    Does NOT modify input.
    """
    ordered: dict[str, Any] = {}
    for name in AGENTS_ORDER_UI:
        if name in agents_dict:
            ordered[name] = agents_dict[name]
    remaining = sorted(k for k in agents_dict if k not in ordered)
    for name in remaining:
        ordered[name] = agents_dict[name]
    return ordered


def _build_v2_export_ordered(dumped: dict[str, Any]) -> dict[str, Any]:
    """
    Build a v2 dict with keys in canonical UI order for export.
    Preserves key order in JSON (Python 3.7+ dict insertion order).
    """
    thresholds = dumped.get("Thresholds") or {}
    ordered_thresholds: dict[str, Any] = {}
    for k in THRESHOLDS_ORDER_UI:
        if k in thresholds:
            ordered_thresholds[k] = thresholds[k]
    for k, v in thresholds.items():
        if k not in ordered_thresholds:
            ordered_thresholds[k] = v

    agents_order = list(dumped.get("Agents") or {})
    prompts = dumped.get("Prompts") or {}
    ordered_prompts: dict[str, Any] = {name: prompts[name] for name in agents_order if name in prompts}
    for k, v in prompts.items():
        if k not in ordered_prompts:
            ordered_prompts[k] = v

    qa = dumped.get("QA") or {}
    qa_enabled = qa.get("Enabled") or {}
    ordered_qa_enabled: dict[str, Any] = {name: qa_enabled[name] for name in AGENTS_ORDER_UI if name in qa_enabled}
    for k, v in qa_enabled.items():
        if k not in ordered_qa_enabled:
            ordered_qa_enabled[k] = v
    ordered_qa: dict[str, Any] = {"Enabled": ordered_qa_enabled, "MaxRetries": qa.get("MaxRetries", 5)}

    result: dict[str, Any] = {}
    for key in V2_TOP_LEVEL_ORDER:
        if key == "Thresholds":
            result["Thresholds"] = ordered_thresholds
        elif key == "Prompts":
            result["Prompts"] = ordered_prompts
        elif key == "QA":
            result["QA"] = ordered_qa
        elif key in dumped:
            result[key] = dumped[key]
    for key, value in dumped.items():
        if key not in result:
            result[key] = value
    return result


def _normalize_raw_from_db(row: Any) -> dict[str, Any]:
    """Build a v1-style dict from AgenticWorkflowConfigTable row. Includes all keys required by validate_legacy_preset_strict."""
    if row is None:
        return _empty_v1()
    raw: dict[str, Any] = {
        "version": "1.0",
        "thresholds": {},
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
    Accepts UI-ordered export format: if preset has per-section blocks (e.g. RankAgent with RankingThreshold),
    converts to v2 then migrates/validates.
    raw: either a dict (from JSON/preset or API) or an AgenticWorkflowConfigTable row.
    Raises ValidationError if migrated config is invalid.
    """
    if not isinstance(raw, dict):
        raw = _normalize_raw_from_db(raw)
    if is_ui_ordered_preset(raw):
        validate_ui_ordered_preset_strict(raw)
        raw = ui_ordered_to_v2(raw)
    elif _is_legacy_v1_shape(raw):
        validate_legacy_preset_strict(raw)
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
    Load preset (v1 or v2), enforce metadata, re-validate, and return UI-ordered export dict.
    Export order matches the workflow config UI: JunkFilter → QASettings → OSDetection → RankAgent
    (settings + prompt + QA) → ExtractAgent → CmdlineExtract (settings + prompt + QA) → … → SigmaAgent.
    - Populates Metadata.CreatedAt (UTC ISO8601) if empty
    - Populates Metadata.Description if empty (default "Exported preset")
    - Re-validates with WorkflowConfigV2 after round-trip; aborts (raises ValidationError) if invalid.
    """
    config = load_workflow_config(raw)
    if not config.Metadata.CreatedAt:
        config.Metadata.CreatedAt = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not config.Metadata.Description:
        config.Metadata.Description = "Exported preset"
    dumped = config.model_dump(mode="json")
    dumped["Agents"] = order_agents_for_export(dumped["Agents"])
    ordered_v2 = _build_v2_export_ordered(dumped)
    WorkflowConfigV2.model_validate(ordered_v2)
    return v2_to_ui_ordered_export(ordered_v2)
