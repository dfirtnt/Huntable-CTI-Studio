#!/usr/bin/env python3
"""
Build workflow config baseline presets with prompts from src/prompts.

Writes three preset JSON files to config/presets/AgentConfigs/ for users to load
via Workflow Config → Import from file (v1 format for UI compatibility).
Normalized v2 schema is supported by src.config.workflow_config_loader; see
config/schema/workflow_config_v2_example.json and docs/architecture/agent-config-schema.md.

Run from repo root: python3 scripts/build_baseline_presets.py
Optional: python3 scripts/build_baseline_presets.py --v2  # also write one v2 example to config/schema/
"""

import json
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRESETS_DIR = REPO_ROOT / "config" / "presets" / "AgentConfigs"


def _defaults() -> dict:
    """Shared default structure (thresholds, qa_enabled, etc.)."""
    return {
        "version": "1.0",
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "thresholds": {
            "junk_filter_threshold": 0.8,
            "ranking_threshold": 6.0,
            "similarity_threshold": 0.5,
        },
        "sigma_fallback_enabled": False,
        "rank_agent_enabled": True,
        "cmdline_attention_preprocessor_enabled": True,
        "qa_max_retries": 3,
        "extract_agent_settings": {"disabled_agents": []},
        "qa_enabled": {
            "OSDetectionAgent": False,
            "RankAgent": False,
            "CmdlineExtract": True,
            "ProcTreeExtract": True,
            "HuntQueriesExtract": True,
            "SigmaAgent": False,
        },
    }


def _agent_models_anthropic_sonnet() -> dict:
    """All agents use Anthropic; model claude-sonnet-4-5."""
    base = "claude-sonnet-4-5"
    return {
        "RankAgent_provider": "anthropic",
        "RankAgent": base,
        "RankAgent_temperature": 0,
        "RankAgent_top_p": 0.9,
        "ExtractAgent_provider": "anthropic",
        "ExtractAgent": base,
        "ExtractAgent_temperature": 0,
        "ExtractAgent_top_p": 0.9,
        "SigmaAgent_provider": "anthropic",
        "SigmaAgent": base,
        "SigmaAgent_temperature": 0,
        "SigmaAgent_top_p": 0.9,
        "OSDetectionAgent_fallback_provider": "anthropic",
        "OSDetectionAgent_fallback": base,
        "CmdlineExtract_provider": "anthropic",
        "CmdlineExtract_model": base,
        "CmdlineExtract_temperature": 0,
        "CmdlineExtract_top_p": 0.9,
        "ProcTreeExtract_provider": "anthropic",
        "ProcTreeExtract_model": base,
        "ProcTreeExtract_temperature": 0,
        "ProcTreeExtract_top_p": 0.9,
        "HuntQueriesExtract_provider": "anthropic",
        "HuntQueriesExtract_model": base,
        "HuntQueriesExtract_temperature": 0,
        "HuntQueriesExtract_top_p": 0.9,
        "RankAgentQA_provider": "anthropic",
        "RankAgentQA": base,
        "RankAgentQA_temperature": 0.1,
        "RankAgentQA_top_p": 0.9,
        "CmdLineQA_provider": "anthropic",
        "CmdLineQA": base,
        "CmdLineQA_temperature": 0.1,
        "CmdLineQA_top_p": 0.9,
        "ProcTreeQA_provider": "anthropic",
        "ProcTreeQA": base,
        "ProcTreeQA_temperature": 0.1,
        "ProcTreeQA_top_p": 0.9,
        "HuntQueriesQA_provider": "anthropic",
        "HuntQueriesQA": base,
        "HuntQueriesQA_temperature": 0.1,
        "HuntQueriesQA_top_p": 0.9,
        "OSDetectionAgent_embedding": "ibm-research/CTI-BERT",
    }


def _agent_models_openai_4o_mini() -> dict:
    """All agents use OpenAI; model gpt-4o-mini."""
    base = "gpt-4o-mini"
    return {
        "RankAgent_provider": "openai",
        "RankAgent": base,
        "RankAgent_temperature": 0,
        "RankAgent_top_p": 0.9,
        "ExtractAgent_provider": "openai",
        "ExtractAgent": base,
        "ExtractAgent_temperature": 0.3,
        "ExtractAgent_top_p": 0.9,
        "SigmaAgent_provider": "openai",
        "SigmaAgent": base,
        "SigmaAgent_temperature": 0.3,
        "SigmaAgent_top_p": 0.9,
        "OSDetectionAgent_fallback_provider": "openai",
        "OSDetectionAgent_fallback": base,
        "CmdlineExtract_provider": "openai",
        "CmdlineExtract_model": base,
        "CmdlineExtract_temperature": 0.2,
        "CmdlineExtract_top_p": 0.9,
        "ProcTreeExtract_provider": "openai",
        "ProcTreeExtract_model": base,
        "ProcTreeExtract_temperature": 0.2,
        "ProcTreeExtract_top_p": 0.9,
        "HuntQueriesExtract_provider": "openai",
        "HuntQueriesExtract_model": base,
        "HuntQueriesExtract_temperature": 0.2,
        "HuntQueriesExtract_top_p": 0.9,
        "RankAgentQA_provider": "openai",
        "RankAgentQA": base,
        "RankAgentQA_temperature": 0.1,
        "RankAgentQA_top_p": 0.9,
        "CmdLineQA_provider": "openai",
        "CmdLineQA": base,
        "CmdLineQA_temperature": 0.1,
        "CmdLineQA_top_p": 0.9,
        "ProcTreeQA_provider": "openai",
        "ProcTreeQA": base,
        "ProcTreeQA_temperature": 0.1,
        "ProcTreeQA_top_p": 0.9,
        "HuntQueriesQA_provider": "openai",
        "HuntQueriesQA": base,
        "HuntQueriesQA_temperature": 0.1,
        "HuntQueriesQA_top_p": 0.9,
        "OSDetectionAgent_embedding": "nlpaueb/sec-bert-base",
    }


