"""Tests for navigation and routing behavior."""

import os

import pytest
from playwright.sync_api import Page, expect


def _base_url():
    return os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")


@pytest.mark.ui
class TestNavigationRouting:
    """Test navigation and routing behavior."""

    def test_navigation_to_articles(self, page: Page):
        """Test navigation to articles page."""
        base_url = _base_url()
        page.goto(f"{base_url}/")

        # Click articles link (adjust selector based on actual UI)
        articles_link = page.locator('a[href="/articles"]').first
        articles_link.click()

        # Assert we're on articles page
        expect(page).to_have_url(f"{base_url}/articles")
        expect(page.locator("h1, .page-title")).to_contain_text("Articles", timeout=5000)

    def test_navigation_to_workflow(self, page: Page):
        """Test navigation to workflow page."""
        base_url = _base_url()
        page.goto(f"{base_url}/")

        # Navigate to workflow
        workflow_link = page.locator('a[href="/workflow"]').first
        workflow_link.click()

        # Assert we're on workflow page
        expect(page).to_have_url(f"{base_url}/workflow")

    def test_breadcrumb_navigation(self, page: Page):
        """Test breadcrumb navigation: Dashboard link goes home."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        breadcrumbs = page.locator('nav[aria-label="Breadcrumb"]')
        expect(breadcrumbs).to_be_visible()
        home_crumb = breadcrumbs.locator('a[href="/"]').first
        expect(home_crumb).to_be_visible()
        home_crumb.click()
        expect(page).to_have_url(f"{base_url}/")

    def test_breadcrumbs_on_articles_page(self, page: Page):
        """Test breadcrumbs on articles list: Dashboard and Articles (current)."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        nav = page.locator('nav[aria-label="Breadcrumb"]')
        expect(nav).to_be_visible()
        expect(nav).to_contain_text("Dashboard")
        expect(nav).to_contain_text("Articles")

    def test_breadcrumbs_on_workflow_page(self, page: Page):
        """Test breadcrumbs on workflow: Dashboard and Agents (current)."""
        base_url = _base_url()
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")

        nav = page.locator('nav[aria-label="Breadcrumb"]')
        expect(nav).to_be_visible()
        expect(nav).to_contain_text("Dashboard")
        expect(nav).to_contain_text("Agents")

    def test_breadcrumbs_on_settings_page(self, page: Page):
        """Test breadcrumbs on settings: Dashboard and Settings (current)."""
        base_url = _base_url()
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        nav = page.locator('nav[aria-label="Breadcrumb"]')
        expect(nav).to_be_visible()
        expect(nav).to_contain_text("Dashboard")
        expect(nav).to_contain_text("Settings")

    def test_breadcrumbs_on_chat_page(self, page: Page):
        """Test breadcrumbs on chat: Dashboard and RAG Search (current)."""
        base_url = _base_url()
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")

        nav = page.locator('nav[aria-label="Breadcrumb"]')
        expect(nav).to_be_visible()
        expect(nav).to_contain_text("Dashboard")
        expect(nav).to_contain_text("RAG Search")

    def test_breadcrumbs_on_mlops_page(self, page: Page):
        """Test breadcrumbs on MLOps: Dashboard and MLOps (current)."""
        base_url = _base_url()
        page.goto(f"{base_url}/mlops")
        page.wait_for_load_state("networkidle")

        nav = page.locator('nav[aria-label="Breadcrumb"]')
        expect(nav).to_be_visible()
        expect(nav).to_contain_text("Dashboard")
        expect(nav).to_contain_text("MLOps")
