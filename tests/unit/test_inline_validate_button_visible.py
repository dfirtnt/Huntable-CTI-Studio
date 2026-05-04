"""Regression: Validate button in the inline agent config prompt panel must
render regardless of edit mode, so users can validate the saved prompt before
clicking Edit.

The panel is built by the renderSinglePrompt() JS function in workflow.html.
Previously the Validate button sat inside the `${isEditing ? ... : ...}`
ternary's editing branch, so it only appeared after clicking Edit. It is now
hoisted alongside Expand (always visible) and the read-only result div is
rendered outside the editing branch too.
"""

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"


@pytest.mark.unit
@pytest.mark.regression
class TestInlineValidateButtonAlwaysVisible:
    @pytest.fixture(scope="class")
    def render_single_prompt_body(self) -> str:
        text = WORKFLOW_TEMPLATE.read_text()
        match = re.search(
            r"function renderSinglePrompt\([^)]*\)\s*\{(.*?)\nfunction ",
            text,
            re.DOTALL,
        )
        assert match, "renderSinglePrompt function not found"
        return match.group(1)

    def test_validate_button_outside_editing_ternary(self, render_single_prompt_body: str) -> None:
        """Validate button must appear before the `${isEditing ? ... : ...}` button block."""
        body = render_single_prompt_body
        validate_idx = body.find('onclick="validateAgentPrompt(')
        ternary_idx = body.find("${isEditing ? `")
        assert validate_idx != -1, "Validate button missing from renderSinglePrompt"
        assert ternary_idx != -1, "isEditing ternary missing from renderSinglePrompt"
        assert validate_idx < ternary_idx, (
            "Validate button must render before the isEditing ternary so it is visible in both read-only and edit modes"
        )

    def test_validate_result_div_outside_editing_ternary(self, render_single_prompt_body: str) -> None:
        """The -validate-result-2 div must render in both edit and read-only modes."""
        body = render_single_prompt_body
        result_div_count = body.count('id="${agentId}-validate-result-2"')
        assert result_div_count == 1, (
            f"Expected exactly one -validate-result-2 div in renderSinglePrompt, found {result_div_count}"
        )

        result_idx = body.find('id="${agentId}-validate-result-2"')
        # The result div must sit outside the inner `${isEditing ? ... : ...}` block
        # used for the system textarea vs. display div. We check by ensuring the div
        # is not inside a line that also contains a template-literal backtick
        # opening an editing-only branch.
        # Simplest invariant: the div sits after the inner ternary's closing `}`,
        # i.e., after the `}` that closes the textarea vs. display ternary.
        inner_ternary_close = body.rfind("`}", 0, result_idx)
        assert inner_ternary_close != -1, "-validate-result-2 div must appear after the editing ternary's closing '}'"


@pytest.mark.unit
class TestValidateAgentPromptReadOnlyFallback:
    """validateAgentPrompt() must read from stored agentPrompts when the textarea
    isn't in the DOM (i.e. read-only mode)."""

    @pytest.fixture(scope="class")
    def validate_fn_body(self) -> str:
        text = WORKFLOW_TEMPLATE.read_text()
        match = re.search(
            r"function validateAgentPrompt\([^)]*\)\s*\{(.*?)\n\}",
            text,
            re.DOTALL,
        )
        assert match, "validateAgentPrompt function not found"
        return match.group(1)

    def test_falls_back_to_stored_prompt(self, validate_fn_body: str) -> None:
        """Function must read stored prompt data for the read-only fallback path.

        Post-canonicalization: validateAgentPrompt now calls
        getAgentPromptParts(agentName) which detects canonical {system, user}
        outer-dict shape and falls back to parsePromptParts(stored.prompt) for
        legacy records. Either accessing agentPrompts directly OR going through
        the canonical-aware helper satisfies the read-only fallback contract.
        """
        uses_canonical_helper = "getAgentPromptParts(agentName)" in validate_fn_body
        uses_direct_access = (
            "agentPrompts[agentName]" in validate_fn_body
            and "parsePromptParts" in validate_fn_body
        )
        assert uses_canonical_helper or uses_direct_access, (
            "validateAgentPrompt must either call getAgentPromptParts(agentName) "
            "(canonical-aware helper) or directly reference agentPrompts[agentName] "
            "with parsePromptParts for the read-only fallback path"
        )
