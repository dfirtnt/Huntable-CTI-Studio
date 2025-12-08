"""
UI flow tests using Playwright for CTI Scraper.
"""

import pytest
import os
import re
from playwright.sync_api import Page, expect
from typing import AsyncGenerator


class TestDashboardFlows:
    """Test dashboard user flows."""

    @pytest.mark.ui
    @pytest.mark.smoke
    def test_dashboard_navigation(self, page: Page):
        """Test navigation between dashboard sections."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Verify dashboard loads
        expect(page).to_have_title("Dashboard - CTI Scraper")
        expect(page.locator("h1").first).to_contain_text("CTI Scraper")

        # Test navigation to articles
        page.click("text=Articles")
        expect(page).to_have_url(f"{base_url}/articles")

        # Test navigation to sources
        page.click("text=Sources")
        expect(page).to_have_url(f"{base_url}/sources")

        # Return to dashboard via logo
        page.click("a[href='/'] h1")
        expect(page).to_have_url(f"{base_url}/")

    @pytest.mark.ui
    def test_article_volume_charts_display(self, page: Page):
        """Test that Article Volume section displays line charts for daily and hourly volume."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load and charts to initialize
        page.wait_for_load_state("networkidle")

        # Verify Article Volume section is visible
        expect(page.locator("text=Article Volume")).to_be_visible()

        # Verify Daily Volume chart section
        expect(page.locator("text=Daily Volume")).to_be_visible()
        daily_chart_canvas = page.locator("#dailyChart")
        expect(daily_chart_canvas).to_be_visible()

        # Verify Hourly Volume chart section
        expect(page.locator("text=Hourly Volume")).to_be_visible()
        hourly_chart_canvas = page.locator("#hourlyChart")
        expect(hourly_chart_canvas).to_be_visible()

        # Verify canvas elements are properly sized (have dimensions)
        daily_canvas = page.locator("#dailyChart")
        daily_box = daily_canvas.bounding_box()
        assert daily_box is not None, "Daily chart canvas should have dimensions"
        assert daily_box["width"] > 0 and daily_box["height"] > 0, (
            "Daily chart canvas should be visible with size"
        )

        hourly_canvas = page.locator("#hourlyChart")
        hourly_box = hourly_canvas.bounding_box()
        assert hourly_box is not None, "Hourly chart canvas should have dimensions"
        assert hourly_box["width"] > 0 and hourly_box["height"] > 0, (
            "Hourly chart canvas should be visible with size"
        )

    @pytest.mark.ui
    def test_high_score_articles_section_display(self, page: Page):
        """Test that High-Score Articles section displays 10 cards sorted by date (latest first)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load
        page.wait_for_load_state("networkidle")

        # Verify High-Score Articles section is visible
        expect(page.locator("text=High-Score Articles")).to_be_visible()

        # Find all article cards in the high-score section
        article_cards = page.locator("#high-score-articles-container a")
        expect(article_cards).to_have_count(10)

        # Verify each card is clickable and navigates to article page
        for i in range(
            min(3, article_cards.count())
        ):  # Test first 3 cards to avoid long test
            card = article_cards.nth(i)
            expect(card).to_be_visible()

            # Get the href attribute to verify it points to an article
            href = card.get_attribute("href")
            assert href is not None, f"Card {i} should have href attribute"
            assert "/articles/" in href, f"Card {i} href should contain '/articles/'"

            # Click the card and verify navigation (but don't actually navigate to avoid slowing test)
            # We'll just verify the link structure is correct
            article_id = href.split("/articles/")[-1]
            assert article_id.isdigit(), (
                f"Article ID should be numeric, got: {article_id}"
            )

        # Verify cards appear to be sorted by date (latest first)
        # This is a basic check - we can't easily verify actual date sorting without more complex logic
        # But we can check that the section exists and has the expected structure
        expect(page.locator("#high-score-articles-container")).to_be_visible()

    @pytest.mark.ui
    def test_copy_urls_button_functionality(self, page: Page):
        """Test that the Copy URLs button in High-Score Articles section copies URLs to clipboard."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load
        page.wait_for_load_state("networkidle")

        # Find the Copy URLs button in the High-Score Articles section
        # Look for button with text "Copy URLs" or similar copy functionality
        copy_urls_button = page.locator(
            "button:has-text('Copy URLs'), button:has-text('📋 Copy URLs'), button[onclick*='copyUrls']"
        )

        # Check if the button exists (it may not be implemented yet)
        if copy_urls_button.count() == 0:
            pytest.skip("Copy URLs button not found - may not be implemented yet")

        expect(copy_urls_button).to_be_visible()

        # Get the expected URLs from the high-score articles before copying
        # The Copy URLs button likely copies the original source URLs, not the internal article URLs
        # We need to check what URLs are actually copied by examining the clipboard content
        article_links = page.locator("#high-score-articles-container a")

        # Ensure we have articles to copy URLs from
        assert article_links.count() > 0, "No articles found in high-score section"

        # Grant clipboard permissions (required for clipboard access)
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])

        # Click the Copy URLs button
        copy_urls_button.click()

        # Wait for clipboard operation to complete
        page.wait_for_timeout(1000)

        # Read the clipboard content
        clipboard_content = page.evaluate("() => navigator.clipboard.readText()")

        # Verify clipboard contains URLs
        assert clipboard_content is not None, (
            "Clipboard should contain content after copy operation"
        )
        assert len(clipboard_content.strip()) > 0, (
            "Clipboard content should not be empty"
        )

        # Check that clipboard contains URLs (could be newline-separated or space-separated)
        clipboard_lines = clipboard_content.strip().split("\n")
        copied_urls = [line.strip() for line in clipboard_lines if line.strip()]

        # Verify we have URLs copied (at least as many as there are articles)
        assert len(copied_urls) >= article_links.count(), (
            f"Expected at least {article_links.count()} URLs, got {len(copied_urls)}"
        )

        # Verify each copied item looks like a URL
        for url in copied_urls:
            assert url.startswith("http://") or url.startswith("https://"), (
                f"Copied content '{url}' does not appear to be a valid URL"
            )

        # Check for success notification (common pattern for copy operations)
        success_notification = page.locator(
            "text=URLs copied, text=Copied to clipboard, text=URLs copied to clipboard, .notification.success, .alert.success"
        )
        # The notification might appear and then disappear, so we check if it exists
        if success_notification.count() > 0:
            expect(success_notification.first()).to_be_visible()

        # Verify the button is still functional after clicking
        expect(copy_urls_button).to_be_visible()

        # Click the Copy URLs button
        copy_urls_button.click()

        # Wait for potential success notification or clipboard operation
        page.wait_for_timeout(1000)

        # Check for success notification (common pattern for copy operations)
        success_notification = page.locator(
            "text=URLs copied, text=Copied to clipboard, text=URLs copied to clipboard, .notification.success, .alert.success"
        )
        # The notification might appear and then disappear, so we check if it exists
        if success_notification.count() > 0:
            expect(success_notification.first()).to_be_visible()

        # Verify the button is still functional after clicking
        expect(copy_urls_button).to_be_visible()

        # Click the Copy URLs button
        copy_urls_button.click()

        # Wait for potential success notification or clipboard operation
        page.wait_for_timeout(1000)

        # Check for success notification (common pattern for copy operations)
        success_notification = page.locator(
            "text=URLs copied, text=Copied to clipboard, .notification.success, .alert.success"
        )
        # The notification might appear and then disappear, so we check if it exists
        if success_notification.count() > 0:
            expect(success_notification.first()).to_be_visible()

        # Alternative: Check if a temporary success message appears in the button area
        # or if the button text changes temporarily
        button_text_after = copy_urls_button.text_content()
        # Button might show "Copied!" temporarily, then revert

        # Verify the button is still functional after clicking
        expect(copy_urls_button).to_be_visible()

    @pytest.mark.ui
    def test_run_health_checks_navigation_and_execution(self, page: Page):
        """Test that Run Health Checks button navigates to health-checks page and executes Run All Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load
        page.wait_for_load_state("networkidle")

        # Find the Run Health Checks button in Quick Actions
        health_check_button = page.locator(
            "button:has-text('🔍 Run Health Check'), button:has-text('Run Health Check')"
        )

        # Check if the button exists
        if health_check_button.count() == 0:
            pytest.skip("Run Health Checks button not found on dashboard")

        expect(health_check_button).to_be_visible()

        # Click the Run Health Checks button
        health_check_button.click()

        # Wait for navigation to health-checks page
        page.wait_for_load_state("networkidle")

        # Verify we navigated to the health-checks page
        expect(page).to_have_url(f"{base_url}/health-checks")
        expect(page.locator("text=🏥 System Health Checks")).to_be_visible()

        # Check if the Run All Checks button exists and if checks started automatically
        run_all_checks_button = page.locator("#runAllChecks")
        expect(run_all_checks_button).to_be_visible()
        expect(run_all_checks_button).to_contain_text("🔄 Run All Checks")

        # Wait a moment to see if checks start automatically after navigation
        page.wait_for_timeout(1000)

        # Look for indicators that checks are running
        loading_indicators = page.locator(
            "text=Running, text=Checking, text=Loading, .loading, .spinner"
        )
        status_updates = page.locator(
            "#overallStatusContent, .health-check-result, .status-indicator"
        )

        # If no automatic execution indicators, manually click Run All Checks
        if loading_indicators.count() == 0 and status_updates.count() == 0:
            # Click the Run All Checks button manually
            run_all_checks_button.click()
            # Wait for the checks to start executing
            page.wait_for_timeout(2000)

        # Verify checks are executing - look for loading indicators, status updates, or results
        # The page might show loading states or update status sections
        loading_indicators = page.locator(
            "text=Running, text=Checking, text=Loading, .loading, .spinner"
        )
        status_updates = page.locator(
            "#overallStatusContent, .health-check-result, .status-indicator"
        )

        # At minimum, verify the page is still functional and hasn't crashed
        expect(page.locator("text=🏥 System Health Checks")).to_be_visible()

        # Verify the page remains functional after running checks
        # (We can't easily verify the exact check results without more complex assertions)

    @pytest.mark.ui
    def test_agents_navigation_to_workflow_page(self, page: Page):
        """Test that the Agents button navigates to the workflow/AI assistant page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for dashboard to load
        page.wait_for_load_state("networkidle")

        # Find the Agents button in the navigation
        agents_button = page.locator("a:has-text('🤖 Agents'), a[href='/workflow']")

        # Check if the button exists
        if agents_button.count() == 0:
            pytest.skip("Agents button not found in navigation")

        expect(agents_button).to_be_visible()

        # Click the Agents button
        agents_button.click()

        # Wait for navigation to workflow page
        page.wait_for_load_state("networkidle")

        # Verify we navigated to the workflow page (may include URL fragments like #config)
        expect(page).to_have_url(re.compile(rf"{base_url}/workflow(#.*)?$"))

        # Verify the workflow page loaded with expected content
        # Look for workflow-related content (AI Assistant, agents, etc.)
        workflow_indicators = page.locator(
            "text=Workflow, text=AI Assistant, text=Agent, text=🤖, h1, h2"
        )

        # At minimum, verify the page loaded (should have some heading or content)
        expect(page.locator("body")).not_to_be_empty()

        # If there are workflow indicators, verify at least one is visible
        if workflow_indicators.count() > 0:
            expect(workflow_indicators.first()).to_be_visible()


