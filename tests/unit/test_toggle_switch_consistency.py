"""
Regression test: all Tailwind toggle switches in workflow.html must use
the same track size, knob size, and focus-ring width.

Prevents size drift when new toggles are copy-pasted with different dimensions.
"""

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"

# Canonical toggle dimensions (track w-11 h-6, knob h-5 w-5, ring-4)
EXPECTED_TRACK = ("w-11", "h-6")
EXPECTED_KNOB = ("after:h-5", "after:w-5")
EXPECTED_RING = "peer-focus:ring-4"

# Pattern: Tailwind peer-checked toggle div (the styled track element)
TOGGLE_RE = re.compile(
    r'<div\s+class="(w-\d+\s+h-\d+\s+bg-gray-200\s+peer-focus:outline-none'
    r'\s+peer-focus:ring-\d+.*?peer-checked:bg-purple-600[^"]*)"',
)


@pytest.mark.unit
@pytest.mark.regression
class TestToggleSwitchConsistency:
    """Verify all toggle switches in workflow.html share identical sizing."""

    def _get_toggles(self):
        content = WORKFLOW_TEMPLATE.read_text()
        return TOGGLE_RE.findall(content)

    def test_toggles_found(self):
        """Sanity: template contains toggle switches."""
        toggles = self._get_toggles()
        assert len(toggles) >= 5, f"Expected at least 5 toggle switches, found {len(toggles)}"

    def test_all_toggles_same_track_size(self):
        """Every toggle track must be w-11 h-6."""
        for i, cls in enumerate(self._get_toggles()):
            for token in EXPECTED_TRACK:
                assert token in cls, f"Toggle #{i + 1} missing '{token}' in: {cls[:80]}..."

    def test_all_toggles_same_knob_size(self):
        """Every toggle knob must be after:h-5 after:w-5."""
        for i, cls in enumerate(self._get_toggles()):
            for token in EXPECTED_KNOB:
                assert token in cls, f"Toggle #{i + 1} missing '{token}' in: {cls[:80]}..."

    def test_all_toggles_same_ring_width(self):
        """Every toggle must use peer-focus:ring-4."""
        for i, cls in enumerate(self._get_toggles()):
            assert EXPECTED_RING in cls, f"Toggle #{i + 1} missing '{EXPECTED_RING}' in: {cls[:80]}..."
