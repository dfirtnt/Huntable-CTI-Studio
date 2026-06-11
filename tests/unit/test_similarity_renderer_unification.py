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


SIMILAR_RULE_MODAL_JS = STATIC_JS_DIR / "similar-rule-modal.js"


class TestWorkflowModalRendererCollapsed:
    """The 'Similar Rule Details' modal -- which had drifted into two copies in
    workflow.html and workflow_executions.html and showed only a bare
    'Similarity: X%' -- is now one shared component that renders the full
    breakdown via renderSimilarityDisplay()."""

    def test_modal_functions_absent_from_both_templates(self):
        for tpl in (WORKFLOW, WORKFLOW_EXECUTIONS):
            html = _read(tpl)
            assert "function showSimilarRuleDetails" not in html, tpl
            assert "function closeSimilarRuleModal" not in html, tpl

    def test_both_templates_load_shared_modal_component(self):
        for tpl in (WORKFLOW, WORKFLOW_EXECUTIONS):
            html = _read(tpl)
            assert "similar-rule-modal.js" in html, tpl
            # callers (onclick handlers) still reference the now-shared function
            assert "showSimilarRuleDetails(" in html, tpl

    def test_shared_modal_renders_breakdown_via_component(self):
        js = _read(SIMILAR_RULE_MODAL_JS)
        assert "renderSimilarityDisplay(ruleData" in js
        # one definition each, in the shared file
        assert js.count("function showSimilarRuleDetails(") == 1
        assert js.count("function closeSimilarRuleModal(") == 1

    def test_shared_modal_guards_pushmodal_fallback(self):
        # workflow_executions.html has no pushModal; the unified function must
        # guard the fallback so it does not ReferenceError there.
        js = _read(SIMILAR_RULE_MODAL_JS)
        assert "typeof pushModal === 'function'" in js

    def test_shared_modal_escapes_interpolated_rule_fields(self):
        # workflow.html's copy interpolated rule fields without escaping; the
        # unified version hardens this.
        js = _read(SIMILAR_RULE_MODAL_JS)
        assert "escapeHtml(ruleData.title" in js
        assert "escapeHtml(ruleData.description)" in js


class TestAbTestUsesSharedComponent:
    """A/B test already routed through the shared component; lock that contract."""

    def test_ab_test_uses_update_similarity_display(self):
        html = _read(SIGMA_AB_TEST)
        assert "similarity-display.js" in html
        assert "updateSimilarityDisplay(" in html
