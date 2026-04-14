"""
Regression test: the 'Current Configuration' disclosure in workflow.html
must keep the structural pieces that make its caret rotate on toggle.

Background
----------
The 'Current Configuration' panel is a native <details>/<summary> widget.
A static '>' (U+25B6) glyph was previously baked into the summary text,
so it never reflected open/closed state. The fix wraps the glyph in
<span class="caret"> and adds a CSS rule that rotates it 90 degrees
when details[open]. All three pieces must stay in place for the caret
to animate:

  1. The details element carries class 'current-config' (CSS selector root)
  2. The caret glyph is wrapped in <span class="caret">...U+25B6...</span>
  3. A CSS rule rotates details.current-config[open] > summary .caret

If any one regresses, the arrow goes back to being static and misleading.
"""

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"


@pytest.mark.unit
class TestCurrentConfigCaret:
    """Guard the markup + CSS that make the caret rotate on toggle."""

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return WORKFLOW_TEMPLATE.read_text()

    def test_details_has_current_config_class(self, template: str) -> None:
        """The <details> block must carry the 'current-config' hook class."""
        # Match a <details ...> whose class attribute contains 'current-config'.
        pattern = re.compile(
            r'<details[^>]*class="[^"]*\bcurrent-config\b[^"]*"[^>]*>',
            re.IGNORECASE,
        )
        assert pattern.search(template), (
            "Expected <details class='... current-config ...'> in workflow.html. "
            "Without this class the [open]-state CSS selector will not match and "
            "the caret will stop rotating."
        )

    def test_caret_glyph_is_wrapped_in_span(self, template: str) -> None:
        """The U+25B6 glyph must live inside <span class='caret'> ...</span>."""
        # Accept either the numeric entity or the raw character.
        pattern = re.compile(
            r'<span\s+class="caret">\s*(?:&#9654;|\u25B6)\s*</span>',
        )
        assert pattern.search(template), (
            "Expected <span class='caret'>&#9654;</span> inside the "
            "'Current Configuration' summary. Without the span wrapper there "
            "is nothing for the rotation CSS to target."
        )

    def test_open_state_rotates_caret(self, template: str) -> None:
        """CSS must rotate the caret when details[open]."""
        # Require a rule keyed on details.current-config[open] ... .caret
        # that sets a non-zero rotate(). We match rotate(90deg) specifically
        # because that is the documented, visually-correct angle; any other
        # value is almost certainly a typo.
        pattern = re.compile(
            r"details\.current-config\[open\][^{]*\.caret\s*\{[^}]*transform\s*:\s*rotate\(\s*90deg\s*\)",
            re.DOTALL,
        )
        assert pattern.search(template), (
            "Expected CSS rule 'details.current-config[open] > summary .caret "
            "{ transform: rotate(90deg); }' in workflow.html. Without it the "
            "caret will not reflect open/closed state."
        )