def _agent_models_lmstudio_qwen8b() -> dict:
    """All agents use LM Studio; model name for Qwen 2.5 8B (user can change in LM Studio)."""
    base = "Qwen/Qwen2.5-8B-Instruct"
    return {
        "RankAgent_provider": "lmstudio",
        "RankAgent": base,
        "RankAgent_temperature": 0,
        "RankAgent_top_p": 0.9,
        "ExtractAgent_provider": "lmstudio",
        "ExtractAgent": base,
        "ExtractAgent_temperature": 0,
        "ExtractAgent_top_p": 0.9,
        "SigmaAgent_provider": "lmstudio",
        "SigmaAgent": base,
        "SigmaAgent_temperature": 0,
        "SigmaAgent_top_p": 0.9,
        "OSDetectionAgent_fallback_provider": "lmstudio",
        "OSDetectionAgent_fallback": base,
        "CmdlineExtract_provider": "lmstudio",
        "CmdlineExtract_model": base,
        "CmdlineExtract_temperature": 0,
        "CmdlineExtract_top_p": 0.9,
        "ProcTreeExtract_provider": "lmstudio",
        "ProcTreeExtract_model": base,
        "ProcTreeExtract_temperature": 0,
        "ProcTreeExtract_top_p": 0.9,
        "HuntQueriesExtract_provider": "lmstudio",
        "HuntQueriesExtract_model": base,
        "HuntQueriesExtract_temperature": 0,
        "HuntQueriesExtract_top_p": 0.9,
        "RankAgentQA_provider": "lmstudio",
        "RankAgentQA": base,
        "RankAgentQA_temperature": 0.1,
        "RankAgentQA_top_p": 0.9,
        "CmdLineQA_provider": "lmstudio",
        "CmdLineQA": base,
        "CmdLineQA_temperature": 0.1,
        "CmdLineQA_top_p": 0.9,
        "ProcTreeQA_provider": "lmstudio",
        "ProcTreeQA": base,
        "ProcTreeQA_temperature": 0.1,
        "ProcTreeQA_top_p": 0.9,
        "HuntQueriesQA_provider": "lmstudio",
        "HuntQueriesQA": base,
        "HuntQueriesQA_temperature": 0.1,
        "HuntQueriesQA_top_p": 0.9,
        "OSDetectionAgent_embedding": "ibm-research/CTI-BERT",
    }


def _build_v2_preset(description: str, agent_models_flat: dict, agent_prompts: dict | None = None) -> dict:
    """Build a v2-format preset dict from flat agent_models (for --v2 output)."""
    from src.config.workflow_config_migrate import migrate_v1_to_v2

    raw = _defaults()
    raw["description"] = description
    raw["agent_models"] = agent_models_flat
    raw["agent_prompts"] = agent_prompts or {}
    return migrate_v1_to_v2(raw)


def main() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    from src.utils.default_agent_prompts import get_default_agent_prompts

    write_v2 = "--v2" in sys.argv
    prompts = get_default_agent_prompts()
    if not prompts:
        print("Warning: no prompts loaded from src/prompts; agent_prompts will be empty.", file=sys.stderr)

    baselines = [
        (
            "anthropic-sonnet-4.5.json",
            "Anthropic Claude Sonnet 4.5 — all workflow agents use Claude Sonnet 4.5. Set ANTHROPIC_API_KEY.",
            _agent_models_anthropic_sonnet(),
        ),
        (
            "chatgpt-4o-mini.json",
            "OpenAI GPT-4o-mini — all workflow agents use gpt-4o-mini. Set OPENAI_API_KEY or CHATGPT_API_KEY.",
            _agent_models_openai_4o_mini(),
        ),
        (
            "lmstudio-qwen2.5-8b.json",
            "LM Studio Qwen 2.5 8B — all workflow agents use a local model (default name Qwen/Qwen2.5-8B-Instruct). Load the model in LM Studio and ensure LMSTUDIO_API_URL is set.",
            _agent_models_lmstudio_qwen8b(),
        ),
    ]

    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, description, agent_models in baselines:
        preset = _defaults()
        preset["description"] = description
        preset["agent_models"] = agent_models
        preset["agent_prompts"] = prompts
        preset["scope"] = "full"
        path = PRESETS_DIR / filename
        path.write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {path}")

    if write_v2:
        schema_dir = REPO_ROOT / "config" / "schema"
        schema_dir.mkdir(parents=True, exist_ok=True)
        v2_preset = _build_v2_preset(baselines[0][1], baselines[0][2], agent_prompts=prompts)
        v2_preset["Metadata"] = v2_preset.get("Metadata") or {}
        v2_preset["Metadata"]["Description"] = baselines[0][1]
        v2_path = schema_dir / "workflow_config_v2_baseline_example.json"
        v2_path.write_text(json.dumps(v2_preset, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote v2 example {v2_path}")


if __name__ == "__main__":
    main()
