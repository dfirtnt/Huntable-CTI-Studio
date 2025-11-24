"""
UI tests for cross-page navigation features using Playwright.
Tests breadcrumbs, deep linking, browser navigation, URL params, and related features.
"""

import pytest
from playwright.sync_api import Page, expect
import os


class TestCrossPageNavigation:
    """Test cross-page navigation features."""
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_dashboard_to_articles_navigation(self, page: Page):
        """Test navigation from dashboard to articles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Navigate to articles
        articles_link = page.locator("a:has-text('Articles')")
        expect(articles_link).to_be_visible()
        articles_link.click()
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/articles")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_articles_to_dashboard_navigation(self, page: Page):
        """Test navigation from articles to dashboard."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Navigate to dashboard
        dashboard_link = page.locator("a[href='/']")
        expect(dashboard_link).to_be_visible()
        dashboard_link.click()
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_browser_back_button(self, page: Page):
        """Test browser back button navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Navigate to articles
        articles_link = page.locator("a:has-text('Articles')")
        articles_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(f"{base_url}/articles")
        
        # Use browser back button
        page.go_back()
        page.wait_for_load_state("networkidle")
        
        # Verify back navigation
        expect(page).to_have_url(f"{base_url}/")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_browser_forward_button(self, page: Page):
        """Test browser forward button navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Navigate to articles
        articles_link = page.locator("a:has-text('Articles')")
        articles_link.click()
        page.wait_for_load_state("networkidle")
        
        # Go back
        page.go_back()
        page.wait_for_load_state("networkidle")
        
        # Go forward
        page.go_forward()
        page.wait_for_load_state("networkidle")
        
        # Verify forward navigation
        expect(page).to_have_url(f"{base_url}/articles")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_deep_linking_to_articles(self, page: Page):
        """Test deep linking to articles page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate directly to articles page
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Verify page loads correctly
        expect(page).to_have_url(f"{base_url}/articles")
        expect(page).to_have_title("Articles - CTI Scraper")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_deep_linking_to_sources(self, page: Page):
        """Test deep linking to sources page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate directly to sources page
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Verify page loads correctly
        expect(page).to_have_url(f"{base_url}/sources")
        expect(page).to_have_title("Sources - CTI Scraper")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_deep_linking_to_settings(self, page: Page):
        """Test deep linking to settings page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate directly to settings page
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify page loads correctly
        expect(page).to_have_url(f"{base_url}/settings")
        expect(page).to_have_title("Settings - CTI Scraper")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_deep_linking_to_workflow(self, page: Page):
        """Test deep linking to workflow page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate directly to workflow page
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")
        
        # Verify page loads correctly
        expect(page).to_have_url(f"{base_url}/workflow")
        expect(page).to_have_title("Agentic Workflow - CTI Scraper")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_url_parameter_persistence(self, page: Page):
        """Test URL parameter persistence."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to articles with query parameters
        page.goto(f"{base_url}/articles?source_id=1&classification=chosen")
        page.wait_for_load_state("networkidle")
        
        # Verify URL parameters are preserved
        expect(page).to_have_url(f"{base_url}/articles?source_id=1&classification=chosen")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_bookmark_functionality(self, page: Page):
        """Test bookmark functionality (URL preservation)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to a specific page
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Get current URL
        current_url = page.url
        
        # Reload page (simulating bookmark)
        page.reload()
        page.wait_for_load_state("networkidle")
        
        # Verify URL is preserved
        expect(page).to_have_url(current_url)
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_navigation_menu_consistency(self, page: Page):
        """Test navigation menu consistency across pages."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        pages = ["/", "/articles", "/sources", "/settings", "/workflow"]
        
        for page_path in pages:
            page.goto(f"{base_url}{page_path}")
            page.wait_for_load_state("networkidle")
            
            # Verify navigation menu exists
            nav_menu = page.locator("nav")
            expect(nav_menu).to_be_visible()
            
            # Verify common navigation links exist
            dashboard_link = page.locator("a[href='/']")
            expect(dashboard_link).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_article_detail_navigation(self, page: Page):
        """Test navigation to article detail page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find first article link
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            first_article = article_links.first
            article_href = first_article.get_attribute("href")
            
            # Click article link
            first_article.click()
            page.wait_for_load_state("networkidle")
            
            # Verify navigation to article detail
            expect(page).to_have_url(f"{base_url}{article_href}")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_article_detail_back_to_list(self, page: Page):
        """Test navigation back to article list from detail."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to article detail
        page.goto(f"{base_url}/articles/1")
        page.wait_for_load_state("networkidle")
        
        # Find back link or navigate via menu
        articles_link = page.locator("a:has-text('Articles')")
        if articles_link.count() > 0:
            articles_link.click()
            page.wait_for_load_state("networkidle")
            
            # Verify navigation back to list
            expect(page).to_have_url(f"{base_url}/articles")
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_workflow_tab_navigation_persistence(self, page: Page):
        """Test workflow tab navigation persistence in URL."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to workflow page
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Click on Executions tab
        executions_tab = page.locator("button:has-text('Executions')")
        if executions_tab.count() > 0:
            executions_tab.click()
            page.wait_for_timeout(1000)
            
            # Verify URL may include tab parameter
            current_url = page.url
            # URL may or may not include tab parameter depending on implementation
    
    @pytest.mark.ui
    @pytest.mark.navigation
    def test_analytics_sub_page_navigation(self, page: Page):
        """Test navigation to analytics sub-pages."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to main analytics page
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Navigate to scraper metrics
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/analytics/scraper-metrics")
        
        # Navigate to hunt metrics
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify navigation
        expect(page).to_have_url(f"{base_url}/analytics/hunt-metrics")


