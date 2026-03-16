"""
Unit tests for the Health page components.
"""

import json
import os
import re

import pytest
from playwright.sync_api import Page, expect


class TestHealthPage:
    """Test the Health page functionality."""

    @pytest.mark.ui
    def test_health_page_loads(self, page: Page):
        """Test that the Health page loads correctly."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")

        # Check page title and header
        expect(page).to_have_title("System Diagnostics & Health - Huntable CTI Studio")
        expect(page.locator("h1").nth(1)).to_contain_text("System Diagnostics & Health")

        # Check description
        expect(page.locator("p").first).to_contain_text("Monitor system")

    @pytest.mark.ui
    def test_health_check_buttons_visible(self, page: Page):
        """Test that all health check buttons are visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")

        # Only runAllHealthChecks exists in diags; individual check buttons do not exist
        button = page.locator("#runAllHealthChecks")
        expect(button).to_be_visible()

    @pytest.mark.ui
    def test_health_check_sections_visible(self, page: Page):
        """Test that all health check sections are visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")

        # Check all health check sections are visible
        sections = [
            "databaseHealthContent",
            "servicesHealthContent",
            "deduplicationHealthContent",
            "celeryHealthContent",
        ]

        for section_id in sections:
            section = page.locator(f"#{section_id}")
            expect(section).to_be_visible()

    @pytest.mark.ui
    def test_run_all_checks_button_click(self, page: Page):
        """Test that Run All Checks button triggers all health checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock all health check API responses
        def mock_health_check(route):
            endpoint = route.request.url.split("/api/health")[-1] or ""
            if endpoint == "":
                # Overall health check
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "timestamp": "2024-01-01T00:00:00",
                            "database": {"status": "connected", "sources": 5, "articles": 100},
                            "version": "2.0.0",
                        }
                    ),
                )
            elif endpoint == "/database":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "timestamp": "2024-01-01T00:00:00",
                            "database": {"status": "connected", "sources": 5, "articles": 100, "duplicates": 10},
                        }
                    ),
                )
            elif endpoint == "/deduplication":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "timestamp": "2024-01-01T00:00:00",
                            "deduplication": {"status": "healthy", "similarity_threshold": 0.85, "total_hashes": 1000},
                        }
                    ),
                )
            elif endpoint == "/services":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "timestamp": "2024-01-01T00:00:00",
                            "services": {"redis": {"status": "healthy"}},
                        }
                    ),
                )
            elif endpoint == "/celery":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "timestamp": "2024-01-01T00:00:00",
                            "celery": {"workers": {"status": "healthy", "active_workers": 2}},
                        }
                    ),
                )
            elif endpoint == "/ingestion":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "timestamp": "2024-01-01T00:00:00",
                            "analytics": {"total_articles": 100, "recent_articles": 10},
                        }
                    ),
                )
            else:
                route.fulfill(status=404)

        page.route("**/api/health*", mock_health_check)

        page.goto(f"{base_url}/diags")

        # Click Run All Checks button
        run_all_button = page.locator("#runAllHealthChecks")
        run_all_button.click()

        # Wait for loading overlay to appear then disappear
        loading_overlay = page.locator("#loadingOverlay")
        loading_overlay.wait_for(state="visible", timeout=2000)
        loading_overlay.wait_for(state="hidden", timeout=15000)

    @pytest.mark.ui
    def test_database_health_check(self, page: Page):
        """Test database health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def mock_health(route):
            url = route.request.url
            if "/api/health/database" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "database": {"connection": "connected", "total_articles": 100, "total_sources": 5},
                        }
                    ),
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "healthy"}),
                )
            else:
                route.continue_()

        page.route("**/api/health**", mock_health)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        db_content = page.locator("#databaseHealthContent")
        expect(db_content).to_contain_text("100", timeout=5000)
        expect(db_content).to_contain_text("connected")

    @pytest.mark.ui
    def test_deduplication_health_check(self, page: Page):
        """Test deduplication health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def mock_health(route):
            url = route.request.url
            if "/api/health/deduplication" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "deduplication": {
                                "exact_duplicates": {"content_hash_duplicates": 0},
                                "near_duplicates": {"simhash_coverage": "95%"},
                            },
                        }
                    ),
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "healthy"}),
                )
            else:
                route.continue_()

        page.route("**/api/health**", mock_health)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        dedup_content = page.locator("#deduplicationHealthContent")
        expect(dedup_content).to_contain_text("0", timeout=5000)

    @pytest.mark.ui
    def test_services_health_check(self, page: Page):
        """Test services health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def mock_health(route):
            url = route.request.url
            if "/api/health/services" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "healthy", "services": {"redis": {"status": "healthy"}}}),
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "healthy"}),
                )
            else:
                route.continue_()

        page.route("**/api/health**", mock_health)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        services_content = page.locator("#servicesHealthContent")
        expect(services_content).to_contain_text(re.compile(r"redis", re.I), timeout=5000)

    @pytest.mark.ui
    def test_celery_health_check(self, page: Page):
        """Test Celery health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def mock_health(route):
            url = route.request.url
            if "/api/health/celery" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "celery": {"workers": {"status": "healthy", "active_workers": 2}},
                        }
                    ),
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "healthy"}),
                )
            else:
                route.continue_()

        page.route("**/api/health**", mock_health)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        celery_content = page.locator("#celeryHealthContent")
        expect(celery_content).to_contain_text(re.compile(r"healthy|✓|WORKERS"), timeout=5000)

    @pytest.mark.ui
    def test_health_check_error_handling(self, page: Page):
        """Test health check error handling when Run All triggers a failed check."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def mock_health(route):
            url = route.request.url
            if "/api/health/database" in url:
                route.fulfill(
                    status=500,
                    content_type="application/json",
                    body=json.dumps({"status": "error", "error": "Service unavailable"}),
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "healthy"}),
                )
            else:
                route.continue_()

        page.route("**/api/health**", mock_health)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        db_content = page.locator("#databaseHealthContent")
        expect(db_content).to_contain_text("unavailable", timeout=5000)

    @pytest.mark.ui
    def test_loading_overlay_functionality(self, page: Page):
        """Test loading overlay shows and hides when Run All Health Checks is clicked."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def mock_health(route):
            if "/api/health" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body='{"status": "healthy"}')
            else:
                route.continue_()

        page.route("**/api/health**", mock_health)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        loading_overlay = page.locator("#loadingOverlay")
        expect(loading_overlay).to_be_visible()
        expect(loading_overlay).to_be_hidden(timeout=15000)

    @pytest.mark.ui
    def test_health_check_button_styling(self, page: Page):
        """Test health check button exists and has primary styling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")

        # Check Run All Health Checks button has primary styling
        run_all_button = page.locator("#runAllHealthChecks")
        expect(run_all_button).to_be_visible()
        button_class = run_all_button.get_attribute("class") or ""
        assert "btn-primary" in button_class

    @pytest.mark.ui
    def test_health_check_section_headers(self, page: Page):
        """Test health check section headers are correct."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")

        # Check section headers
        headers = [
            "Database Health",
            "External Services",
            "Deduplication System",
            "Celery Workers",
        ]

        for header_text in headers:
            header = page.locator(f"h2:has-text('{header_text}')")
            expect(header).to_be_visible()

    @pytest.mark.ui
    def test_health_check_initial_content(self, page: Page):
        """Test initial content in health check sections."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")

        # Check initial content messages (diags uses single Run All Health Checks button)
        initial_messages = [
            'Click "Run All Health Checks" to check database status',
            'Click "Run All Health Checks" to check external services',
            'Click "Run All Health Checks" to check deduplication status',
            'Click "Run All Health Checks" to check background task processing',
        ]

        for message in initial_messages:
            content = page.locator(f"text={message}")
            expect(content).to_be_visible()

    @pytest.mark.ui
    def test_health_check_navigation(self, page: Page):
        """Test navigation to health checks page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Start from dashboard
        page.goto(f"{base_url}/")

        # Click Health link in navigation
        health_link = page.locator("a[href='/diags']").first
        health_link.click()

        # Verify we're on the health checks page
        expect(page).to_have_url(f"{base_url}/diags")
        expect(page.locator("h1").nth(1)).to_contain_text("System Diagnostics & Health")
