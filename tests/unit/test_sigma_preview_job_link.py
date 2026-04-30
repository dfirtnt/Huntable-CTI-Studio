"""Regression: Sigma Rule Preview modal must show a "Job" link back to the
workflow execution that created the rule.

The link was added to renderRulePreview() in workflow.html so reviewers can
jump from the queue preview directly to the originating execution.

Invariants:
  1. The Job link is guarded by Number.isInteger(rule.workflow_execution_id)
     so rules without a linked execution show nothing, not a broken link.
  2. The link calls closeModal() before navigating so the preview is dismissed.
  3. viewExecution() is invoked with the execution id so the correct detail
     view opens in the Executions tab.
  4. The "Job:" label appears inside the content block (not elsewhere in the
     function) so it renders in the modal body.
"""

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"


@pytest.mark.unit
@pytest.mark.regression
class TestSigmaPreviewJobLink:
    @pytest.fixture(scope="class")
    def render_rule_preview_body(self) -> str:
        text = WORKFLOW_TEMPLATE.read_text()
        match = re.search(
            r"function renderRulePreview\([^)]*\)\s*\{(.*?)\nfunction ",
            text,
            re.DOTALL,
        )
        assert match, "renderRulePreview function not found in workflow.html"
        return match.group(1)

    @pytest.fixture(scope="class")
    def content_block(self, render_rule_preview_body: str) -> str:
        """Extract just the `const content = ...` template literal."""
        match = re.search(
            r"const content\s*=\s*`(.*?)`\s*;",
            render_rule_preview_body,
            re.DOTALL,
        )
        assert match, "const content template literal not found in renderRulePreview"
        return match.group(1)

    def test_job_link_guarded_by_integer_check(self, content_block: str) -> None:
        """Job link must only render when workflow_execution_id is an integer."""
        assert "Number.isInteger(rule.workflow_execution_id)" in content_block, (
            "Job link in renderRulePreview must be guarded by Number.isInteger() "
            "to avoid rendering a broken link for rules without an execution id."
        )

    def test_job_link_calls_close_modal(self, content_block: str) -> None:
        """Clicking the link must dismiss the preview modal first."""
        assert "closeModal()" in content_block, (
            "Job link onclick must call closeModal() so the preview is dismissed "
            "before navigating to the executions tab."
        )

    def test_job_link_calls_view_execution(self, content_block: str) -> None:
        """Clicking the link must open the target execution detail view."""
        assert "viewExecution(" in content_block, (
            "Job link onclick must call viewExecution() with the execution id so "
            "the correct execution is shown in the Executions tab."
        )

    def test_job_label_present(self, content_block: str) -> None:
        """The 'Job:' label must appear in the modal content block."""
        assert "Job:" in content_block, (
            "renderRulePreview content block must include a 'Job:' label so the "
            "link is clearly identified for reviewers."
        )

    def test_empty_string_fallback_when_no_execution_id(self, content_block: str) -> None:
        """When workflow_execution_id is absent the ternary must produce ''."""
        # The ternary must end with : '' to render nothing (not '-' or undefined).
        pattern = re.compile(
            r"Number\.isInteger\(rule\.workflow_execution_id\)\s*\?.*?:\s*''",
            re.DOTALL,
        )
        assert pattern.search(content_block), (
            "The workflow_execution_id ternary must fall back to empty string ('') "
            "so no placeholder text appears for older rules without an execution."
        )
