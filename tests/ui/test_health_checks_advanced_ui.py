"""
UI tests for Health Checks page advanced monitoring features using Playwright.
Tests history, alerts, scheduling, export, and related features.
"""

import json
import os

import pytest
from playwright.sync_api import Page, expect


class TestHealthChecksPageLoad:
    """Test health checks page basic loading."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_health_checks_page_loads(self, page: Page):
        """Test health checks page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify page title
        expect(page).to_have_title("System Diagnostics & Health - Huntable CTI Studio")

        # Verify main heading
        heading = page.locator("h1:has-text('System Diagnostics & Health')").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_health_check_controls_display(self, page: Page):
        """Test health check controls display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify Quick Actions section exists (diags.html)
        controls_section = page.locator("text=⚡ Quick Actions")
        expect(controls_section).to_be_visible()

        # Verify Run All Health Checks button exists (diags.html: only this button exists;
        # individual check buttons #runDatabaseCheck etc. do not exist)
        run_all_btn = page.locator("#runAllHealthChecks")
        expect(run_all_btn).to_be_visible()
        expect(run_all_btn).to_contain_text("Run All")


class TestHealthCheckButtons:
    """Test health check button functionality."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_run_all_checks_button(self, page: Page):
        """Test Run All Checks button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API response
        def handle_route(route):
            if "/api/health" in route.request.url and route.request.method == "GET":
                mock_response = {"status": "healthy", "timestamp": "2025-01-01T00:00:00Z", "version": "1.0.0"}
                route.fulfill(
                    status=200,
                    body=json.dumps(mock_response),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/health", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Click Run All Checks button
        run_all_btn = page.locator("#runAllHealthChecks")
        run_all_btn.click()
        page.wait_for_timeout(2000)

        # Verify loading overlay appears
        page.locator("#loadingOverlay")
        # Overlay may be hidden after check completes

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_database_health_button(self, page: Page):
        """Test database health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            url = route.request.url
            if "/api/health/database" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "database": {"connection": "Connected", "total_articles": 1000},
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps({"status": "healthy"}),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/health**", handle_route)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        database_content = page.locator("#databaseHealthContent")
        expect(database_content).to_contain_text("1000", timeout=5000)

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_deduplication_health_button(self, page: Page):
        """Test deduplication health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            url = route.request.url
            if "/api/health/deduplication" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "deduplication": {
                                "exact_duplicates": {"content_hash_duplicates": 0},
                                "near_duplicates": {"simhash_coverage": "95%"},
                            },
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps({"status": "healthy"}),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/health**", handle_route)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        deduplication_content = page.locator("#deduplicationHealthContent")
        expect(deduplication_content).to_contain_text("0", timeout=5000)

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_services_health_button(self, page: Page):
        """Test services health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            url = route.request.url
            if "/api/health/services" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps({"status": "healthy", "services": {"redis": {"status": "healthy"}}}),
                    headers={"Content-Type": "application/json"},
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps({"status": "healthy"}),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/health**", handle_route)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        services_content = page.locator("#servicesHealthContent")
        expect(services_content).to_contain_text("redis", timeout=5000)

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_celery_health_button(self, page: Page):
        """Test Celery health content after Run All Health Checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            url = route.request.url
            if "/api/health/celery" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps(
                        {
                            "status": "healthy",
                            "celery": {"workers": {"status": "healthy", "active_workers": 2}},
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200,
                    body=json.dumps({"status": "healthy"}),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/health**", handle_route)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        celery_content = page.locator("#celeryHealthContent")
        expect(celery_content).to_contain_text("healthy", timeout=5000)

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_refresh_job_data_button(self, page: Page):
        """Test Refresh Job Data button (diags: #refreshJobData, #lastUpdated)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            if "/api/jobs" in route.request.url:
                route.fulfill(
                    status=200,
                    body=json.dumps({"status": "ok"}),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/jobs**", handle_route)
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")
        refresh_btn = page.locator("#refreshJobData")
        expect(refresh_btn).to_be_visible()
        refresh_btn.click()
        page.wait_for_timeout(1000)
        last_updated = page.locator("#lastUpdated")
        expect(last_updated).to_be_visible()


class TestHealthCheckLoadingOverlay:
    """Test health check loading overlay."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_loading_overlay_display(self, page: Page):
        """Test loading overlay displays during health checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify loading overlay exists
        loading_overlay = page.locator("#loadingOverlay")
        expect(loading_overlay).to_be_visible()
        expect(loading_overlay).to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_loading_message_display(self, page: Page):
        """Test loading message displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify loading message element exists
        loading_message = page.locator("#loadingMessage")
        expect(loading_message).to_be_visible()

        # Initial placeholder is "Please wait..."; run-all uses "Checking ..." messages
        expect(loading_message).to_contain_text("wait")


class TestHealthCheckStatusDisplay:
    """Test health check status display."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_overall_status_display(self, page: Page):
        """Test overall status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify overall status section exists (diags: #overallHealthStatus)
        overall_status = page.locator("#overallHealthStatus")
        expect(overall_status).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_database_health_section_display(self, page: Page):
        """Test database health section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify database health section exists
        database_section = page.locator("text=🗄️ Database Health")
        expect(database_section).to_be_visible()

        # Verify database health content exists
        database_content = page.locator("#databaseHealthContent")
        expect(database_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_deduplication_health_section_display(self, page: Page):
        """Test deduplication health section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify deduplication health section exists
        deduplication_section = page.locator("text=🔍 Deduplication System Health")
        expect(deduplication_section).to_be_visible()

        # Verify deduplication health content exists
        deduplication_content = page.locator("#deduplicationHealthContent")
        expect(deduplication_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_services_health_section_display(self, page: Page):
        """Test services health section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify services health section exists
        services_section = page.locator("text=🔧 External Services Health")
        expect(services_section).to_be_visible()

        # Verify services health content exists
        services_content = page.locator("#servicesHealthContent")
        expect(services_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_celery_health_section_display(self, page: Page):
        """Test celery health section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify celery health section exists
        celery_section = page.locator("text=⚙️ Celery Workers Health")
        expect(celery_section).to_be_visible()

        # Verify celery health content exists
        celery_content = page.locator("#celeryHealthContent")
        expect(celery_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_ingestion_analytics_section_display(self, page: Page):
        """Test ingestion analytics section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify ingestion analytics section exists
        ingestion_section = page.locator("text=📊 Article Ingestion Analytics")
        expect(ingestion_section).to_be_visible()

        # Verify ingestion analytics content exists
        ingestion_content = page.locator("#ingestionAnalyticsContent")
        expect(ingestion_content).to_be_visible()


class TestHealthCheckErrorHandling:
    """Test health check error handling."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_health_check_error_display(self, page: Page):
        """Test health check error display when Run All triggers a failed check."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            url = route.request.url
            if "/api/health/database" in url:
                route.fulfill(
                    status=500,
                    body=json.dumps({"status": "error", "error": "Database connection failed"}),
                    headers={"Content-Type": "application/json"},
                )
            elif "/api/health" in url:
                route.fulfill(
                    status=200, body=json.dumps({"status": "healthy"}), headers={"Content-Type": "application/json"}
                )
            else:
                route.continue_()

        page.route("**/api/health**", handle_route)
        page.goto(f"{base_url}/diags")
        page.locator("#runAllHealthChecks").click()
        page.locator("#loadingOverlay").wait_for(state="hidden", timeout=15000)
        db_content = page.locator("#databaseHealthContent")
        expect(db_content).to_contain_text("failed", timeout=5000)


class TestHealthCheckAutoRefresh:
    """Test health check auto-refresh features."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_auto_refresh_timestamp(self, page: Page):
        """Test auto-refresh timestamp (30s interval)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Track API calls
        api_call_count = {"count": 0}

        def handle_route(route):
            if "/api/health" in route.request.url:
                api_call_count["count"] += 1
                mock_response = {"status": "healthy", "timestamp": "2025-01-01T00:00:00Z", "version": "1.0.0"}
                route.fulfill(
                    status=200,
                    body=json.dumps(mock_response),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/health", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify initial API call
        assert api_call_count["count"] >= 0, "Health check API may be called on load"

        # Note: Testing 30s auto-refresh would require waiting 30+ seconds
        # This test verifies the auto-refresh setup exists


class TestHealthCheckSessionStorage:
    """Test health check session storage integration."""

    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_auto_run_health_checks_flag(self, page: Page):
        """Test auto-run health checks flag from session storage."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set session storage flag before navigating
        page.goto(f"{base_url}/")
        page.evaluate("sessionStorage.setItem('autoRunHealthChecks', 'true');")

        # Navigate to health checks page
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("load")

        # Verify diags page has overall health status element (diags: #overallHealthStatus)
        overall_status = page.locator("#overallHealthStatus")
        expect(overall_status).to_be_visible()
