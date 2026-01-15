"""Tests for navigation and routing behavior."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
class TestNavigationRouting:
    """Test navigation and routing behavior."""
    
    def test_navigation_to_articles(self, page: Page):
        """Test navigation to articles page."""
        page.goto("http://localhost:8002/")
        
        # Click articles link (adjust selector based on actual UI)
        articles_link = page.locator('a[href="/articles"]').first
        articles_link.click()
        
        # Assert we're on articles page
        expect(page).to_have_url("http://localhost:8002/articles")
        expect(page.locator("h1, .page-title")).to_contain_text("Articles", timeout=5000)
    
    def test_navigation_to_workflow(self, page: Page):
        """Test navigation to workflow page."""
        page.goto("http://localhost:8002/")
        
        # Navigate to workflow
        workflow_link = page.locator('a[href="/workflow"]').first
        workflow_link.click()
        
        # Assert we're on workflow page
        expect(page).to_have_url("http://localhost:8002/workflow")
    
    def test_breadcrumb_navigation(self, page: Page):
        """Test breadcrumb navigation behavior."""
        page.goto("http://localhost:8002/articles")
        
        # If breadcrumbs exist, test navigation
        breadcrumbs = page.locator(".breadcrumb, [aria-label='breadcrumb']")
        if breadcrumbs.count() > 0:
            # Click home breadcrumb
            home_crumb = breadcrumbs.locator("a").first
            home_crumb.click()
            expect(page).to_have_url("http://localhost:8002/")
