"""Unit tests for scripts/build_baseline_presets.py path constants and helpers."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_baseline_presets as script


def test_presets_dir_under_config_presets_agent_configs():
    """PRESETS_DIR is config/presets/AgentConfigs under repo root."""
    assert script.PRESETS_DIR == script.REPO_ROOT / "config" / "presets" / "AgentConfigs"


def test_quickstart_dir_is_presets_dir_quickstart():
    """QUICKSTART_DIR is config/presets/AgentConfigs/quickstart."""
    assert script.QUICKSTART_DIR == script.PRESETS_DIR / "quickstart"
    assert script.QUICKSTART_DIR == script.REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"


def test_defaults_has_required_keys():
    """_defaults() returns dict with version, thresholds, qa_enabled, and expected structure."""
    d = script._defaults()
    assert d["version"] == "1.0"
    assert "thresholds" in d
    assert d["thresholds"].keys() >= {"junk_filter_threshold", "ranking_threshold", "similarity_threshold"}
    assert "qa_enabled" in d
    assert "qa_max_retries" in d
    assert "sigma_fallback_enabled" in d
    assert "osdetection_fallback_enabled" in d
    assert "created_at" in d


def test_order_v1_preset_preserves_keys_and_order():
    """_order_v1_preset returns dict with V1_ROOT_ORDER keys first, then any extra."""
    preset = {
        "version": "1.0",
        "description": "x",
        "thresholds": {"junk_filter_threshold": 0.8, "ranking_threshold": 6.0},
        "agent_models": {},
        "agent_prompts": {},
    }
    ordered = script._order_v1_preset(preset)
    order = list(ordered.keys())
    for key in script.V1_ROOT_ORDER:
        if key in preset:
            assert key in ordered, f"missing key {key}"
    assert ordered["version"] == "1.0"
    assert ordered["thresholds"]["junk_filter_threshold"] == 0.8
