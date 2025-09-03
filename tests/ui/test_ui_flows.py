"""
UI flow tests using Playwright for CTI Scraper.
"""
import pytest
from playwright.async_api import Page, expect
from typing import AsyncGenerator

class TestDashboardFlows:
    """Test dashboard user flows."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    async def test_dashboard_navigation(self, page: Page):
        """Test navigation between dashboard sections."""
        await page.goto("http://localhost:8000/")
        
        # Verify dashboard loads
        await expect(page).to_have_title("CTI Scraper")
        await expect(page.locator("h1")).to_contain_text("CTI Scraper Dashboard")
        
        # Test navigation to articles
        await page.click("text=Articles")
        await expect(page).to_have_url("http://localhost:8000/articles")
        
        # Test navigation to analysis
        await page.click("text=TTP Analysis")
        await expect(page).to_have_url("http://localhost:8000/analysis")
        
        # Test navigation to sources
        await page.click("text=Sources")
        await expect(page).to_have_url("http://localhost:8000/sources")
        
        # Return to dashboard
        await page.click("text=Dashboard")
        await expect(page).to_have_url("http://localhost:8000/")

class TestArticlesFlows:
    """Test article browsing and viewing flows."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    async def test_articles_listing(self, page: Page):
        """Test articles listing page functionality."""
        await page.goto("http://localhost:8000/articles")
        
        # Verify page loads
        await expect(page.locator("h1")).to_contain_text("Articles")
        
        # Check for article elements
        await expect(page.locator("text=Browse Articles")).to_be_visible()
        
        # Test pagination if available
        pagination = page.locator("[data-testid='pagination']")
        if await pagination.count() > 0:
            await expect(pagination).to_be_visible()
    
    @pytest.mark.ui
    async def test_article_detail_view(self, page: Page):
        """Test individual article detail page."""
        await page.goto("http://localhost:8000/articles")
        
        # Try to click on first article if available
        first_article = page.locator("a[href^='/articles/']").first
        if await first_article.count() > 0:
            await first_article.click()
            
            # Verify article detail page loads
            await expect(page.locator("text=Article Content")).to_be_visible()
            await expect(page.locator("text=Threat Hunting Analysis")).to_be_visible()
            await expect(page.locator("text=TTP Quality Assessment")).to_be_visible()
            
            # Test back navigation
            await page.click("text=Back to Articles")
            await expect(page).to_have_url("http://localhost:8000/articles")
    
    @pytest.mark.ui
    async def test_article_navigation(self, page: Page):
        """Test article navigation (previous/next)."""
        await page.goto("http://localhost:8000/articles/1")
        
        # Check if navigation buttons exist
        prev_button = page.locator("text=Previous Article")
        next_button = page.locator("text=Next Article")
        
        if await prev_button.count() > 0:
            await expect(prev_button).to_be_visible()
        
        if await next_button.count() > 0:
            await expect(next_button).to_be_visible()

class TestAnalysisFlows:
    """Test TTP analysis dashboard flows."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    async def test_analysis_dashboard(self, page: Page):
        """Test analysis dashboard functionality."""
        await page.goto("http://localhost:8000/analysis")
        
        # Verify dashboard loads
        await expect(page.locator("h1")).to_contain_text("Threat Hunting Analysis Dashboard")
        
        # Check quality metrics
        await expect(page.locator("text=Combined Quality")).to_be_visible()
        await expect(page.locator("text=TTP Quality")).to_be_visible()
        await expect(page.locator("text=LLM Quality")).to_be_visible()
        
        # Check charts
        await expect(page.locator("#qualityChart")).to_be_visible()
        await expect(page.locator("#tacticalChart")).to_be_visible()
    
    @pytest.mark.ui
    async def test_quality_distribution_chart(self, page: Page):
        """Test quality distribution chart functionality."""
        await page.goto("http://localhost:8000/analysis")
        
        # Wait for chart to load
        await page.wait_for_selector("#qualityChart")
        
        # Check if chart canvas is present
        canvas = page.locator("#qualityChart")
        await expect(canvas).to_be_visible()
        
        # Verify chart data is loaded (basic check)
        await expect(page.locator("text=Excellent")).to_be_visible()
        await expect(page.locator("text=Good")).to_be_visible()
        await expect(page.locator("text=Fair")).to_be_visible()
        await expect(page.locator("text=Limited")).to_be_visible()
    
    @pytest.mark.ui
    async def test_tactical_distribution_chart(self, page: Page):
        """Test tactical vs strategic distribution chart."""
        await page.goto("http://localhost:8000/analysis")
        
        # Wait for chart to load
        await page.wait_for_selector("#tacticalChart")
        
        # Check if chart canvas is present
        canvas = page.locator("#tacticalChart")
        await expect(canvas).to_be_visible()
        
        # Verify chart categories
        await expect(page.locator("text=Tactical")).to_be_visible()
        await expect(page.locator("text=Strategic")).to_be_visible()
        await expect(page.locator("text=Hybrid")).to_be_visible()

class TestSourcesFlows:
    """Test source management flows."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    async def test_sources_management(self, page: Page):
        """Test source management functionality."""
        await page.goto("http://localhost:8000/sources")
        
        # Verify page loads
        await expect(page.locator("h1")).to_contain_text("Sources")
        
        # Check for source management elements
        await expect(page.locator("text=Manage Sources")).to_be_visible()
        
        # Look for add source functionality
        add_source = page.locator("text=Add Source, New Source, + Add").first
        if await add_source.count() > 0:
            await expect(add_source).to_be_visible()

