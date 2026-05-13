"""Unit tests for scripts/build_baseline_presets.py path constants."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_baseline_presets as script
import pytest

pytestmark = pytest.mark.unit


def test_presets_dir_under_config_presets_agent_configs():
    """PRESETS_DIR is config/presets/AgentConfigs under repo root."""
    assert script.PRESETS_DIR == script.REPO_ROOT / "config" / "presets" / "AgentConfigs"


def test_quickstart_dir_is_presets_dir_quickstart():
    """QUICKSTART_DIR is config/presets/AgentConfigs/quickstart."""
    assert script.QUICKSTART_DIR == script.PRESETS_DIR / "quickstart"
    assert script.QUICKSTART_DIR == script.REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"
