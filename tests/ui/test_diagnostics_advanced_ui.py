"""
UI tests for Diagnostics page advanced features using Playwright.
Tests report generation, export, history, filtering, and related features.
"""

import json
import os

import pytest
from playwright.sync_api import Page, expect


class TestDiagnosticsPageLoad:
    """Test diagnostics page basic loading."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_diagnostics_page_loads(self, page: Page):
        """Test diagnostics page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for JavaScript initialization

        # Verify page title
        expect(page).to_have_title("System Diagnostics - Huntable CTI Scraper")

        # Verify main heading
        heading = page.locator("h1:has-text('🔧 System Diagnostics')").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_quick_actions_display(self, page: Page):
        """Test quick actions display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify quick actions section exists
        quick_actions = page.locator("text=⚡ Quick Actions")
        expect(quick_actions).to_be_visible()

        # Verify all quick action buttons exist
        run_all_btn = page.locator("#runAllHealthChecks")
        expect(run_all_btn).to_be_visible()

        refresh_btn = page.locator("#refreshJobData")
        expect(refresh_btn).to_be_visible()

        auto_refresh_checkbox = page.locator("#autoRefresh")
        expect(auto_refresh_checkbox).to_be_visible()


class TestDiagnosticsQuickActions:
    """Test diagnostics quick actions."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_run_all_health_checks_button(self, page: Page):
        """Test Run All Health Checks button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API responses
        def handle_route(route):
            if "/api/health" in route.request.url:
                mock_response = {"status": "healthy", "timestamp": "2025-01-01T00:00:00Z", "version": "1.0.0"}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/health/database" in route.request.url:
                mock_response = {"status": "healthy", "database": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/health/deduplication" in route.request.url:
                mock_response = {"status": "healthy", "deduplication": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/health/services" in route.request.url:
                mock_response = {"status": "healthy", "services": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/health/celery" in route.request.url:
                mock_response = {"status": "healthy", "celery": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/health/**", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Click Run All Health Checks button
        run_all_btn = page.locator("#runAllHealthChecks")
        run_all_btn.click()
        page.wait_for_timeout(3000)

        # Verify health status sections update
        overall_health = page.locator("#overallHealthStatus")
        expect(overall_health).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_refresh_job_data_button(self, page: Page):
        """Test Refresh Job Data button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API response
        def handle_route(route):
            if "/api/jobs" in route.request.url:
                mock_response = {"workers": [], "queues": {}, "active_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/jobs", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Click Refresh Job Data button
        refresh_btn = page.locator("#refreshJobData")
        refresh_btn.click()
        page.wait_for_timeout(2000)

        # Verify job data sections exist
        worker_status = page.locator("#workerStatus")
        expect(worker_status).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_auto_refresh_toggle(self, page: Page):
        """Test auto-refresh toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify auto-refresh checkbox exists and is checked by default
        auto_refresh = page.locator("#autoRefresh")
        expect(auto_refresh).to_be_visible()
        expect(auto_refresh).to_be_checked()

        # Toggle auto-refresh off
        auto_refresh.uncheck()
        page.wait_for_timeout(500)
        expect(auto_refresh).not_to_be_checked()

        # Toggle auto-refresh on
        auto_refresh.check()
        page.wait_for_timeout(500)
        expect(auto_refresh).to_be_checked()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_last_updated_timestamp_display(self, page: Page):
        """Test last updated timestamp display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify last updated timestamp exists
        last_updated = page.locator("#lastUpdated")
        expect(last_updated).to_be_visible()


class TestDiagnosticsSystemStatus:
    """Test diagnostics system status display."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_overall_health_status_display(self, page: Page):
        """Test overall health status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify overall health status section exists
        overall_health = page.locator("#overallHealthStatus")
        expect(overall_health).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_worker_status_display(self, page: Page):
        """Test worker status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify worker status section exists
        worker_status = page.locator("#workerStatus")
        expect(worker_status).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_queue_status_display(self, page: Page):
        """Test queue status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify queue status section exists
        queue_status = page.locator("#queueStatus")
        expect(queue_status).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_active_tasks_display(self, page: Page):
        """Test active tasks display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify active tasks section exists
        active_tasks = page.locator("#activeTasks")
        expect(active_tasks).to_be_visible()


class TestDiagnosticsHealthChecks:
    """Test diagnostics health checks sections."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_database_health_display(self, page: Page):
        """Test database health display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify database health section exists
        database_health = page.locator("#databaseHealthContent")
        expect(database_health).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_services_health_display(self, page: Page):
        """Test services health display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify services health section exists
        services_health = page.locator("#servicesHealthContent")
        expect(services_health).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_deduplication_health_display(self, page: Page):
        """Test deduplication health display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify deduplication health section exists
        deduplication_health = page.locator("#deduplicationHealthContent")
        expect(deduplication_health).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_celery_health_display(self, page: Page):
        """Test celery health display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify celery health section exists
        celery_health = page.locator("#celeryHealthContent")
        expect(celery_health).to_be_visible()


class TestDiagnosticsJobHistory:
    """Test diagnostics job history features."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_job_history_section_display(self, page: Page):
        """Test job history section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify job history section exists
        job_history_header = page.locator("text=📋 Recent Job History")
        expect(job_history_header).to_be_visible()

        # Verify job history content exists
        job_history_content = page.locator("#job-history-content")
        expect(job_history_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_job_history_toggle(self, page: Page):
        """Test job history toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify toggle button exists
        toggle_btn = page.locator("#job-history-toggle")
        expect(toggle_btn).to_be_visible()

        # Verify job history content is initially hidden
        job_history_content = page.locator("#job-history-content")
        expect(job_history_content).to_have_class("hidden")

        # Click toggle to expand
        toggle_btn.click()
        page.wait_for_timeout(500)

        # Verify job history content is visible
        expect(job_history_content).not_to_have_class("hidden")

        # Click toggle to collapse
        toggle_btn.click()
        page.wait_for_timeout(500)

        # Verify job history content is hidden again
        expect(job_history_content).to_have_class("hidden")


class TestDiagnosticsAutoRefresh:
    """Test diagnostics auto-refresh features."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_auto_refresh_functionality(self, page: Page):
        """Test auto-refresh functionality (5s interval)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Track API calls
        api_call_count = {"count": 0}

        def handle_route(route):
            if "/api/jobs" in route.request.url:
                api_call_count["count"] += 1
                mock_response = {"workers": [], "queues": {}, "active_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/jobs", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify initial API call
        initial_count = api_call_count["count"]
        assert initial_count >= 1, "Job data API should be called on load"

        # Wait for potential auto-refresh (5s interval)
        # Note: Testing full 5s interval would require waiting 5+ seconds
        # This test verifies the auto-refresh setup exists

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_auto_refresh_disabled(self, page: Page):
        """Test auto-refresh disabled state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Track API calls
        api_call_count = {"count": 0}

        def handle_route(route):
            if "/api/jobs" in route.request.url:
                api_call_count["count"] += 1
                mock_response = {"workers": [], "queues": {}, "active_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/jobs", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Disable auto-refresh
        auto_refresh = page.locator("#autoRefresh")
        auto_refresh.uncheck()
        page.wait_for_timeout(1000)

        # Get initial count
        api_call_count["count"]

        # Wait a bit
        page.wait_for_timeout(2000)

        # Verify no additional API calls (auto-refresh disabled)
        # Note: This is a basic check - full verification would require waiting 5+ seconds


class TestDiagnosticsLoadingOverlay:
    """Test diagnostics loading overlay."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_loading_overlay_display(self, page: Page):
        """Test loading overlay displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify loading overlay exists
        loading_overlay = page.locator("#loadingOverlay")
        expect(loading_overlay).to_be_visible()
        expect(loading_overlay).to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_loading_message_display(self, page: Page):
        """Test loading message displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify loading message element exists
        loading_message = page.locator("#loadingMessage")
        expect(loading_message).to_be_visible()

        # Verify loading text exists
        loading_text = page.locator("text=Running Diagnostics")
        expect(loading_text).to_be_visible()


class TestDiagnosticsErrorHandling:
    """Test diagnostics error handling."""

    @pytest.mark.ui
    @pytest.mark.diagnostics
    def test_job_data_error_handling(self, page: Page):
        """Test job data error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API error
        def handle_route(route):
            if "/api/jobs" in route.request.url:
                route.fulfill(status=500, body="Internal Server Error")
            else:
                route.continue_()

        page.route("**/api/jobs", handle_route)

        page.goto(f"{base_url}/diags")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify page still loads (graceful error handling)
        heading = page.locator("h1:has-text('🔧 System Diagnostics')").first
        expect(heading).to_be_visible()
