"""Contract guard for the enrich modal's active-config state indicator + in-place Save.

The SIGMA enrich modal (workflow.html #enrichModal) lets a user load an
enrichment preset and then edit provider/model/system-prompt/instruction on top
of it. Before this feature there was no signal for "what's active / what's saved
/ what's drifted", and Save always prompted for a brand-new name (save-as-new),
so editing a loaded preset and re-saving silently forked it.

This test pins the contract of that feature against workflow.html so a future
refactor can't quietly drop it:

- A #enrichPresetState indicator element exists.
- updateEnrichPresetState() renders the three states (Unsaved / clean / modified).
- loadPresetById, saveEnrichmentPreset, and openEnrichModal maintain the
  loaded-preset + baseline state so drift is detectable.
- saveEnrichmentPreset defaults the name prompt to the loaded preset's name
  (in-place update via the upsert-by-name backend), not a blank save-as-new.

These are unit tests — no DB, no browser. They parse the template source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"


def _source() -> str:
    return WORKFLOW_TEMPLATE.read_text()


def _function_body(source: str, name: str) -> str:
    """Extract a top-level function body from declaration to the next function."""
    m = re.search(
        rf"((?:async )?function {re.escape(name)}\b.*?)(?=\n(?:async )?function )",
        source,
        re.DOTALL,
    )
    assert m, f"{name} not found in workflow.html — update this test if it was renamed"
    return m.group(1)


# ---------------------------------------------------------------------------
# Indicator element + renderer
# ---------------------------------------------------------------------------


def test_indicator_element_present():
    src = _source()
    assert 'id="enrichPresetState"' in src, "The #enrichPresetState indicator element must exist in the enrich modal"


def test_update_function_renders_three_states():
    body = _function_body(_source(), "updateEnrichPresetState")
    assert "Unsaved config" in body, "must render the no-preset 'Unsaved config' state"
    assert "· clean" in body, "must render the clean (no-drift) state"
    assert "· modified" in body, "must render the modified (drift) state"


def test_state_vars_declared():
    src = _source()
    assert "let enrichLoadedPreset" in src, "enrichLoadedPreset state var must be declared"
    assert "let enrichBaseline" in src, "enrichBaseline state var must be declared"


# ---------------------------------------------------------------------------
# Drift detection compares the four editable fields
# ---------------------------------------------------------------------------


def test_drift_compares_all_four_fields():
    body = _function_body(_source(), "_enrichConfigDrifted")
    for field in ("provider", "model", "systemPrompt", "userInstruction"):
        assert field in body, f"_enrichConfigDrifted must compare {field}"


def test_drift_listeners_wired_for_each_control():
    body = _function_body(_source(), "_wireEnrichDriftListeners")
    for control in (
        "enrichProviderSelect",
        "enrichModelSelect",
        "enrichInstruction",
        "enrichSystemPrompt",
    ):
        assert control in body, f"drift listener must be wired for #{control}"
    assert "addEventListener" in body


# ---------------------------------------------------------------------------
# Load / Save / Open maintain the state
# ---------------------------------------------------------------------------


def test_load_preset_sets_loaded_and_baseline():
    body = _function_body(_source(), "loadPresetById")
    assert "enrichLoadedPreset = { id, name: data.name }" in body, (
        "loadPresetById must record the loaded preset id + name"
    )
    assert "_captureEnrichBaseline()" in body, "loadPresetById must snapshot the baseline"
    assert "updateEnrichPresetState()" in body, "loadPresetById must refresh the indicator"


def test_save_preset_defaults_to_loaded_name_for_in_place_update():
    body = _function_body(_source(), "saveEnrichmentPreset")
    # The name prompt must pre-fill the loaded preset's name so OK updates in place.
    assert re.search(r"prompt\([^)]*enrichLoadedPreset\s*\?\s*enrichLoadedPreset\.name", body), (
        "saveEnrichmentPreset must default the name prompt to the loaded preset's name "
        "(in-place update via upsert-by-name), falling back to blank for save-as-new"
    )
    assert "_captureEnrichBaseline()" in body, "save must reset the baseline to the saved config"
    assert "updateEnrichPresetState()" in body, "save must refresh the indicator to clean"


def test_open_modal_resets_to_unsaved_and_wires_listeners():
    body = _function_body(_source(), "openEnrichModal")
    assert "enrichLoadedPreset = null" in body, "opening the modal must clear any loaded preset"
    assert "_wireEnrichDriftListeners()" in body, "opening the modal must wire drift listeners"
    assert "updateEnrichPresetState()" in body, "opening the modal must set the initial indicator"
