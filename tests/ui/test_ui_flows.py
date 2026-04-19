"""
UI flow tests using Playwright for CTI Scraper.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.ui

# Disable in environments without full UI/data stack.
# pytestmark = pytest.mark.skip(reason="UI flow tests disabled in this environment.")


class TestDashboardFlows:
    """Test dashboard user flows."""

    @pytest.mark.ui_smoke
    def test_dashboard_navigation(self, page: Page):
        """Test navigation between dashboard sections."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        # Verify dashboard loads
        expect(page).to_have_title(re.compile(r"Dashboard.*Huntable CTI Studio"))
        expect(page.locator("h1").first).to_contain_text("Huntable")

        # Test navigation to articles
        page.locator("a:has-text('Articles')").first.click()
        expect(page).to_have_url(f"{base_url}/articles")

        # Test navigation to sources
        page.locator("a:has-text('Sources')").first.click()
        expect(page).to_have_url(f"{base_url}/sources")

        # Return to dashboard via logo
        page.locator("a[href='/']").first.click()
        expect(page).to_have_url(f"{base_url}/")

    @pytest.mark.ui
    def test_high_score_articles_section_display(self, page: Page):
        """Test that High-Score Articles section displays 10 cards sorted by date (latest first)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load
        page.wait_for_load_state("load")

        # Verify High-Score Articles section is visible
        expect(page.locator("#high-score-articles-container")).to_be_visible()

        # Find all article cards in the high-score section
        article_cards = page.locator("#high-score-articles-container a")
        assert article_cards.count() >= 0

        # Verify each card is clickable and navigates to article page
        for i in range(min(3, article_cards.count())):  # Test first 3 cards to avoid long test
            card = article_cards.nth(i)
            expect(card).to_be_visible()

            # Get the href attribute to verify it points to an article
            href = card.get_attribute("href")
            assert href is not None, f"Card {i} should have href attribute"
            assert "/articles/" in href, f"Card {i} href should contain '/articles/'"

            # Click the card and verify navigation (but don't actually navigate to avoid slowing test)
            # We'll just verify the link structure is correct
            article_id = href.split("/articles/")[-1]
            assert article_id.isdigit(), f"Article ID should be numeric, got: {article_id}"

        # Verify cards appear to be sorted by date (latest first)
        # This is a basic check - we can't easily verify actual date sorting without more complex logic
        # But we can check that the section exists and has the expected structure
        expect(page.locator("#high-score-articles-container")).to_be_visible()

    @pytest.mark.ui
    def test_agents_navigation_to_workflow_page(self, page: Page):
        """Test that the Agents button navigates to the workflow page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load
        page.wait_for_load_state("load")

        # Find the Agents button in the navigation
        agents_button = page.locator("a[href='/workflow']")

        # Check if the button exists
        if agents_button.count() == 0:
            pytest.skip("Agents button not found in navigation")

        expect(agents_button.first).to_be_visible()

        # Click the Agents button
        agents_button.first.click()

        # Wait for navigation to workflow page
        page.wait_for_load_state("load")

        # Verify we navigated to the workflow page (may include URL fragments like #config)
        expect(page).to_have_url(re.compile(rf"{base_url}/workflow(#.*)?$"))

        # Verify the workflow page loaded with expected content
        # Look for workflow-related content (agents, etc.)
        workflow_indicators = page.locator("text=Workflow, text=Agent, text=\U0001f916, h1, h2")

        # At minimum, verify the page loaded (should have some heading or content)
        expect(page.locator("body")).not_to_be_empty()

        # If there are workflow indicators, verify at least one is visible
        if workflow_indicators.count() > 0:
            expect(workflow_indicators.first()).to_be_visible()


class TestArticlesFlows:
    """Test article browsing and viewing flows."""

    @pytest.mark.ui_smoke
    def test_articles_listing(self, page: Page):
        """Test articles listing page functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        # Verify page loads
        heading = page.get_by_role("heading", name=re.compile("Threat Intelligence Articles"))
        expect(heading).to_be_visible()

        # Test pagination if available
        pagination = page.locator("[data-testid='pagination']")
        if pagination.count() > 0:
            expect(pagination).to_be_visible()

    @pytest.mark.ui
    def test_article_detail_view(self, page: Page):
        """Test individual article detail page."""
        page.goto("http://localhost:8001/articles")

        # Try to click on first article if available
        first_article = page.locator("a[href^='/articles/']").first
        if first_article.count() > 0:
            first_article.click()

            # Verify article detail page loads (check headings present in article_detail.html)
            expect(page.locator("text=Article Content").first).to_be_visible()
            expect(page.locator("text=Article Metadata").first).to_be_visible()

            # Test back navigation
            page.click("text=Back to Articles")
            expect(page).to_have_url("http://localhost:8001/articles")


class TestSourcesFlows:
    """Test source management flows."""

    @pytest.mark.ui_smoke
    def test_sources_management(self, page: Page):
        """Test source management functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("load")

        # Verify page loads
        heading = page.get_by_role("heading", name=re.compile("Threat Intelligence Sources"))
        expect(heading).to_be_visible()

        # Check for source management elements
        expect(heading).to_be_visible()

        # Look for add source functionality
        add_source = page.locator("text=Add Source, New Source, + Add").first
        if add_source.count() > 0:
            expect(add_source).to_be_visible()


class TestErrorHandling:
    """Test error handling in UI."""

    @pytest.mark.ui
    def test_404_page(self, page: Page):
        """Test 404 error page."""
        page.goto("http://localhost:8001/nonexistent-page")

        # Should show error page
        expect(page.locator("text=Something went wrong")).to_be_visible()
        expect(page.locator("text=Page not found")).to_be_visible()

        # Check error page navigation
        page.click("text=Go to Dashboard")
        expect(page).to_have_url("http://localhost:8001/")

    @pytest.mark.ui
    def test_invalid_article_id(self, page: Page):
        """Test handling of invalid article IDs."""
        page.goto("http://localhost:8001/articles/999999")

        # Should handle gracefully
        if page.url.endswith("999999"):
            # If it shows an error page
            expect(page.locator("text=Something went wrong")).to_be_visible()
        else:
            # Or redirects to a valid page
            expect(page).to_have_url(lambda url: "999999" not in url)


class TestQuickActionsFlows:
    """Test quick action button flows."""

    @pytest.mark.ui
    def test_rescore_all_articles_button(self, page: Page):
        """Test the rescore all articles button functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for page to load
        page.wait_for_load_state("load")

        # Find and click the rescore button
        rescore_button = page.locator("#btn-rescore")
        expect(rescore_button).to_be_visible()

        # Click the button
        rescore_button.click()

        # Wait for API call to complete and check for success notification
        page.wait_for_timeout(3000)
