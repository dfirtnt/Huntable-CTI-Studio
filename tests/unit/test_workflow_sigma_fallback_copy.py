"""Regression tests for SIGMA full-article fallback UI copy in workflow.html."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WORKFLOW_TEMPLATE = Path("src/web/templates/workflow.html")


def test_sigma_fallback_helper_text_describes_article_and_grouped_observables() -> None:
    html = WORKFLOW_TEMPLATE.read_text(encoding="utf-8")

    assert "Extracted observables, if any, are still included in the prompt either way." not in html
    assert (
        "When enabled, SIGMA reviews the junk-filtered article alongside Sigma-eligible extracted "
        "observables for the current detection category. This lets it create rules grounded in the "
        "extracted evidence and identify additional relevant behavior in the article."
    ) in html
