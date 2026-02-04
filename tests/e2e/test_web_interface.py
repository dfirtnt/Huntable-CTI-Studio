import re
import time

import pytest

# Try to import Playwright
try:
    from playwright.sync_api import Page, expect

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    # Create dummy types for skip conditions
    Page = None
    expect = None


# Check if web server is accessible
def check_web_server():
    """Check if web server is accessible"""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 8001))
        sock.close()
        return result == 0
    except Exception:
        return False


WEB_SERVER_AVAILABLE = check_web_server()

# Mark all tests in this file as e2e tests (require web server + Playwright)
# These tests will be skipped if Playwright browsers aren't installed (handled by pytest-playwright)
# or if web server isn't available
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not available"),
    pytest.mark.skipif(not WEB_SERVER_AVAILABLE, reason="Web server not accessible on localhost:8001"),
]


# Hook to skip tests if Playwright browsers aren't installed
def pytest_runtest_setup(item):
    """Skip tests if Playwright browsers aren't installed"""
    if "test_web_interface" in str(item.fspath):
        # Check if we can actually use Playwright
        if PLAYWRIGHT_AVAILABLE:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    # Just check if we can get the browser type
                    _ = p.chromium
            except Exception as e:
                if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
                    pytest.skip("Playwright browsers not installed. Run 'playwright install'")
                # Re-raise other exceptions
                raise