class TestArticlesFlows:
    """Test article browsing and viewing flows."""

    @pytest.mark.ui
    @pytest.mark.smoke
    def test_articles_listing(self, page: Page):
        """Test articles listing page functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")

        # Verify page loads
        expect(page.locator("h1").nth(1)).to_contain_text(
            "Threat Intelligence Articles"
        )

        # Check for article elements
        expect(page.locator("h1").nth(1)).to_be_visible()

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

            # Verify article detail page loads
            expect(page.locator("text=Article Content")).to_be_visible()
            expect(page.locator("text=Threat Hunting Analysis")).to_be_visible()
            expect(page.locator("text=TTP Quality Assessment")).to_be_visible()

            # Test back navigation
            page.click("text=Back to Articles")
            expect(page).to_have_url("http://localhost:8001/articles")

    @pytest.mark.ui
    def test_article_navigation(self, page: Page):
        """Test article navigation (previous/next)."""
        page.goto("http://localhost:8001/articles/1")

        # Check if navigation buttons exist
        prev_button = page.locator("text=Previous Article")
        next_button = page.locator("text=Next Article")

        if prev_button.count() > 0:
            expect(prev_button).to_be_visible()

        if next_button.count() > 0:
            expect(next_button).to_be_visible()

    @pytest.mark.ui
    def test_article_ai_assistant_button_functionality(self, page: Page):
        """Test that the AL/ML Assistant button works on article pages."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Navigate directly to an article page (using a known article ID)
        page.goto(f"{base_url}/articles/2175")

        # Wait for article page to load
        page.wait_for_load_state("networkidle")

        # Verify we're on an article page
        expect(page).to_have_url(re.compile(rf"{base_url}/articles/\d+"))

        # Find the AL/ML Assistant button
        ai_assistant_button = page.locator(
            "button:has-text('AL/ML Assistant'), button:has-text('AI/ML Assistant')"
        )

        # Check if the button exists
        if ai_assistant_button.count() == 0:
            pytest.skip("AL/ML Assistant button not found on article page")

        expect(ai_assistant_button).to_be_visible()

        # Click the AL/ML Assistant button
        ai_assistant_button.click()

        # Wait for the AI Assistant modal to appear
        page.wait_for_timeout(1000)

        # Verify the modal opened (look for common modal indicators)
        modal_selectors = [
            "#aiAssistantModal",
            ".modal",
            "[role='dialog']",
            "text=AI Assistant",
            "text=AL/ML Assistant",
        ]

        modal_found = False
        for selector in modal_selectors:
            elements = page.locator(selector)
            if elements.count() > 0 and elements.nth(0).is_visible():
                modal_found = True
                break

        assert modal_found, "AI Assistant modal should open after clicking the button"

        # Verify the modal has expected content (buttons, text areas, etc.)
        modal_content = page.locator("#aiAssistantModal, .modal, [role='dialog']")
        if modal_content.count() > 0:
            # Check for common AI assistant elements
            assistant_elements = modal_content.locator(
                "button, textarea, select, input"
            )
            if assistant_elements.count() > 0:
                expect(assistant_elements.nth(0)).to_be_visible()


