"""Phase 4 of the sigma-similarity unification: retire the hand-rolled renderers.

Template-contract tests proving every similarity surface routes through the
shared component (similarity-display.js) instead of a hand-rolled renderer:
- test page: dead embedding-breakdown block (NaN%) gone; shared component used
- queue: buildSimilarityDetailHtml / mapSimilarityResponse(FromCache) retired
- workflow + workflow-executions: showSimilarRuleDetails duplicate retired
- A/B: confirmed on the shared component

These are grep-level contract assertions (the repo convention for template
edits -- :8001 is Docker-served from the MAIN tree, so browser verification is a
post-merge step). Plan: docs/development/sigma-similarity-unification-plan-2026-06-05.md
section 6 (Phase 4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

TEMPLATES_DIR = Path("src/web/templates")
STATIC_JS_DIR = Path("src/web/static/js/components")
SIGMA_QUEUE = TEMPLATES_DIR / "sigma_queue.html"
WORKFLOW = TEMPLATES_DIR / "workflow.html"
WORKFLOW_EXECUTIONS = TEMPLATES_DIR / "workflow_executions.html"
SIGMA_SIMILARITY_TEST = TEMPLATES_DIR / "sigma_similarity_test.html"
SIGMA_AB_TEST = TEMPLATES_DIR / "sigma_ab_test.html"


def _read(path: Path) -> str:
    assert path.exists(), f"File not found: {path}"
    return path.read_text(encoding="utf-8")


class TestSigmaSimilarityTestPageRenderer:
    """The test page must drop the dead embedding-era breakdown block (which
    read fields the behavioral engine never returns -> literal NaN%) and render
    the real metrics via the shared component."""

    def test_dead_embedding_breakdown_block_removed(self):
        html = _read(SIGMA_SIMILARITY_TEST)
        # These read breakdown.title/.description/.tags/.signature, which the
        # backend never returns -> '(undefined * 100).toFixed(1)' === 'NaN'.
        assert "breakdown.title" not in html
        assert "breakdown.description" not in html
        assert "breakdown.signature" not in html
        assert "Embedding Similarity Breakdown" not in html

    def test_uses_shared_renderer_for_metrics(self):
        html = _read(SIGMA_SIMILARITY_TEST)
        assert "similarity-display.js" in html
        assert "renderSimilarityDisplay(" in html
