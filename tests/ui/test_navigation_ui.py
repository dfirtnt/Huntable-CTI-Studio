"""
UI tests for navigation, routing, breadcrumbs, deep linking, and browser history.

Consolidated from test_navigation_routing.py and test_cross_page_navigation_ui.py.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect


def _base_url():
    return os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")


@pytest.mark.ui
@pytest.mark.navigation
class TestBreadcrumbs:
    """Test breadcrumb navigation across pages."""

    def test_breadcrumb_home_link(self, page: Page):
        """Breadcrumb Dashboard link navigates home."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        breadcrumbs = page.locator('nav[aria-label="Breadcrumb"]')
        expect(breadcrumbs).to_be_visible()
        home_crumb = breadcrumbs.locator('a[href="/"]').first
        expect(home_crumb).to_be_visible()
        home_crumb.click()
        expect(page).to_have_url(f"{base_url}/")

    @pytest.mark.parametrize(
        ("path", "expected_crumbs"),
        [
            ("/articles", ("Dashboard", "Articles")),
            ("/workflow", ("Dashboard", "Agents")),
            ("/settings", ("Dashboard", "Settings")),
            ("/chat", ("Dashboard", "RAG Search")),
            ("/mlops", ("Dashboard", "MLOps")),
        ],
    )
    def test_breadcrumbs_contain_expected_text(self, page: Page, path: str, expected_crumbs: tuple):
        """Breadcrumb nav shows correct trail for each page."""
        base_url = _base_url()
        page.goto(f"{base_url}{path}")
        page.wait_for_load_state("load")

        nav = page.locator('nav[aria-label="Breadcrumb"]')
        expect(nav).to_be_visible()
        for crumb in expected_crumbs:
            expect(nav).to_contain_text(crumb)


@pytest.mark.ui
@pytest.mark.navigation
class TestPageNavigation:
    """Test link-click navigation between pages."""

    def test_dashboard_to_articles(self, page: Page):
        """Navigate from dashboard to articles via link."""
        base_url = _base_url()
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        articles_link = page.locator("a:has-text('Articles')").first
        expect(articles_link).to_be_visible()
        articles_link.click()
        expect(page).to_have_url(f"{base_url}/articles")

    def test_articles_to_dashboard(self, page: Page):
        """Navigate from articles back to dashboard via link."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        dashboard_link = page.locator("a[href='/']").first
        expect(dashboard_link).to_be_visible()
        dashboard_link.click()
        expect(page).to_have_url(f"{base_url}/")

    def test_dashboard_to_workflow(self, page: Page):
        """Navigate from dashboard to workflow via link."""
        base_url = _base_url()
        page.goto(f"{base_url}/")

        workflow_link = page.locator('a[href="/workflow"]').first
        workflow_link.click()
        expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/workflow(#.*)?$"))

    def test_article_detail_navigation(self, page: Page):
        """Navigate to article detail from list (data-dependent)."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            first_article = article_links.first
            article_href = first_article.get_attribute("href")
            first_article.click()
            page.wait_for_load_state("load")
            expect(page).to_have_url(f"{base_url}{article_href}")

    def test_article_detail_back_to_list(self, page: Page):
        """Navigate back to article list from detail."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles/1")
        page.wait_for_load_state("load")

        articles_link = page.locator("a:has-text('Articles')")
        if articles_link.count() > 0:
            articles_link.first.click()
            page.wait_for_load_state("load")
            expect(page).to_have_url(f"{base_url}/articles")


@pytest.mark.ui
@pytest.mark.navigation
class TestBrowserHistory:
    """Test browser back/forward button behavior."""

    def test_back_button(self, page: Page):
        """Browser back button returns to previous page."""
        base_url = _base_url()
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        page.locator("a:has-text('Articles')").first.click()
        page.wait_for_load_state("load")
        expect(page).to_have_url(f"{base_url}/articles")

        page.go_back()
        page.wait_for_load_state("load")
        expect(page).to_have_url(f"{base_url}/")

    def test_forward_button(self, page: Page):
        """Browser forward button after back returns to visited page."""
        base_url = _base_url()
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        page.locator("a:has-text('Articles')").first.click()
        page.wait_for_load_state("load")

        page.go_back()
        page.wait_for_load_state("load")

        page.go_forward()
        page.wait_for_load_state("load")
        expect(page).to_have_url(f"{base_url}/articles")


@pytest.mark.ui
@pytest.mark.navigation
class TestDeepLinking:
    """Test direct URL access and parameter preservation."""

    @pytest.mark.parametrize(
        ("path", "expected_title"),
        [
            ("/articles", "Articles - Huntable CTI Studio"),
            ("/sources", "Sources - Huntable CTI Studio"),
            ("/settings", "Settings - Huntable CTI Studio"),
        ],
    )
    def test_deep_link_loads_correct_page(self, page: Page, path: str, expected_title: str):
        """Direct URL access loads the correct page with expected title."""
        base_url = _base_url()
        page.goto(f"{base_url}{path}")
        page.wait_for_load_state("load")
        expect(page).to_have_url(f"{base_url}{path}")
        expect(page).to_have_title(expected_title)

    def test_deep_link_workflow(self, page: Page):
        """Direct workflow URL loads correctly (may include hash fragment)."""
        base_url = _base_url()
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/workflow(#.*)?$"))
        expect(page).to_have_title("Agentic Workflow - Huntable CTI Studio")

    def test_url_parameter_persistence(self, page: Page):
        """URL query parameters are preserved on page load."""
        base_url = _base_url()
        page.goto(f"{base_url}/articles?source_id=1&threat_hunting_range=80-100")
        page.wait_for_load_state("load")
        expect(page).to_have_url(re.compile(r".*source_id=1.*threat_hunting_range=80-100.*"))

    def test_bookmark_reload_preserves_url(self, page: Page):
        """Page reload preserves the current URL (bookmark behavior)."""
        base_url = _base_url()
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("load")
        current_url = page.url
        page.reload()
        page.wait_for_load_state("load")
        expect(page).to_have_url(current_url)


@pytest.mark.ui
@pytest.mark.navigation
class TestNavigationConsistency:
    """Test navigation menu and structure consistency."""

    def test_nav_menu_present_on_all_pages(self, page: Page):
        """Navigation menu exists and has dashboard link on all main pages."""
        base_url = _base_url()

        for page_path in ("/", "/articles", "/sources", "/settings", "/workflow"):
            page.goto(f"{base_url}{page_path}")
            page.wait_for_load_state("load")

            nav_menu = page.locator("nav").first
            expect(nav_menu).to_be_visible()
            dashboard_link = page.locator("a[href='/']").first
            expect(dashboard_link).to_be_visible()

    def test_analytics_sub_page_navigation(self, page: Page):
        """Analytics sub-pages are directly accessible."""
        base_url = _base_url()

        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("load")
        expect(page).to_have_url(f"{base_url}/analytics/scraper-metrics")

        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("load")
        expect(page).to_have_url(f"{base_url}/analytics/hunt-metrics")