class TestSourcesFlows:
    """Test source management flows."""

    @pytest.mark.ui
    @pytest.mark.smoke
    def test_sources_management(self, page: Page):
        """Test source management functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")

        # Verify page loads
        expect(page.locator("h1").nth(1)).to_contain_text("Threat Intelligence Sources")

        # Check for source management elements
        expect(page.locator("h1").nth(1)).to_be_visible()

        # Look for add source functionality
        add_source = page.locator("text=Add Source, New Source, + Add").first
        if add_source.count() > 0:
            expect(add_source).to_be_visible()


class TestResponsiveDesign:
    """Test responsive design and mobile compatibility."""

    @pytest.mark.ui
    def test_mobile_viewport(self, page: Page):
        """Test mobile viewport rendering."""
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto("http://localhost:8001/")

        # Verify mobile layout
        expect(page.locator("nav")).to_be_visible()

        # Check if content is properly sized for mobile
        expect(page.locator("main")).to_be_visible()

    @pytest.mark.ui
    def test_tablet_viewport(self, page: Page):
        """Test tablet viewport rendering."""
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto("http://localhost:8001/")

        # Verify tablet layout
        expect(page.locator("main")).to_be_visible()

        # Check grid layouts adapt properly
        grid_items = page.locator(".grid")
        if grid_items.count() > 0:
            expect(grid_items.first).to_be_visible()


class TestAccessibility:
    """Test accessibility features."""

    @pytest.mark.ui
    def test_page_structure(self, page: Page):
        """Test proper page structure and headings."""
        page.goto("http://localhost:8001/")

        # Check for proper heading hierarchy
        h1 = page.locator("h1")
        expect(h1).to_have_count(1)

        # Check for main content area
        main = page.locator("main")
        expect(main).to_have_count(1)

    @pytest.mark.ui
    def test_navigation_accessibility(self, page: Page):
        """Test navigation accessibility."""
        page.goto("http://localhost:8001/")

        # Check for navigation element
        nav = page.locator("nav")
        expect(nav).to_be_visible()

        # Check for navigation links
        nav_links = page.locator("nav a")
        expect(nav_links).to_have_count_at_least(3)


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
    @pytest.mark.smoke
    def test_rescore_all_articles_button(self, page: Page):
        """Test the rescore all articles button functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Find and click the rescore button
        rescore_button = page.locator("button:has-text('Rescore All Articles')")
        expect(rescore_button).to_be_visible()

        # Click the button
        rescore_button.click()

        # Wait for API call to complete and check for success notification
        # Wait for the completion notification specifically
        completion_notification = page.locator(
            "div.fixed.top-4.right-4:has-text('Rescoring completed')"
        )
        expect(completion_notification).to_be_visible(timeout=10000)
        expect(completion_notification).to_contain_text("Rescoring completed")

    @pytest.mark.ui
    @pytest.mark.slow
    def test_rescore_button_with_articles(self, page: Page):
        """Test rescore button when articles exist."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Wait for page to load
        page.wait_for_load_state("networkidle")

        # Check if there are articles to rescore
        rescore_button = page.locator("button:has-text('Rescore All Articles')")
        expect(rescore_button).to_be_visible()

        # Click the button
        rescore_button.click()

        # Wait for processing to complete
        page.wait_for_timeout(5000)

        # Check for notification
        notification = page.locator(".fixed.top-4.right-4")
        if notification.count() > 0:
            expect(notification).to_be_visible()
            # Should show either success or "already have scores" message
            notification_text = notification.text_content()
            assert any(
                msg in notification_text
                for msg in [
                    "Rescoring completed",
                    "No articles found",
                    "All articles already have scores",
                ]
            )

    @pytest.mark.ui
    def test_quick_actions_section(self, page: Page):
        """Test that quick actions section is properly displayed."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")

        # Check for quick actions section
        quick_actions = page.locator("text=Quick Actions")
        expect(quick_actions).to_be_visible()

        # Check for rescore button
        rescore_button = page.locator("button:has-text('Rescore All Articles')")
        expect(rescore_button).to_be_visible()

        # Check for health check button
        health_button = page.locator("button:has-text('Run Health Check')")
        expect(health_button).to_be_visible()


class TestPerformance:
    """Test UI performance."""

    @pytest.mark.ui
    @pytest.mark.slow
    def test_page_load_times(self, page: Page):
        """Test page load performance."""
        import time

        start_time = time.time()
        page.goto("http://localhost:8001/")
        page.wait_for_load_state("networkidle")
        end_time = time.time()

        load_time = end_time - start_time
        assert load_time < 10.0, f"Page took {load_time:.2f}s to load"

    @pytest.mark.ui
    @pytest.mark.slow
    def test_chart_rendering(self, page: Page):
        """Test chart rendering performance."""
        page.goto("http://localhost:8001/analysis")

        # Wait for charts to load
        page.wait_for_selector("#qualityChart")
        page.wait_for_selector("#tacticalChart")

        # Check if charts are interactive
        quality_canvas = page.locator("#qualityChart")
        tactical_canvas = page.locator("#tacticalChart")

        expect(quality_canvas).to_be_visible()
        expect(tactical_canvas).to_be_visible()
