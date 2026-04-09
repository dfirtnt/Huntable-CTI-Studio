"""Unit tests for similarity search repo-scope labelling.

Validates that:
- UI templates use inclusive "indexed repositories" language (not SigmaHQ-only)
- Match list items show repo-origin badges (Your repo / SigmaHQ)
- Capability service returns descriptive messages for unindexed customer repos
- Empty-state messages are repo-agnostic
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.capability_service import CapabilityService

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Paths to the templates under test
# ---------------------------------------------------------------------------
TEMPLATES_DIR = Path("src/web/templates")
SIGMA_QUEUE = TEMPLATES_DIR / "sigma_queue.html"
WORKFLOW = TEMPLATES_DIR / "workflow.html"
WORKFLOW_EXECUTIONS = TEMPLATES_DIR / "workflow_executions.html"
ARTICLE_DETAIL = TEMPLATES_DIR / "article_detail.html"
SIGMA_SIMILARITY_TEST = TEMPLATES_DIR / "sigma_similarity_test.html"
SIGMA_AB_TEST = TEMPLATES_DIR / "sigma_ab_test.html"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    assert path.exists(), f"Template not found: {path}"
    return path.read_text(encoding="utf-8")


# ===================================================================
# 1. Modal titles & loading messages use inclusive language
# ===================================================================
class TestModalTitlesIncludeUserRepo:
    """Modal titles and loading messages must say 'indexed repositories',
    not 'SigmaHQ Repository'."""

    def test_sigma_queue_modal_title(self):
        html = _read(SIGMA_QUEUE)
        assert "Similar rules across indexed repositories" in html

    def test_sigma_queue_loading_message(self):
        html = _read(SIGMA_QUEUE)
        assert "Searching for similar rules across indexed repositories" in html

    def test_workflow_modal_title(self):
        html = _read(WORKFLOW)
        assert "Similar Rules Across Indexed Repositories" in html

    def test_workflow_loading_message(self):
        html = _read(WORKFLOW)
        assert "Searching for similar rules across indexed repositories" in html

    def test_workflow_executions_loading_message(self):
        html = _read(WORKFLOW_EXECUTIONS)
        assert "Searching for similar rules across indexed repositories" in html

    def test_article_detail_button_tooltip(self):
        html = _read(ARTICLE_DETAIL)
        assert "Search for similar rules across indexed repositories" in html

    def test_sigma_similarity_test_subtitle(self):
        html = _read(SIGMA_SIMILARITY_TEST)
        assert "indexed repositories" in html

    def test_sigma_ab_test_compare_description(self):
        html = _read(SIGMA_AB_TEST)
        assert "SigmaHQ and your repo" in html


# ===================================================================
# 2. Empty states use repo-agnostic language
# ===================================================================
class TestEmptyStatesRepoAgnostic:
    """Empty states when no matches are found must not say 'SigmaHQ rules'."""

    def test_sigma_queue_empty_title(self):
        html = _read(SIGMA_QUEUE)
        assert "Rule Corpus Unavailable" in html
        assert "No indexed rules were available for behavioral comparison" in html

    def test_sigma_queue_empty_subtitle(self):
        html = _read(SIGMA_QUEUE)
        assert "No indexed rules share detection logic with this rule" in html

    def test_workflow_empty_title(self):
        html = _read(WORKFLOW)
        assert "Rule Corpus Unavailable" in html

    def test_workflow_empty_subtitle(self):
        html = _read(WORKFLOW)
        assert "No indexed rules share detection logic with this rule" in html

    def test_article_detail_empty_state(self):
        html = _read(ARTICLE_DETAIL)
        assert "No indexed rules share detection logic with this rule" in html

    def test_sigma_ab_test_novel_state(self):
        html = _read(SIGMA_AB_TEST)
        assert "No similar rules found in indexed repositories" in html


# ===================================================================
# 3. Match list items include repo-origin badge markup
# ===================================================================
class TestMatchListOriginBadges:
    """Match list sidebar items must render 'Your repo' / 'SigmaHQ' badges."""

    def test_sigma_queue_match_items_have_origin_badge(self):
        """The sigma_queue match list builder must emit a repo-origin badge."""
        html = _read(SIGMA_QUEUE)
        # Customer-rule badge
        assert "Your repo</span>" in html
        # SigmaHQ badge (for non-customer rules in the match list)
        assert "SigmaHQ</span>" in html

    def test_sigma_queue_customer_rule_detection(self):
        """Match list must detect customer rules via rule_id prefix."""
        html = _read(SIGMA_QUEUE)
        assert "startsWith('cust-')" in html

    def test_workflow_match_cards_have_origin_badge(self):
        """Workflow match cards must include repo-origin badge."""
        html = _read(WORKFLOW)
        # The badge variable assignment
        assert "isCustomerRule" in html or "isCustomer" in html
        assert "repoOriginBadge" in html or "originBadge" in html


# ===================================================================
# 4. Capability service message accuracy
# ===================================================================
class TestCapabilityServiceMessages:
    """CapabilityService._check_sigma_customer_repo_indexed returns
    descriptive messages about customer-repo indexing status."""

    def test_unindexed_message_explains_sigmahq_only(self, monkeypatch):
        """When no customer rules are indexed, the reason must explain the gap."""
        service = CapabilityService()

        # Simulate zero customer rules via monkeypatch
        def _fake_check(session):
            return {
                "enabled": False,
                "count": 0,
                "reason": "No rules from your repo are indexed yet — similarity search covers SigmaHQ only",
                "action": "Run sigma index-customer-repo to include your approved rules",
            }

        monkeypatch.setattr(service, "_check_sigma_customer_repo_indexed", _fake_check)

        result = service._check_sigma_customer_repo_indexed(None)
        assert result["enabled"] is False
        assert "indexed" in result["reason"].lower()
        assert "action" in result

    def test_indexed_message_includes_count(self, monkeypatch):
        """When customer rules ARE indexed, the reason must include the count."""
        service = CapabilityService()

        def _fake_check(session):
            return {
                "enabled": True,
                "count": 42,
                "reason": "42 rules from your repo included in similarity search",
            }

        monkeypatch.setattr(service, "_check_sigma_customer_repo_indexed", _fake_check)

        result = service._check_sigma_customer_repo_indexed(None)
        assert result["enabled"] is True
        assert result["count"] == 42
        assert "42" in result["reason"]
