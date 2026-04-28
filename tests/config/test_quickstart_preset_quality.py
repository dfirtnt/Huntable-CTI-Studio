"""
Data-quality invariant tests for quickstart preset files.

Guards against regressions in the JSON files themselves (not the loader):
- QA agent temperatures must be uniform within each preset.
- Base agent temperatures must all be 0.0.
- Descriptions must not be the stale "Exported preset" export artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_QUICKSTART_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
_QUICKSTART_PRESETS = sorted(_QUICKSTART_DIR.glob("*.json"))

# Sections that carry a nested QA block with a Temperature field.
_QA_SECTIONS = [
    "RankAgent",
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
]

# Sections whose top-level Temperature must be deterministic (0.0).
_BASE_AGENT_SECTIONS = [
    "RankAgent",
    "ExtractAgent",
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
    "SigmaAgent",
]


def _load(preset_path: Path) -> dict:
    return json.loads(preset_path.read_text())


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_description_not_stale(preset_path: Path):
    """Description must not be the stale 'Exported preset' default."""
    data = _load(preset_path)
    desc = data.get("Metadata", {}).get("Description", "")
    assert desc != "Exported preset", (
        f"{preset_path.name}: Description is the stale export default 'Exported preset'; "
        "update it to describe the preset."
    )
    assert desc, f"{preset_path.name}: Description is empty."


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_qa_temperatures_uniform(preset_path: Path):
    """All QA agent temperatures within a preset must be the same value (no one-offs)."""
    data = _load(preset_path)
    temps: dict[str, float] = {}
    for section in _QA_SECTIONS:
        block = data.get(section, {})
        qa = block.get("QA")
        if qa and isinstance(qa, dict) and "Temperature" in qa:
            temps[section] = float(qa["Temperature"])

    if len(temps) < 2:
        return

    unique = set(temps.values())
    assert len(unique) == 1, (
        f"{preset_path.name}: QA temperatures are not uniform across agents. Values by section: {temps}"
    )


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_base_agent_temperatures_deterministic(preset_path: Path):
    """All base agent (non-QA) temperatures must be 0.0 for deterministic extraction."""
    data = _load(preset_path)
    wrong: dict[str, float] = {}
    for section in _BASE_AGENT_SECTIONS:
        block = data.get(section, {})
        if "Temperature" in block:
            t = float(block["Temperature"])
            if t != 0.0:
                wrong[section] = t

    assert not wrong, f"{preset_path.name}: Base agent temperatures must be 0.0. Non-zero values: {wrong}"
