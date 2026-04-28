"""
Utility test: compare an exported workflow config against a quickstart preset.

Skips automatically when env vars are not set, so it is safe for CI.

Usage:
    EXPORT_FILE=~/Downloads/workflow-preset-2026-04-27.json \\
    PRESET_NAME=Quickstart-LMStudio-Gemma4B \\
    pytest tests/config/test_preset_export_comparison.py -v
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_QUICKSTART_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"


def _norm(v: Any) -> Any:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in sorted(v.items())}
    return v


def _load_normalized(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    out = copy.deepcopy(data)
    out.pop("Metadata", None)  # CreatedAt refreshes on export; Description is overwritten
    return _norm(out)


def compare_preset_files(path_a: Path, path_b: Path) -> list[str]:
    """Return a list of section-level mismatch descriptions, empty if identical."""
    a = _load_normalized(path_a)
    b = _load_normalized(path_b)
    all_sections = sorted(set(a.keys()) | set(b.keys()))
    mismatches: list[str] = []
    for section in all_sections:
        sa = a.get(section)
        sb = b.get(section)
        if sa != sb:
            mismatches.append(
                f"\n  [{section}]\n    file_a: {json.dumps(sa, indent=2)}\n    file_b: {json.dumps(sb, indent=2)}"
            )
    return mismatches


def test_compare_export_to_preset():
    """
    Compare an exported config file against a named quickstart preset.

    EXPORT_FILE  -- path to the exported JSON file (e.g. ~/Downloads/workflow-preset-*.json)
    PRESET_NAME  -- stem of the quickstart preset file (e.g. Quickstart-LMStudio-Gemma4B)

    Metadata is excluded from comparison: CreatedAt is always refreshed on export and
    Description is always overwritten with the stale "Exported preset" default.
    int/float differences (0 vs 0.0) are normalized before comparison.
    """
    export_path_str = os.environ.get("EXPORT_FILE")
    preset_name = os.environ.get("PRESET_NAME")

    if not export_path_str or not preset_name:
        pytest.skip("Set EXPORT_FILE and PRESET_NAME env vars to run this comparison")

    export_path = Path(export_path_str).expanduser().resolve()
    preset_path = _QUICKSTART_DIR / f"{preset_name}.json"

    assert export_path.exists(), f"Export file not found: {export_path}"
    assert preset_path.exists(), (
        f"Preset '{preset_name}' not found. Available: {sorted(p.stem for p in _QUICKSTART_DIR.glob('*.json'))}"
    )

    mismatches = compare_preset_files(export_path, preset_path)
    assert not mismatches, "Export differs from preset:" + "".join(mismatches)
