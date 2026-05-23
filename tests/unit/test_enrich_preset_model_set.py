"""
Regression guard: loadPresetById must set the model dropdown via direct
assignment, not via setTimeout.

The setTimeout(100) race existed because populateEnrichModelDropdown was
not yet async-awaitable when the original code was written. The await was
added later but the setTimeout was left behind, creating a window where
the 100 ms could fire before the catalog options existed on slow loads,
silently dropping the preset model back to the dropdown default.

Fix committed 2026-05-23 (5e4ba82b): replaced with direct assignment
immediately after the await, plus a console.warn guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"

pytestmark = pytest.mark.unit


def _load_preset_by_id_body() -> str:
    """Extract the loadPresetById function body from workflow.html."""
    source = WORKFLOW_TEMPLATE.read_text()
    # Capture from the function declaration to the next top-level function
    m = re.search(
        r"(async function loadPresetById\b.*?)(?=\nasync function |\nfunction )",
        source,
        re.DOTALL,
    )
    assert m, "loadPresetById not found in workflow.html — update this test if the function was renamed"
    return m.group(1)


class TestLoadPresetByIdModelSetRegression:
    """Regression: model dropdown must be set synchronously after populateEnrichModelDropdown await."""

    def test_no_settimeout_for_model_assignment(self):
        """setTimeout must not be used to set enrichModelSelect.value inside loadPresetById.

        A setTimeout wrapper races against the await on populateEnrichModelDropdown —
        on slow catalog loads the timer fires before <option> elements exist.
        """
        body = _load_preset_by_id_body()
        # Detect any setTimeout that references model assignment
        bad = re.search(r"setTimeout\s*\(.*?enrichModelSelect.*?\)", body, re.DOTALL)
        assert not bad, (
            "loadPresetById uses setTimeout to set enrichModelSelect.value — "
            "this races against populateEnrichModelDropdown on slow catalog loads. "
            "Use a direct assignment after `await populateEnrichModelDropdown()`."
        )

    def test_direct_model_assignment_after_await(self):
        """After awaiting populateEnrichModelDropdown, model must be assigned directly."""
        body = _load_preset_by_id_body()
        assert "await populateEnrichModelDropdown(" in body, (
            "loadPresetById must await populateEnrichModelDropdown before setting model"
        )
        assert "modelSelect.value = data.model" in body, (
            "loadPresetById must directly assign modelSelect.value = data.model "
            "after the await (no setTimeout wrapper)"
        )

    def test_console_warn_guard_present(self):
        """A console.warn must fire if the resolved model is absent from the catalog."""
        body = _load_preset_by_id_body()
        assert 'console.warn' in body, (
            "loadPresetById should warn when the preset model is not found in the "
            "populated catalog — silent failures are hard to diagnose"
        )
