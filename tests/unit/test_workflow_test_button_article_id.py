"""Regression tests for workflow agent-test button article ID handling."""

from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"


@pytest.mark.unit
def test_agent_test_buttons_await_article_id_prompt():
    """Test buttons must not pass the prompt Promise as an article ID."""
    content = WORKFLOW_TEMPLATE.read_text()

    assert "const id = promptForArticleId(2155);" not in content
    assert content.count("onclick=\"promptAndTestSubAgent('") == 7
    assert "onclick=\"promptAndTestRankAgent();\"" in content
    assert "onclick=\"promptAndTestSigmaAgent();\"" in content

    for function_name in (
        "promptAndTestSubAgent",
        "promptAndTestRankAgent",
        "promptAndTestSigmaAgent",
    ):
        function_start = content.index(f"async function {function_name}")
        function_body = content[function_start : function_start + 300]
        assert "await promptForArticleId()" in function_body
