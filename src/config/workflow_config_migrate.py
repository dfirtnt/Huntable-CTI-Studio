"""
Migrate legacy (v1) flat workflow config to normalized v2 schema.

On read: always run through migration so v1 configs become v2.
On write: accept v1 or v2; normalize to v2 before persist.
Logs deprecation for legacy keys consumed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

V2_VERSION = "2.0"

# Legacy flat agent key -> (v2 agent name, model_key for flat dict)
# Model key: "Name" for main/QA, "Name_model" for sub-agents, "OSDetectionAgent_fallback" for fallback
_AGENT_FLAT_PREFIXES = [
    ("RankAgent", "RankAgent", "RankAgent"),
    ("ExtractAgent", "ExtractAgent", "ExtractAgent"),
    ("SigmaAgent", "SigmaAgent", "SigmaAgent"),
    ("OSDetectionAgent_fallback", "OSDetectionFallback", "OSDetectionAgent_fallback"),
    ("CmdlineExtract", "CmdlineExtract", "CmdlineExtract_model"),
    ("ProcTreeExtract", "ProcTreeExtract", "ProcTreeExtract_model"),
    ("HuntQueriesExtract", "HuntQueriesExtract", "HuntQueriesExtract_model"),
    ("RankAgentQA", "RankAgentQA", "RankAgentQA"),
    ("CmdLineQA", "CmdlineQA", "CmdLineQA"),  # legacy CmdLineQA -> CmdlineQA
    ("ProcTreeQA", "ProcTreeQA", "ProcTreeQA"),
    ("HuntQueriesQA", "HuntQueriesQA", "HuntQueriesQA"),
]


def _float_val(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bool_val(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def _str_val(v: Any, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _normalize_v2_strict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize already-v2 dict to strict schema: strip legacy feature keys,
    align QA.Enabled and Prompts keys, ensure agent Enabled from legacy flags.
    """
    from src.config.workflow_config_schema import CANONICAL_PROMPT_AGENT_NAMES

    out = dict(raw)
    # Features: remove agent-enablement keys (derive from Agents on export/legacy)
    features = dict(out.get("Features") or {})
    rank_en = features.pop("RankAgentEnabled", None)
    os_fb = features.pop("OsDetectionFallbackEnabled", None)
    out["Features"] = features

    agents = dict(out.get("Agents") or {})
    if "RankAgent" in agents and rank_en is not None:
        agents["RankAgent"] = dict(agents["RankAgent"])
        agents["RankAgent"]["Enabled"] = _bool_val(rank_en, True)
    if "OSDetectionFallback" in agents and os_fb is not None:
        agents["OSDetectionFallback"] = dict(agents["OSDetectionFallback"])
        agents["OSDetectionFallback"]["Enabled"] = _bool_val(os_fb, False)
    out["Agents"] = agents

    # QA.Enabled: OSDetectionAgent -> OSDetectionFallback
    qa = dict(out.get("QA") or {})
    enabled = dict(qa.get("Enabled") or {})
    if "OSDetectionAgent" in enabled:
        enabled["OSDetectionFallback"] = enabled.pop("OSDetectionAgent")
    qa["Enabled"] = enabled
    out["QA"] = qa

    # Prompts: drop non-canonical keys (e.g. ExtractAgentSettings)
    prompts = dict(out.get("Prompts") or {})
    prompts_clean = {
        k: {"prompt": (v.get("prompt", "") if isinstance(v, dict) else ""), "instructions": (v.get("instructions", "") if isinstance(v, dict) else "")}
        for k, v in prompts.items()
        if k in CANONICAL_PROMPT_AGENT_NAMES
    }
    out["Prompts"] = prompts_clean

    return out


def migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Transform legacy flat structure to normalized v2 (PascalCase sections).
    If Version is already "2.0", normalize to strict v2 (strip legacy feature keys, align QA/Prompts).
    Otherwise build v2 from flat keys and log deprecation for legacy keys used.
    """
    if raw.get("Version") == V2_VERSION or raw.get("version") == V2_VERSION:
        return _normalize_v2_strict(raw)

    # Normalize input: accept snake_case or camelCase from presets/DB
    version = raw.get("version") or raw.get("Version") or "1.0"
    if version == V2_VERSION:
        return raw

    deprecated_used: list[str] = []

    # Thresholds
    thresholds = raw.get("thresholds") or {}
    min_hunt = raw.get("min_hunt_score")
    if min_hunt is not None:
        deprecated_used.append("min_hunt_score")
    Thresholds = {
        "MinHuntScore": _float_val(min_hunt if min_hunt is not None else thresholds.get("min_hunt_score"), 97.0),
        "RankingThreshold": _float_val(thresholds.get("ranking_threshold") or raw.get("ranking_threshold"), 6.0),
        "SimilarityThreshold": _float_val(thresholds.get("similarity_threshold") or raw.get("similarity_threshold"), 0.5),
        "JunkFilterThreshold": _float_val(thresholds.get("junk_filter_threshold") or raw.get("junk_filter_threshold"), 0.8),
        "AutoTriggerHuntScoreThreshold": _float_val(
            raw.get("auto_trigger_hunt_score_threshold"), 60.0
        ),
    }
    if raw.get("ranking_threshold") is not None:
        deprecated_used.append("ranking_threshold")
    if raw.get("similarity_threshold") is not None:
        deprecated_used.append("similarity_threshold")
    if raw.get("junk_filter_threshold") is not None:
        deprecated_used.append("junk_filter_threshold")

    # Agent models (flat) -> Agents (nested)
    agent_models = raw.get("agent_models") or {}
    Agents: dict[str, dict[str, Any]] = {}
    for flat_prefix, v2_name, model_key in _AGENT_FLAT_PREFIXES:
        provider = agent_models.get(f"{flat_prefix}_provider")
        if provider is not None or flat_prefix in ("RankAgent", "ExtractAgent", "SigmaAgent"):
            deprecated_used.append(f"agent_models[{flat_prefix}_*]")
        model = agent_models.get(model_key) if model_key != flat_prefix else agent_models.get(flat_prefix)
        temp = agent_models.get(f"{flat_prefix}_temperature")
        top_p = agent_models.get(f"{flat_prefix}_top_p")
        Agents[v2_name] = {
            "Provider": _str_val(provider, "lmstudio"),
            "Model": _str_val(model),
            "Temperature": _float_val(temp, 0.0),
            "TopP": _float_val(top_p, 0.9),
            "Enabled": True,
        }

    # Embeddings (from agent_models)
    os_emb = agent_models.get("OSDetectionAgent_embedding")
    sigma_emb = agent_models.get("SigmaEmbeddingModel")
    if os_emb is not None:
        deprecated_used.append("agent_models[OSDetectionAgent_embedding]")
    if sigma_emb is not None:
        deprecated_used.append("agent_models[SigmaEmbeddingModel]")
    Embeddings = {
        "OsDetection": _str_val(os_emb, "ibm-research/CTI-BERT"),
        "Sigma": _str_val(sigma_emb, "ibm-research/CTI-BERT"),
    }

    # QA: align keys with Agents (OSDetectionAgent -> OSDetectionFallback)
    qa_enabled = raw.get("qa_enabled") or {}
    qa_max = raw.get("qa_max_retries")
    if qa_max is not None:
        deprecated_used.append("qa_max_retries")
    qa_enabled_normalized: dict[str, bool] = {}
    for k, v in qa_enabled.items():
        key = "OSDetectionFallback" if k == "OSDetectionAgent" else k
        qa_enabled_normalized[key] = _bool_val(v)
    QA = {
        "Enabled": qa_enabled_normalized,
        "MaxRetries": int(qa_max) if qa_max is not None else 5,
    }

    # Agent execution: rank and OS fallback from legacy flags into Agents
    rank_en = raw.get("rank_agent_enabled")
    os_fb = raw.get("osdetection_fallback_enabled")
    if rank_en is not None:
        deprecated_used.append("rank_agent_enabled")
    if os_fb is not None:
        deprecated_used.append("osdetection_fallback_enabled")
    if "RankAgent" in Agents:
        Agents["RankAgent"]["Enabled"] = _bool_val(rank_en, True)
    if "OSDetectionFallback" in Agents:
        Agents["OSDetectionFallback"]["Enabled"] = _bool_val(os_fb, False)

    # Features (no agent enablement; only sigma fallback and cmdline preprocessor)
    sigma_fb = raw.get("sigma_fallback_enabled")
    cmdline_pre = raw.get("cmdline_attention_preprocessor_enabled")
    if sigma_fb is not None:
        deprecated_used.append("sigma_fallback_enabled")
    if cmdline_pre is not None:
        deprecated_used.append("cmdline_attention_preprocessor_enabled")
    Features = {
        "SigmaFallbackEnabled": _bool_val(sigma_fb, False),
        "CmdlineAttentionPreprocessorEnabled": _bool_val(cmdline_pre, True),
    }

    # Prompts: only canonical agent names (no ExtractAgentSettings; that lives under Execution)
    from src.config.workflow_config_schema import CANONICAL_PROMPT_AGENT_NAMES

    agent_prompts = raw.get("agent_prompts") or {}
    Prompts: dict[str, Any] = {}
    for name, val in agent_prompts.items():
        if name == "ExtractAgentSettings":
            continue
        if name not in CANONICAL_PROMPT_AGENT_NAMES:
            continue
        if isinstance(val, dict):
            Prompts[name] = {"prompt": val.get("prompt", ""), "instructions": val.get("instructions", "")}
        else:
            Prompts[name] = {"prompt": "", "instructions": ""}

    # Execution
    extract_settings = raw.get("extract_agent_settings") or {}
    disabled = extract_settings.get("disabled_agents") if isinstance(extract_settings, dict) else []
    if not isinstance(disabled, list):
        disabled = []
    selected_os = agent_models.get("OSDetectionAgent_selected_os") or raw.get("OSDetectionAgent_selected_os")
    if selected_os is not None:
        deprecated_used.append("OSDetectionAgent_selected_os")
    if not isinstance(selected_os, list):
        selected_os = ["Windows"]
    Execution = {
        "ExtractAgentSettings": {"DisabledAgents": disabled},
        "OsDetectionSelectedOs": selected_os,
    }

    # Metadata
    created = raw.get("created_at") or raw.get("Metadata", {}).get("CreatedAt") if isinstance(raw.get("Metadata"), dict) else ""
    desc = raw.get("description") or (raw.get("Metadata", {}) or {}).get("Description") if isinstance(raw.get("Metadata"), dict) else ""
    if isinstance(created, bytes):
        created = ""
    if isinstance(desc, bytes):
        desc = ""
    Metadata = {
        "CreatedAt": _str_val(created),
        "Description": _str_val(desc),
    }

    if deprecated_used:
        logger.info("Workflow config migration v1->v2: consumed legacy keys: %s", deprecated_used)

    return {
        "Version": V2_VERSION,
        "Metadata": Metadata,
        "Thresholds": Thresholds,
        "Agents": Agents,
        "Embeddings": Embeddings,
        "QA": QA,
        "Features": Features,
        "Prompts": Prompts,
        "Execution": Execution,
    }
