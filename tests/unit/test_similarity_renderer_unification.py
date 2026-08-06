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

from tests.utils.workflow_html_source import read_workflow_src

pytestmark = [pytest.mark.unit]

TEMPLATES_DIR = Path("src/web/templates")
STATIC_JS_DIR = Path("src/web/static/js/components")
WORKFLOW = TEMPLATES_DIR / "workflow.html"
SIGMA_SIMILARITY_TEST = TEMPLATES_DIR / "sigma_similarity_test.html"
SIGMA_AB_TEST = TEMPLATES_DIR / "sigma_ab_test.html"


def _read(path: Path) -> str:
    assert path.exists(), f"File not found: {path}"
    if path == WORKFLOW:
        # workflow.html's inline script was split into src/web/static/js/workflow/*.js
        # modules (loaded back in via <script src>); include them so substring
        # checks still find content that moved out of the template.
        return read_workflow_src()
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
        for tpl in (WORKFLOW,):
            html = _read(tpl)
            assert "function showSimilarRuleDetails" not in html, tpl
            assert "function closeSimilarRuleModal" not in html, tpl

    def test_both_templates_load_shared_modal_component(self):
        for tpl in (WORKFLOW,):
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


class TestSigmaQueueRendererRetired:
    """The queue detail pane no longer hand-rolls the metric/atom rendering; the
    remap layer is retired and matches flow canonically into the shared
    component, with only queue-specific YAML/source chrome kept."""

    def test_hand_rolled_renderer_and_remap_retired(self):
        html = _read(WORKFLOW)
        assert "buildSimilarityDetailHtml" not in html
        assert "mapSimilarityResponse" not in html  # covers FromCache too
        assert "renderSimilarityDisplay(" in html


ARTICLE_DETAIL = TEMPLATES_DIR / "article_detail.html"
SIGMA_SIMILARITY_TEST_ROUTE = Path("src/web/routes/sigma_similarity_test.py")
SERIALIZER = Path("src/services/similarity_serialization.py")


class TestPhase5CleanupVestiges:
    """Phase 5: legacy aliases retired, embedding vestiges removed, the #sigma
    similarity render re-homed onto the shared component (kept, not deleted --
    the modal is still reachable via the #sigma URL fragment)."""

    # Surfaces that previously read the raw singular aliases.
    _ALIAS_SURFACES = (SIGMA_AB_TEST, WORKFLOW, ARTICLE_DETAIL, SIGMA_SIMILARITY_TEST)

    def test_no_surface_template_reads_singular_legacy_aliases(self):
        # The DB cache column is `similarity_scores` (plural) -- not an alias.
        # The defensive adapter in similarity-display.js may keep reading them,
        # but no surface template may.
        for tpl in self._ALIAS_SURFACES:
            html = _read(tpl)
            assert "match.similarity_score" not in html, tpl
            assert "match.similarity_breakdown" not in html, tpl

    def test_serializer_emits_canonical_only(self):
        src = _read(SERIALIZER)
        # No emitted alias keys (docstring mention is fine; the dict literal is not).
        assert '"similarity_score": similarity' not in src
        assert '"similarity_breakdown":' not in src

    def test_embedding_model_param_and_label_removed(self):
        route = _read(SIGMA_SIMILARITY_TEST_ROUTE)
        assert "embedding_model" not in route
        assert "behavioral-novelty-engine" not in route
        html = _read(SIGMA_SIMILARITY_TEST)
        assert "embedding_model" not in html
        assert 'id="embeddingModel"' not in html

    def test_sigma_similarity_test_still_renders_via_shared_component(self):
        # Re-home sanity: the page still uses the shared renderer (Phase 4) and
        # the LLM rerank dropdown survives the embedding-picker removal.
        html = _read(SIGMA_SIMILARITY_TEST)
        assert "renderSimilarityDisplay(" in html
        assert 'id="llmModel"' in html

    def test_article_detail_sigma_render_uses_canonical_fields(self):
        # #sigma modal kept (reachable via fragment) but its similarity render
        # is re-homed: reads canonical match.similarity / atom_jaccard, not aliases.
        html = _read(ARTICLE_DETAIL)
        assert "match.atom_jaccard !== undefined ? renderSimilarityDisplay" in html
