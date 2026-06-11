"""Regression tests for SIGMA full-article fallback UI copy in workflow.html."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WORKFLOW_TEMPLATE = Path("src/web/templates/workflow.html")


def test_sigma_fallback_helper_text_describes_main_content_block_not_observables() -> None:
    html = WORKFLOW_TEMPLATE.read_text(encoding="utf-8")

    assert "If enabled, SIGMA uses junk-filtered article content instead of extracted observables summary." not in html
    assert (
        "If enabled, SIGMA uses the junk-filtered full article as the main content block "
        "instead of the extracted-artifact summary. Extracted observables, if any, are still "
        "included in the prompt either way."
    ) in html
