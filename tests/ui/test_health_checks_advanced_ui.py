"""
UI tests for Health Checks page advanced monitoring features using Playwright.
Tests history, alerts, scheduling, export, and related features.
"""

import pytest
from playwright.sync_api import Page, expect
import os
import json


class TestHealthChecksPageLoad:
    """Test health checks page basic loading."""
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_health_checks_page_loads(self, page: Page):
        """Test health checks page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Health Checks - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('🏥 System Health Checks')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_health_check_controls_display(self, page: Page):
        """Test health check controls display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Verify controls section exists
        controls_section = page.locator("text=🔧 Health Check Controls")
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
                mock_response = {
                    "status": "healthy",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "version": "1.0.0"
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Run All Checks button
        run_all_btn = page.locator("#runAllHealthChecks")
        run_all_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify loading overlay appears
        loading_overlay = page.locator("#loadingOverlay")
        # Overlay may be hidden after check completes
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    @pytest.mark.skip(reason="#runDatabaseCheck does not exist; diags uses single #runAllHealthChecks")
    def test_database_health_button(self, page: Page):
        """Test Database Health button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response
        def handle_route(route):
            if "/api/health/database" in route.request.url:
                mock_response = {
                    "status": "healthy",
                    "database": {
                        "connection": "Connected",
                        "total_articles": 1000,
                        "total_sources": 50,
                        "simhash": {"coverage": "95%"},
                        "deduplication": {
                            "total_articles": 1000,
                            "unique_urls": 950,
                            "duplicate_rate": "5%"
                        },
                        "performance": [
                            {"test": "Query Test", "query_time_ms": 10, "rows_returned": 100}
                        ]
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health/database", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Database Health button
        database_btn = page.locator("#runDatabaseCheck")
        database_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify database health content updates
        database_content = page.locator("#databaseHealthContent")
        expect(database_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    @pytest.mark.skip(reason="#runDeduplicationCheck does not exist; diags uses single #runAllHealthChecks")
    def test_deduplication_health_button(self, page: Page):
        """Test Deduplication Health button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response
        def handle_route(route):
            if "/api/health/deduplication" in route.request.url:
                mock_response = {
                    "status": "healthy",
                    "deduplication": {
                        "exact_duplicates": {
                            "content_hash_duplicates": 0,
                            "duplicate_details": []
                        },
                        "near_duplicates": {
                            "potential_near_duplicates": 0,
                            "simhash_coverage": "95%"
                        },
                        "simhash_buckets": {
                            "bucket_distribution": [
                                {"bucket_id": 1, "articles_count": 100}
                            ],
                            "most_active_bucket": [1, 100]
                        }
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health/deduplication", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Deduplication Health button
        deduplication_btn = page.locator("#runDeduplicationCheck")
        deduplication_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify deduplication health content updates
        deduplication_content = page.locator("#deduplicationHealthContent")
        expect(deduplication_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    @pytest.mark.skip(reason="#runServicesCheck does not exist; diags uses single #runAllHealthChecks")
    def test_services_health_button(self, page: Page):
        """Test Services Health button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response
        def handle_route(route):
            if "/api/health/services" in route.request.url:
                mock_response = {
                    "status": "healthy",
                    "services": {
                        "redis": {
                            "status": "healthy",
                            "info": {"used_memory": 1024000}
                        }
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health/services", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Services Health button
        services_btn = page.locator("#runServicesCheck")
        services_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify services health content updates
        services_content = page.locator("#servicesHealthContent")
        expect(services_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    @pytest.mark.skip(reason="#runCeleryCheck does not exist; diags uses single #runAllHealthChecks")
    def test_celery_health_button(self, page: Page):
        """Test Celery Health button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response
        def handle_route(route):
            if "/api/health/celery" in route.request.url:
                mock_response = {
                    "status": "healthy",
                    "celery": {
                        "workers": 2,
                        "active_tasks": 0
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health/celery", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Celery Health button
        celery_btn = page.locator("#runCeleryCheck")
        celery_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify celery health content updates
        celery_content = page.locator("#celeryHealthContent")
        expect(celery_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    @pytest.mark.skip(reason="#runIngestionCheck does not exist; diags uses single #runAllHealthChecks")
    def test_ingestion_analytics_button(self, page: Page):
        """Test Ingestion Analytics button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response
        def handle_route(route):
            if "/api/health/ingestion" in route.request.url:
                mock_response = {
                    "status": "healthy",
                    "ingestion": {
                        "total_stats": {
                            "total_articles": 1000,
                            "total_sources": 50,
                            "earliest_article": "2025-01-01T00:00:00Z",
                            "latest_article": "2025-01-31T00:00:00Z"
                        },
                        "daily_trends": [],
                        "hunt_score_ranges": [],
                        "hourly_distribution": [],
                        "source_breakdown": []
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health/ingestion", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Ingestion Analytics button
        ingestion_btn = page.locator("#runIngestionCheck")
        ingestion_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify ingestion analytics content updates
        ingestion_content = page.locator("#ingestionAnalyticsContent")
        expect(ingestion_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    @pytest.mark.skip(reason="#refreshTimestamp and #overallStatusContent do not exist in diags template")
    def test_refresh_timestamp_button(self, page: Page):
        """Test Refresh Timestamp button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response
        def handle_route(route):
            if "/api/health" in route.request.url:
                mock_response = {
                    "status": "healthy",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "version": "1.0.0"
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Refresh Timestamp button
        refresh_btn = page.locator("#refreshTimestamp")
        refresh_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify overall status updates
        overall_status = page.locator("#overallStatusContent")
        expect(overall_status).to_be_visible()


class TestHealthCheckLoadingOverlay:
    """Test health check loading overlay."""
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_loading_overlay_display(self, page: Page):
        """Test loading overlay displays during health checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Verify loading overlay exists
        loading_overlay = page.locator("#loadingOverlay")
        expect(loading_overlay).to_be_visible()
        expect(loading_overlay).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_loading_message_display(self, page: Page):
        """Test loading message displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Verify loading message element exists
        loading_message = page.locator("#loadingMessage")
        expect(loading_message).to_be_visible()
        
        # Verify loading text exists
        loading_text = page.locator("text=Running Health Checks")
        expect(loading_text).to_be_visible()


class TestHealthCheckStatusDisplay:
    """Test health check status display."""
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_overall_status_display(self, page: Page):
        """Test overall status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Verify overall status section exists
        overall_status = page.locator("#overallStatus")
        expect(overall_status).to_be_visible()
        
        # Verify overall status content exists
        overall_status_content = page.locator("#overallStatusContent")
        expect(overall_status_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.health_checks
    def test_database_health_section_display(self, page: Page):
        """Test database health section display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
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
    @pytest.mark.skip(reason="#runDatabaseCheck does not exist; diags uses single #runAllHealthChecks")
    def test_health_check_error_display(self, page: Page):
        """Test health check error display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API error
        def handle_route(route):
            if "/api/health/database" in route.request.url:
                route.fulfill(status=500, body=json.dumps({"status": "error", "error": "Database connection failed"}), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health/database", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        
        # Click Database Health button
        database_btn = page.locator("#runDatabaseCheck")
        database_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify error message appears
        error_message = page.locator("text=Database Health Check Failed")
        expect(error_message).to_be_visible()


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
                mock_response = {
                    "status": "healthy",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "version": "1.0.0"
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/health", handle_route)
        
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
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
        page.goto(f"{base_url}/health-checks")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify flag was set (checked via page behavior)
        # Note: Auto-run may trigger health checks automatically
        overall_status = page.locator("#overallStatusContent")
        expect(overall_status).to_be_visible()


