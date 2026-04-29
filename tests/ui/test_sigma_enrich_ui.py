"""UI tests for SIGMA rule enrichment functionality."""

import json
import os

import pytest
from playwright.sync_api import Page, expect

# Minimal queued rule so tests don't skip when queue is empty (fixture mocks list API).
_SIGMA_QUEUE_LIST_MOCK = [
    {
        "id": 1,
        "article_id": 1,
        "article_title": "Test Article",
        "workflow_execution_id": None,
        "rule_yaml": "title: Test Rule\ndetection:\n  condition: true\n",
        "rule_metadata": {"title": "Test Rule"},
        "similarity_scores": [],
        "max_similarity": 0.5,
        "status": "pending",
        "reviewed_by": None,
        "review_notes": None,
        "pr_submitted": False,
        "pr_url": None,
        "created_at": "2024-01-01T12:00:00",
        "reviewed_at": None,
    }
]


@pytest.mark.ui
@pytest.mark.sigma
class TestSigmaEnrichUI:
    """Test SIGMA rule enrichment UI functionality."""

    @pytest.fixture(autouse=True)
    def mock_sigma_queue_list(self, page: Page):
        """Mock sigma queue list API so table has one rule (avoids 'No rules in queue to test' skip)."""

        def handle(route):
            if "/api/sigma-queue/list" in route.request.url:
                route.fulfill(
                    status=200,
                    body=json.dumps(
                        {
                            "items": _SIGMA_QUEUE_LIST_MOCK,
                            "total": len(_SIGMA_QUEUE_LIST_MOCK),
                            "limit": 50,
                            "offset": 0,
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list**", handle)
        yield

    @pytest.fixture(autouse=True)
    def setup(self, page: Page, mock_sigma_queue_list):
        """Setup: Navigate to workflow Queue tab (after list mock is applied).

        The standalone /sigma-queue page was removed; queue lives in /workflow#queue.
        """
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow#queue")
        page.wait_for_load_state("networkidle")
        yield
        # Close any modals left open so the next test in this class starts clean.
        # The class-scoped page is reused across tests and goto is deduplicated,
        # so in-page modal state persists between tests without this teardown.
        try:
            page.evaluate(
                "() => { ['ruleModal','enrichModal'].forEach(id => {"
                " const el = document.getElementById(id); if (el) el.classList.add('hidden'); }); }"
            )
        except Exception:
            pass

    def test_sigma_queue_page_shows_pagination_bar(self, page: Page):
        """Workflow Queue tab shows pagination bar with Showing X-Y of Z."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        bar = page.locator("#queuePaginationBar")
        expect(bar).to_be_visible(timeout=5000)
        expect(bar).to_contain_text("Showing", timeout=10000)
        expect(bar).to_contain_text("of ")

    def test_enrich_button_visible_in_rule_modal(self, page: Page):
        """Test that Enrich button is visible in rule preview modal."""
        # Wait for actual rule rows (Preview button appears only once data is rendered)
        preview_button = page.locator('#queueTableBody button:has-text("Preview")').first
        if not preview_button.is_visible(timeout=10000):
            pytest.skip("No rules in queue to test")

        preview_button.click()

        # Wait for rule modal to open (hidden class removed)
        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=5000)

        # Check for Enrich button (may have emoji prefix depending on template version)
        enrich_button = page.locator('#ruleModal button:has-text("Enrich")')
        expect(enrich_button).to_be_visible(timeout=2000)

    def _open_preview_then_enrich(self, page: Page):
        """Helper: open rule preview modal and click the Enrich button.

        Returns (rule_modal locator, enrich_modal locator) or calls pytest.skip.
        """
        preview_button = page.locator('#queueTableBody button:has-text("Preview")').first
        if not preview_button.is_visible(timeout=10000):
            pytest.skip("No rules in queue to test")

        preview_button.click()

        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=5000)

        enrich_button = page.locator('#ruleModal button:has-text("Enrich")').first
        enrich_button.click()

        enrich_modal = page.locator("#enrichModal")
        expect(enrich_modal).to_be_visible(timeout=5000)
        return rule_modal, enrich_modal

    def test_enrich_modal_opens(self, page: Page):
        """Test that enrich modal opens when enrich button is clicked."""
        _rule_modal, enrich_modal = self._open_preview_then_enrich(page)
        # Modal visible confirmed inside helper; verify hidden class removed
        expect(enrich_modal).not_to_have_class("hidden")

    def test_enrich_modal_contains_required_elements(self, page: Page):
        """Test that enrich modal contains all required UI elements."""
        self._open_preview_then_enrich(page)

        # Check for required elements
        expect(page.locator("#enrichOriginalRule")).to_be_visible()
        expect(page.locator("#enrichInstruction")).to_be_visible()
        expect(page.locator("#enrichBtn")).to_be_visible()
        expect(page.locator('#enrichModal button:has-text("Cancel")')).to_be_visible()

    def test_enrich_modal_closes_on_cancel(self, page: Page):
        """Test that enrich modal closes when cancel button is clicked."""
        _rule_modal, enrich_modal = self._open_preview_then_enrich(page)

        cancel_button = page.locator('#enrichModal button:has-text("Cancel")')
        cancel_button.click()

        # Modal should be hidden; use not_to_be_visible() because the element
        # retains its full multi-class string (e.g. "fixed inset-0 ... hidden")
        # and to_have_class("hidden") would do an exact match, not a token check.
        expect(enrich_modal).not_to_be_visible(timeout=2000)

    def test_enrich_modal_closes_on_escape(self, page: Page):
        """Test that enrich modal closes when Escape key is pressed."""
        _rule_modal, enrich_modal = self._open_preview_then_enrich(page)

        page.keyboard.press("Escape")

        # Modal should be hidden (see cancel test for why not_to_be_visible is used)
        expect(enrich_modal).not_to_be_visible(timeout=2000)

    def test_enrich_modal_populates_original_rule(self, page: Page):
        """Test that enrich modal populates with original rule YAML."""
        self._open_preview_then_enrich(page)

        original_rule_textarea = page.locator("#enrichOriginalRule")
        expect(original_rule_textarea).to_be_visible()

        original_yaml = original_rule_textarea.input_value()
        assert len(original_yaml) > 0, "Original rule YAML should be populated"

    def test_enrich_modal_shows_error_on_api_failure(self, page: Page):
        """Test that enrich modal shows error when API call fails."""
        page.route(
            "**/api/sigma-queue/*/enrich",
            lambda route: route.fulfill(
                status=500, content_type="application/json", body='{"error": "Internal server error"}'
            ),
        )

        self._open_preview_then_enrich(page)

        enrich_rule_button = page.locator("#enrichBtn")
        enrich_rule_button.click()

        # Wait for error to appear
        enrich_error = page.locator("#enrichError")
        expect(enrich_error).to_be_visible(timeout=10000)
        expect(enrich_error).not_to_have_class("hidden")

        error_text = enrich_error.text_content()
        assert error_text is not None
        assert len(error_text) > 0

    def test_enrich_button_disabled_during_enrichment(self, page: Page):
        """Test that enrich button is disabled during enrichment process."""

        import threading

        def slow_response(route):
            # Use a background thread so the Playwright event loop is not blocked.
            # time.sleep() inside a route handler blocks the event loop, preventing
            # subsequent Playwright calls (like text_content()) from executing until
            # after the sleep completes -- by which point the button has already reset.
            def _fulfill():
                import time

                time.sleep(2)
                try:
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"enriched_yaml": "title: Test Rule", "message": "Success"}',
                    )
                except Exception:
                    pass

            threading.Thread(target=_fulfill, daemon=True).start()

        page.route("**/api/sigma-queue/*/enrich", slow_response)

        self._open_preview_then_enrich(page)

        enrich_rule_button = page.locator("#enrichBtn")
        enrich_rule_button.click()

        # Check that button is disabled while request is in flight
        expect(enrich_rule_button).to_be_disabled(timeout=3000)

        # Check for loading indicator text (readable because event loop is not blocked)
        button_text = enrich_rule_button.text_content()
        assert "Enriching" in button_text or "..." in button_text