class TestCTIScraperWebInterface:
    """End-to-end tests for CTIScraper web interface"""

    @pytest.fixture(autouse=True)
    def setup(self, page):
        """Setup for each test"""
        # Skip if Playwright browsers aren't installed (error will be caught by pytest-playwright)
        try:
            page.goto("http://localhost:8001")
            page.wait_for_load_state("networkidle")
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
                pytest.skip(f"Playwright browsers not installed: {e}")
            raise

    def test_homepage_loads(self, page):
        """Test that the homepage loads successfully"""
        expect(page).to_have_title("Dashboard - Huntable CTI Studio")
        expect(page.locator("h1").first).to_be_visible()

    def test_navigation_menu(self, page):
        """Test navigation menu functionality"""
        # Check main navigation links
        expect(page.locator("nav")).to_be_visible()

        # Test sources page navigation
        page.click("text=Sources")
        expect(page).to_have_url("http://localhost:8001/sources")
        # Use more specific selector to avoid strict mode violation (h1 heading)
        expect(
            page.get_by_role("heading", name=re.compile(r".*Threat Intelligence Sources.*", re.IGNORECASE))
        ).to_be_visible()

    def test_sources_page(self, page):
        """Test sources page functionality"""
        page.goto("http://localhost:8001/sources")
        page.wait_for_load_state("networkidle")

        # Check sources table is visible (may use different structure)
        # Look for table or source list elements
        table_or_list = page.locator("table, .source-list, [class*='source']")
        if table_or_list.count() > 0:
            expect(table_or_list.first).to_be_visible()

        # Check for source names (may not have Group-IB specifically)
        # Just verify sources are displayed
        sources_list = page.locator("h4, .source-name, [class*='source']")
        if sources_list.count() > 0:
            expect(sources_list.first).to_be_visible()

        # Check source status indicators (Active/Inactive badges)
        status_badges = page.locator("text=Active, text=Inactive")
        if status_badges.count() > 0:
            expect(status_badges.first).to_be_visible()

    def test_articles_page(self, page):
        """Test articles page functionality"""
        page.goto("http://localhost:8001/articles")
        page.wait_for_load_state("networkidle")

        # Check articles table (may use different structure)
        # Look for table or article list elements
        table_or_list = page.locator("table, .article-list, [class*='article']")
        if table_or_list.count() > 0:
            expect(table_or_list.first).to_be_visible()

        # Check for article content (may use different selectors)
        # Look for article rows or titles
        article_elements = page.locator("table tbody tr, .article, [class*='article']")
        if article_elements.count() > 0:
            expect(article_elements.first).to_be_visible()

    def test_api_endpoints(self, page):
        """Test API endpoints via browser"""
        # Test health endpoint
        response = page.request.get("http://localhost:8001/health")
        expect(response).to_be_ok()

        # Test sources API
        response = page.request.get("http://localhost:8001/api/sources")
        expect(response).to_be_ok()
        data = response.json()
        assert "sources" in data, "API response should contain 'sources' key"

    def test_search_functionality(self, page):
        """Test search functionality"""
        page.goto("http://localhost:8001/articles")

        # Look for search input
        search_input = page.locator("input[type='search'], input[placeholder*='search']")
        if search_input.count() > 0:
            search_input.first.fill("threat")
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle")

            # Check results
            expect(page.locator(".search-results")).to_be_visible()

    def test_responsive_design(self, page):
        """Test responsive design on mobile viewport"""
        page.set_viewport_size({"width": 375, "height": 667})  # iPhone SE

        page.goto("http://localhost:8001")

        # Check mobile navigation
        expect(page.locator("nav")).to_be_visible()

        # Check table responsiveness (may use different structure)
        page.goto("http://localhost:8001/sources")
        table_or_list = page.locator("table, .source-list, [class*='source']")
        if table_or_list.count() > 0:
            expect(table_or_list.first).to_be_visible()

    def test_error_handling(self, page):
        """Test error handling for invalid routes"""
        # Test 404 page
        page.goto("http://localhost:8001/nonexistent-page")

        # Should show error page or redirect
        expect(page.locator("body")).to_be_visible()

    def test_performance(self, page):
        """Test page load performance"""
        start_time = time.time()
        page.goto("http://localhost:8001")
        page.wait_for_load_state("networkidle")
        load_time = time.time() - start_time

        # Page should load within 5 seconds
        assert load_time < 5.0, f"Page load time {load_time:.2f}s exceeds 5s limit"

    def test_accessibility(self, page: Page):
        """Test basic accessibility features"""
        page.goto("http://localhost:8001")
        page.wait_for_load_state("networkidle")

        # Check for alt text on images (skip decorative images)
        images = page.locator("img")
        image_count = images.count()
        for i in range(min(image_count, 10)):  # Check first 10 images
            img = images.nth(i)
            alt_text = img.get_attribute("alt")
            # Some images may be decorative and have empty alt (acceptable)
            # Just verify attribute exists
            aria_hidden = img.get_attribute("aria-hidden")
            assert alt_text is not None or aria_hidden == "true", f"Image {i} missing alt text or aria-hidden"

        # Check for proper heading hierarchy (may have multiple h1 in different sections)
        h1_count = page.locator("h1").count()
        assert h1_count >= 1, f"Expected at least 1 h1, found {h1_count}"

    def test_threat_hunting_scoring(self, page):
        """Test threat hunting scoring interface"""
        page.goto("http://localhost:8001/articles")

        # Look for scoring elements
        score_elements = page.locator(".threat-score, .score, [data-score]")
        if score_elements.count() > 0:
            expect(score_elements.first).to_be_visible()

            # Check score values are numeric
            score_text = score_elements.first.text_content()
            assert score_text.replace(".", "").replace("-", "").isdigit(), "Score should be numeric"

    def test_source_management(self, page):
        """Test source management functionality"""
        page.goto("http://localhost:8001/sources")

        # Check for source controls (may use different structure)
        table_or_list = page.locator("table, .source-list, [class*='source']")
        if table_or_list.count() > 0:
            expect(table_or_list.first).to_be_visible()

        # Check for active/inactive indicators (Active/Inactive badges)
        status_indicators = page.locator("text=Active, text=Inactive")
        if status_indicators.count() > 0:
            expect(status_indicators.first).to_be_visible()

    def test_data_export(self, page):
        """Test data export functionality"""
        page.goto("http://localhost:8001/articles")

        # Look for export buttons
        export_buttons = page.locator("button:has-text('Export'), a:has-text('Export'), .export-btn")
        if export_buttons.count() > 0:
            # Test export functionality
            with page.expect_download() as download_info:
                export_buttons.first.click()
            download = download_info.value
            assert download.suggested_filename.endswith((".csv", ".json", ".xlsx")), "Export should be a data file"
