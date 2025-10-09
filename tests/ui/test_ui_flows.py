"""
UI flow tests using Playwright for CTI Scraper.
"""
import pytest
import os
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
        expect(page).to_have_title("CTI Scraper Dashboard")
        expect(page.locator("h1").first).to_contain_text("CTI Scraper")
        
        # Test navigation to articles
        page.click("text=Articles")
        expect(page).to_have_url(f"{base_url}/articles")

        # Test navigation to sources
        page.click("text=Sources")
        expect(page).to_have_url(f"{base_url}/sources")

        # Return to dashboard
        page.click("text=Dashboard")
        expect(page).to_have_url(f"{base_url}/")

class TestArticlesFlows:
    """Test article browsing and viewing flows."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    
    def test_articles_listing(self, page: Page):
        """Test articles listing page functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        
        # Verify page loads
        expect(page.locator("h1").nth(1)).to_contain_text("Threat Intelligence Articles")
        
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
        
        # Wait for API call to complete
        page.wait_for_timeout(2000)
        
        # Check for success notification
        notification = page.locator(".fixed.top-4.right-4")
        if notification.count() > 0:
            expect(notification).to_be_visible()
            # Notification should contain success message
            expect(notification).to_contain_text("Rescoring completed")
    
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
            assert any(msg in notification_text for msg in [
                "Rescoring completed",
                "No articles found",
                "All articles already have scores"
            ])
    
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
