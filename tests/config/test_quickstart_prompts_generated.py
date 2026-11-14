"""Quickstart preset prompts must be exactly what scripts/build_quickstart_prompts.py renders.

Regression context
-----------------
The 14 quickstart presets each embed a full copy of every agent prompt. SigmaAgent
fixes were hand-applied to some copies and not others: in October 2026 a stale
"never use EventID" rule survived in all 14 presets (three differently worded
variants) after the src/prompts/ version had been fixed, and the live config was
seeded from one of them. Nothing errored; generation just used the old rule.

Prompts are now edited only under src/prompts/ and rendered into the presets. This
test fails when a preset is edited by hand or a source changes without a rebuild.
Fix: ``uv run --frozen python scripts/build_quickstart_prompts.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_quickstart_prompts as builder  # noqa: E402

pytestmark = pytest.mark.unit


def test_every_quickstart_preset_matches_its_rendered_prompts():
    changed = builder.build(check=True)
    assert changed == [], (
        f"Quickstart presets drifted from src/prompts/: {changed}. "
        "Edit the source under src/prompts/ and run scripts/build_quickstart_prompts.py."
    )


def test_shared_sigma_block_reaches_every_preset():
    block = (builder.SHARED_DIR / "sigma_validation_pitfalls.txt").read_text(encoding="utf-8").rstrip("\n")
    for path in sorted(builder.QUICKSTART_DIR.glob("*.json")):
        system = json.loads(json.loads(path.read_text(encoding="utf-8"))["SigmaAgent"]["Prompt"]["prompt"])["system"]
        assert block in system, path.name
        assert "@@include" not in system, path.name


def test_check_mode_detects_a_source_change(tmp_path, monkeypatch):
    # Guard against a vacuous pass: editing a shared block must flag every preset that includes it.
    shared = tmp_path / "shared"
    shared.mkdir()
    original = (builder.SHARED_DIR / "sigma_validation_pitfalls.txt").read_text(encoding="utf-8")
    (shared / "sigma_validation_pitfalls.txt").write_text(original + "- extra rule\n", encoding="utf-8")
    monkeypatch.setattr(builder, "SHARED_DIR", shared)

    changed = builder.build(check=True)

    assert sorted(changed) == sorted(p.name for p in builder.QUICKSTART_DIR.glob("*.json"))


def test_manifest_lists_exactly_the_shipped_presets():
    manifest = builder.load_manifest()
    assert set(manifest) == {p.name for p in builder.QUICKSTART_DIR.glob("*.json")}
