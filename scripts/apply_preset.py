#!/usr/bin/env python3
"""
Apply any workflow preset to config via API.

Steps:
1. Load preset, extract provider(s) from agent_models
2. Enable WORKFLOW_*_ENABLED in Settings for those providers
3. Convert preset to legacy, PUT to /api/workflow/config

Supports OpenAI, Anthropic, Gemini, LMStudio presets.

Usage:
  python3 scripts/apply_preset.py [PRESET_PATH] [--base-url http://localhost:8001]

  PRESET_PATH: Path to preset JSON (default: config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-4.1-mini.json)
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_PRESET = (
    Path(__file__).resolve().parent.parent
    / "config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-4.1-mini.json"
)

_PROVIDER_TO_SETTINGS_KEY = {
    "openai": "WORKFLOW_OPENAI_ENABLED",
    "anthropic": "WORKFLOW_ANTHROPIC_ENABLED",
    "gemini": "WORKFLOW_GEMINI_ENABLED",
    "lmstudio": "WORKFLOW_LMSTUDIO_ENABLED",
}


def extract_providers_from_agent_models(agent_models: dict) -> set[str]:
    """Extract unique provider names from agent_models (keys ending with _provider)."""
    providers = set()
    if not agent_models:
        return providers
    for key, value in agent_models.items():
        if key.endswith("_provider") and value and isinstance(value, str):
            prov = value.strip().lower()
            if prov in _PROVIDER_TO_SETTINGS_KEY:
                providers.add(prov)
    return providers


def load_and_convert_preset(preset_path: Path) -> dict:
    """Load preset and convert to legacy shape for PUT payload."""
    from src.config.workflow_config_loader import load_workflow_config

    raw = json.loads(preset_path.read_text(encoding="utf-8"))
    config = load_workflow_config(raw)
    return _v2_to_legacy(config)


def _v2_to_legacy(config) -> dict:
    """Convert WorkflowConfigV2 to legacy preset shape (matches workflow_config._v2_to_legacy_preset_dict)."""
    qa_enabled = dict(config.QA.Enabled)
    if "OSDetectionFallback" in qa_enabled and "OSDetectionAgent" not in qa_enabled:
        qa_enabled["OSDetectionAgent"] = qa_enabled["OSDetectionFallback"]
    return {
        "min_hunt_score": config.Thresholds.MinHuntScore,
        "auto_trigger_hunt_score_threshold": config.Thresholds.AutoTriggerHuntScoreThreshold,
        "ranking_threshold": config.Thresholds.RankingThreshold,
        "similarity_threshold": config.Thresholds.SimilarityThreshold,
        "junk_filter_threshold": config.Thresholds.JunkFilterThreshold,
        "thresholds": {
            "ranking_threshold": config.Thresholds.RankingThreshold,
            "similarity_threshold": config.Thresholds.SimilarityThreshold,
            "junk_filter_threshold": config.Thresholds.JunkFilterThreshold,
        },
        "agent_models": config.flatten_for_llm_service(),
        "qa_enabled": qa_enabled,
        "sigma_fallback_enabled": config.Features.SigmaFallbackEnabled,
        "osdetection_fallback_enabled": (
            config.Agents.get("OSDetectionFallback").Enabled if config.Agents.get("OSDetectionFallback") else False
        ),
        "rank_agent_enabled": (config.Agents.get("RankAgent").Enabled if config.Agents.get("RankAgent") else True),
        "qa_max_retries": config.QA.MaxRetries,
        "cmdline_attention_preprocessor_enabled": config.Features.CmdlineAttentionPreprocessorEnabled,
        "extract_agent_settings": {"disabled_agents": list(config.Execution.ExtractAgentSettings.DisabledAgents)},
        "agent_prompts": {
            name: {
                "prompt": p.get("prompt", "") if isinstance(p, dict) else getattr(p, "prompt", ""),
                "instructions": p.get("instructions", "") if isinstance(p, dict) else getattr(p, "instructions", ""),
            }
            for name, p in config.Prompts.items()
        },
    }


def build_put_payload(legacy: dict, description: str = "Preset applied via script") -> dict:
    """Build PUT /api/workflow/config payload from legacy preset."""
    prompts = dict(legacy.get("agent_prompts") or {})
    extract_settings = legacy.get("extract_agent_settings") or {}
    disabled = extract_settings.get("disabled_agents") or []
    if "ExtractAgentSettings" not in prompts:
        prompts["ExtractAgentSettings"] = {}
    prompts["ExtractAgentSettings"]["disabled_agents"] = disabled

    th = legacy.get("thresholds", {})
    return {
        "min_hunt_score": legacy.get("min_hunt_score", 97.0),
        "ranking_threshold": th.get("ranking_threshold", legacy.get("ranking_threshold", 6.0)),
        "similarity_threshold": th.get("similarity_threshold", legacy.get("similarity_threshold", 0.5)),
        "junk_filter_threshold": th.get("junk_filter_threshold", legacy.get("junk_filter_threshold", 0.8)),
        "auto_trigger_hunt_score_threshold": legacy.get("auto_trigger_hunt_score_threshold", 60.0),
        "agent_models": legacy.get("agent_models", {}),
        "qa_enabled": legacy.get("qa_enabled", {}),
        "sigma_fallback_enabled": legacy.get("sigma_fallback_enabled", False),
        "osdetection_fallback_enabled": legacy.get("osdetection_fallback_enabled", False),
        "rank_agent_enabled": legacy.get("rank_agent_enabled", True),
        "qa_max_retries": legacy.get("qa_max_retries", 5),
        "cmdline_attention_preprocessor_enabled": legacy.get("cmdline_attention_preprocessor_enabled", True),
        "agent_prompts": prompts,
        "description": description,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply workflow preset to config via API")
    parser.add_argument(
        "preset_path",
        nargs="?",
        default=str(DEFAULT_PRESET),
        help=f"Path to preset JSON (default: {DEFAULT_PRESET})",
    )
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL of the app")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    preset_path = Path(args.preset_path)
    if not preset_path.exists():
        print(f"Error: Preset not found: {preset_path}")
        return 1

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Load preset and extract providers
        print(f"1. Loading preset: {preset_path}")
        legacy = load_and_convert_preset(preset_path)
        agent_models = legacy.get("agent_models") or {}
        providers = extract_providers_from_agent_models(agent_models)
        if not providers:
            print("   Warning: No known providers in preset (openai, anthropic, gemini, lmstudio)")
        else:
            print(f"   Providers in preset: {', '.join(sorted(providers))}")

        # Step 2: Enable providers in Settings
        if providers:
            settings = {_PROVIDER_TO_SETTINGS_KEY[p]: "true" for p in providers}
            print(f"2. Enabling providers in Settings: {list(settings.keys())}")
            r = client.post(f"{base}/api/settings/bulk", json={"settings": settings})
            if r.status_code != 200:
                print(f"   Warning: Settings bulk update failed: {r.status_code} {r.text}")
            else:
                print("   OK")
        else:
            print("2. Skipping Settings (no providers to enable)")

        # Step 3: Apply preset
        desc = f"{preset_path.stem} (applied via script)"
        payload = build_put_payload(legacy, description=desc)
        print("3. Applying preset to workflow config...")
        r = client.put(f"{base}/api/workflow/config", json=payload)
        if r.status_code != 200:
            print(f"   Error: Config update failed: {r.status_code}")
            print(r.text)
            return 1
        print("   OK")

        # Verify
        r = client.get(f"{base}/api/workflow/config")
        if r.status_code == 200:
            cfg = r.json()
            am = cfg.get("agent_models") or {}
            rank_prov = am.get("RankAgent_provider", "?")
            rank_model = am.get("RankAgent", "?")
            print(f"4. Verified: RankAgent = {rank_model} (provider: {rank_prov})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