class TestResponsiveDesign:
    """Test responsive design and mobile compatibility."""
    
    @pytest.mark.ui
    async def test_mobile_viewport(self, page: Page):
        """Test mobile viewport rendering."""
        await page.set_viewport_size({"width": 375, "height": 667})
        await page.goto("http://localhost:8000/")
        
        # Verify mobile layout
        await expect(page.locator("nav")).to_be_visible()
        
        # Check if content is properly sized for mobile
        await expect(page.locator("main")).to_be_visible()
    
    @pytest.mark.ui
    async def test_tablet_viewport(self, page: Page):
        """Test tablet viewport rendering."""
        await page.set_viewport_size({"width": 768, "height": 1024})
        await page.goto("http://localhost:8000/")
        
        # Verify tablet layout
        await expect(page.locator("main")).to_be_visible()
        
        # Check grid layouts adapt properly
        grid_items = page.locator(".grid")
        if await grid_items.count() > 0:
            await expect(grid_items.first).to_be_visible()

class TestAccessibility:
    """Test accessibility features."""
    
    @pytest.mark.ui
    async def test_page_structure(self, page: Page):
        """Test proper page structure and headings."""
        await page.goto("http://localhost:8000/")
        
        # Check for proper heading hierarchy
        h1 = page.locator("h1")
        await expect(h1).to_have_count(1)
        
        # Check for main content area
        main = page.locator("main")
        await expect(main).to_have_count(1)
    
    @pytest.mark.ui
    async def test_navigation_accessibility(self, page: Page):
        """Test navigation accessibility."""
        await page.goto("http://localhost:8000/")
        
        # Check for navigation element
        nav = page.locator("nav")
        await expect(nav).to_be_visible()
        
        # Check for navigation links
        nav_links = page.locator("nav a")
        await expect(nav_links).to_have_count_at_least(3)

class TestErrorHandling:
    """Test error handling in UI."""
    
    @pytest.mark.ui
    async def test_404_page(self, page: Page):
        """Test 404 error page."""
        await page.goto("http://localhost:8000/nonexistent-page")
        
        # Should show error page
        await expect(page.locator("text=Something went wrong")).to_be_visible()
        await expect(page.locator("text=Page not found")).to_be_visible()
        
        # Check error page navigation
        await page.click("text=Go to Dashboard")
        await expect(page).to_have_url("http://localhost:8000/")
    
    @pytest.mark.ui
    async def test_invalid_article_id(self, page: Page):
        """Test handling of invalid article IDs."""
        await page.goto("http://localhost:8000/articles/999999")
        
        # Should handle gracefully
        if page.url.endswith("999999"):
            # If it shows an error page
            await expect(page.locator("text=Something went wrong")).to_be_visible()
        else:
            # Or redirects to a valid page
            await expect(page).to_have_url(lambda url: "999999" not in url)

class TestPerformance:
    """Test UI performance."""
    
    @pytest.mark.ui
    @pytest.mark.slow
    async def test_page_load_times(self, page: Page):
        """Test page load performance."""
        import time
        
        start_time = time.time()
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")
        end_time = time.time()
        
        load_time = end_time - start_time
        assert load_time < 10.0, f"Page took {load_time:.2f}s to load"
    
    @pytest.mark.ui
    @pytest.mark.slow
    async def test_chart_rendering(self, page: Page):
        """Test chart rendering performance."""
        await page.goto("http://localhost:8000/analysis")
        
        # Wait for charts to load
        await page.wait_for_selector("#qualityChart")
        await page.wait_for_selector("#tacticalChart")
        
        # Check if charts are interactive
        quality_canvas = page.locator("#qualityChart")
        tactical_canvas = page.locator("#tacticalChart")
        
        await expect(quality_canvas).to_be_visible()
        await expect(tactical_canvas).to_be_visible()
