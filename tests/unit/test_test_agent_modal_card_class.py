"""
Regression test: the Test-Agent modal in workflow.html must use a defined
card class, not the phantom `card-xl` utility.

Background
----------
`card-xl` is not defined in any CSS layer in this repo (base.html only
defines .card, .card-elevated, .card-interactive, .card-hover). When the
modal container used `card-xl`, Tailwind silently emitted no styles for
it, so the modal rendered transparent: no background, no border, no
radius, and the underlying page bled through, making the Test-Agent
modal look shattered.

This test pins the container to the defined `.card` class so the bug
cannot silently regress if someone copy-pastes the old pattern back.
"""

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"

# Matches the innerHTML line that opens the Test-Agent modal card. The
# preceding JS lines pin this to the test-subagent modal, so matching on
# the max-w-4xl + overflow-hidden + flex-col combo is enough to uniquely
# identify this container.
TEST_AGENT_CARD_RE = re.compile(
    r'<div class="([^"]*max-w-4xl w-full mx-4 max-h-\[90vh\] overflow-hidden flex flex-col[^"]*)">'
)


@pytest.mark.unit
class TestTestAgentModalCardClass:
    """Guard the Test-Agent modal container class list."""

    def _find_card_class(self) -> str:
        content = WORKFLOW_TEMPLATE.read_text()
        match = TEST_AGENT_CARD_RE.search(content)
        assert match is not None, (
            "Test-Agent modal container div not found in workflow.html -- selector drifted; update TEST_AGENT_CARD_RE."
        )
        return match.group(1)

    def test_uses_defined_card_class(self):
        """The container must include the defined `.card` class."""
        classes = self._find_card_class().split()
        assert "card" in classes, f"Test-Agent modal must use the defined `.card` class; got class list: {classes}"

    def test_does_not_use_phantom_card_xl(self):
        """`card-xl` has no CSS definition and must not be used here."""
        classes = self._find_card_class().split()
        assert "card-xl" not in classes, (
            "Test-Agent modal reintroduced the undefined `card-xl` class, "
            "which renders the modal transparent. Use `card` instead."
        )
