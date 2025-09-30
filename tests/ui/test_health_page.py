"""
Unit tests for the Health page components.
"""
import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from playwright.async_api import Page, expect


class TestHealthPage:
    """Test the Health page functionality."""

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_page_loads(self, page: Page):
        """Test that the Health page loads correctly."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        await page.goto(f"{base_url}/health-checks")
        
        # Check page title and header
        await expect(page).to_have_title("Health Checks - CTI Scraper")
        await expect(page.locator("h1").nth(1)).to_contain_text("🏥 System Health Checks")
        
        # Check description
        await expect(page.locator("p").first).to_contain_text("Monitor system performance, deduplication, and service health")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_buttons_visible(self, page: Page):
        """Test that all health check buttons are visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        await page.goto(f"{base_url}/health-checks")
        
        # Check all health check buttons are visible
        buttons = [
            "runAllChecks",
            "runDatabaseCheck", 
            "runDeduplicationCheck",
            "runServicesCheck",
            "runCeleryCheck",
            "runIngestionCheck"
        ]
        
        for button_id in buttons:
            button = page.locator(f"#{button_id}")
            await expect(button).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_sections_visible(self, page: Page):
        """Test that all health check sections are visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        await page.goto(f"{base_url}/health-checks")
        
        # Check all health check sections are visible
        sections = [
            "databaseHealthContent",
            "deduplicationHealthContent", 
            "servicesHealthContent",
            "celeryHealthContent",
            "ingestionAnalyticsContent"
        ]
        
        for section_id in sections:
            section = page.locator(f"#{section_id}")
            await expect(section).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_run_all_checks_button_click(self, page: Page):
        """Test that Run All Checks button triggers all health checks."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        
        # Mock all health check API responses
        async def mock_health_check(route, request):
            endpoint = request.url.split('/api/health')[-1]
            if endpoint == '':
                # Overall health check
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "database": {"status": "connected", "sources": 5, "articles": 100}, "version": "2.0.0"}'
                )
            elif endpoint == '/database':
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "database": {"status": "connected", "sources": 5, "articles": 100, "duplicates": 10}}'
                )
            elif endpoint == '/deduplication':
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "deduplication": {"status": "healthy", "similarity_threshold": 0.85, "total_hashes": 1000}}'
                )
            elif endpoint == '/services':
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "services": {"redis": {"status": "healthy"}, "ollama": {"status": "healthy"}}}'
                )
            elif endpoint == '/celery':
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "celery": {"workers": {"status": "healthy", "active_workers": 2}}}'
                )
            elif endpoint == '/ingestion':
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "analytics": {"total_articles": 100, "recent_articles": 10}}'
                )
            else:
                await route.fulfill(status=404)
        
        await page.route("**/api/health*", mock_health_check)
        
        await page.goto(f"{base_url}/health-checks")
        
        # Click Run All Checks button
        run_all_button = page.locator("#runAllChecks")
        await run_all_button.click()
        
        # Wait for loading overlay to appear and disappear
        loading_overlay = page.locator("#loadingOverlay")
        await expect(loading_overlay).to_be_visible()
        await expect(loading_overlay).to_be_hidden()

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_database_health_check(self, page: Page):
        """Test database health check functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")

        # Mock database health check response
        async def mock_database_health(route, request):
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "database": {"connection": "connected", "total_articles": 100, "total_sources": 5, "simhash": {"coverage": "95%"}, "deduplication": {"total_articles": 100, "unique_urls": 95, "duplicate_rate": "5%"}, "performance": [{"test": "articles_query", "query_time_ms": 45, "rows_returned": 100}]}}'
            )

        await page.route("**/api/health/database", mock_database_health)

        await page.goto(f"{base_url}/health-checks")

        # Click Database Health button
        db_button = page.locator("#runDatabaseCheck")
        await db_button.click()

        # Wait for content to update and check for success indicators
        db_content = page.locator("#databaseHealthContent")
        await expect(db_content).to_contain_text("Database Connection")
        await expect(db_content).to_contain_text("100")
        await expect(db_content).to_contain_text("connected")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_deduplication_health_check(self, page: Page):
        """Test deduplication health check functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")

        # Mock deduplication health check response
        async def mock_deduplication_health(route, request):
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "deduplication": {"exact_duplicates": {"content_hash_duplicates": 0, "duplicate_details": []}, "near_duplicates": {"potential_near_duplicates": 0, "simhash_coverage": "95%"}, "simhash_buckets": {"bucket_distribution": [{"bucket_id": 1, "articles_count": 10}], "most_active_bucket": [1, 10]}}}'
            )

        await page.route("**/api/health/deduplication", mock_deduplication_health)

        await page.goto(f"{base_url}/health-checks")

        # Click Deduplication Health button
        dedup_button = page.locator("#runDeduplicationCheck")
        await dedup_button.click()

        # Wait for content to update and check for success indicators
        dedup_content = page.locator("#deduplicationHealthContent")
        await expect(dedup_content).to_contain_text("Exact Duplicates")
        await expect(dedup_content).to_contain_text("0")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_services_health_check(self, page: Page):
        """Test services health check functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")

        # Mock services health check response
        async def mock_services_health(route, request):
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "services": {"redis": {"status": "healthy", "info": {"used_memory": 1024}}, "ollama": {"status": "healthy", "models_available": 2, "models": ["llama2", "codellama"]}}}'
            )

        await page.route("**/api/health/services", mock_services_health)

        await page.goto(f"{base_url}/health-checks")

        # Click Services Health button
        services_button = page.locator("#runServicesCheck")
        await services_button.click()

        # Wait for content to update and check for success indicators
        services_content = page.locator("#servicesHealthContent")
        await expect(services_content).to_contain_text("REDIS")
        await expect(services_content).to_contain_text("OLLAMA")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_celery_health_check(self, page: Page):
        """Test Celery health check functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        
        # Mock Celery health check response
        async def mock_celery_health(route, request):
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "celery": {"workers": {"status": "healthy", "active_workers": 2}, "broker": {"status": "healthy"}}}'
            )
        
        await page.route("**/api/health/celery", mock_celery_health)
        
        await page.goto(f"{base_url}/health-checks")
        
        # Click Celery Health button
        celery_button = page.locator("#runCeleryCheck")
        await celery_button.click()
        
        # Check that Celery health content is updated
        celery_content = page.locator("#celeryHealthContent")
        await expect(celery_content).to_contain_text("healthy")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_ingestion_analytics_check(self, page: Page):
        """Test ingestion analytics check functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")

        # Mock ingestion analytics response
        async def mock_ingestion_analytics(route, request):
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00", "ingestion": {"total_stats": {"total_articles": 100, "total_sources": 5, "earliest_article": "2024-01-01T00:00:00", "latest_article": "2024-01-01T23:59:59"}, "daily_trends": [{"date": "2024-01-01", "articles_count": 5, "sources_count": 2}], "hunt_score_ranges": [{"date": "2024-01-01", "excellent": 2, "good": 1, "moderate": 1, "low": 1, "minimal": 0}], "hourly_distribution": [{"hour": 0, "articles_count": 1}], "source_breakdown": [{"source_name": "Test Source", "articles_count": 5, "avg_hunt_score": 75.5, "chosen_ratio": "60%", "chosen_count": 3, "rejected_ratio": "20%", "rejected_count": 1, "unclassified_ratio": "20%", "unclassified_count": 1}]}}'
            )

        await page.route("**/api/health/ingestion", mock_ingestion_analytics)

        await page.goto(f"{base_url}/health-checks")

        # Click Ingestion Analytics button
        ingestion_button = page.locator("#runIngestionCheck")
        await ingestion_button.click()

        # Wait for content to update and check for success indicators
        ingestion_content = page.locator("#ingestionAnalyticsContent")
        await expect(ingestion_content).to_contain_text("Total Articles")
        await expect(ingestion_content).to_contain_text("100")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_error_handling(self, page: Page):
        """Test health check error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")

        # Mock error response
        async def mock_health_error(route, request):
            await route.fulfill(
                status=500,
                content_type="application/json",
                body='{"status": "error", "error": "Service unavailable"}'
            )

        await page.route("**/api/health/database", mock_health_error)

        await page.goto(f"{base_url}/health-checks")

        # Click Database Health button
        db_button = page.locator("#runDatabaseCheck")
        await db_button.click()

        # Check that error is handled gracefully
        db_content = page.locator("#databaseHealthContent")
        await expect(db_content).to_contain_text("Database Health Check Failed")
        await expect(db_content).to_contain_text("Service unavailable")

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_loading_overlay_functionality(self, page: Page):
        """Test loading overlay shows and hides correctly."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        
        # Mock slow response
        async def mock_slow_health(route, request):
            import asyncio
            await asyncio.sleep(0.5)  # Simulate slow response
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"status": "healthy", "timestamp": "2024-01-01T00:00:00"}'
            )
        
        await page.route("**/api/health/database", mock_slow_health)
        
        await page.goto(f"{base_url}/health-checks")
        
        # Click Database Health button
        db_button = page.locator("#runDatabaseCheck")
        await db_button.click()
        
        # Check loading overlay appears
        loading_overlay = page.locator("#loadingOverlay")
        await expect(loading_overlay).to_be_visible()
        
        # Check loading message
        loading_message = page.locator("#loadingMessage")
        await expect(loading_message).to_contain_text("Checking database")
        
        # Wait for loading overlay to disappear
        await expect(loading_overlay).to_be_hidden()

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_button_styling(self, page: Page):
        """Test health check button styling and classes."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        await page.goto(f"{base_url}/health-checks")
        
        # Check Run All Checks button styling
        run_all_button = page.locator("#runAllChecks")
        button_class = await run_all_button.get_attribute("class")
        assert "bg-blue-600" in button_class
        assert "text-white" in button_class
        
        # Check individual health check buttons styling
        db_button = page.locator("#runDatabaseCheck")
        db_button_class = await db_button.get_attribute("class")
        assert "bg-white" in db_button_class
        assert "border-gray-400" in db_button_class

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_section_headers(self, page: Page):
        """Test health check section headers are correct."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        await page.goto(f"{base_url}/health-checks")
        
        # Check section headers
        headers = [
            "🗄️ Database Health",
            "🔍 Deduplication System Health", 
            "🔧 External Services Health",
            "⚙️ Celery Workers Health",
            "📊 Article Ingestion Analytics"
        ]
        
        for header_text in headers:
            header = page.locator(f"h2:has-text('{header_text}')")
            await expect(header).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_initial_content(self, page: Page):
        """Test initial content in health check sections."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")
        await page.goto(f"{base_url}/health-checks")
        
        # Check initial content messages
        initial_messages = [
            "Click \"Database Health\" to check database status",
            "Click \"Deduplication Health\" to check deduplication status",
            "Click \"Services Health\" to check external services",
            "Click \"Celery Health\" to check background task processing",
            "Click \"Ingestion Analytics\" to view article collection trends"
        ]
        
        for message in initial_messages:
            content = page.locator(f"text={message}")
            await expect(content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.asyncio
    async def test_health_check_navigation(self, page: Page):
        """Test navigation to health checks page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8000")

        # Start from dashboard
        await page.goto(f"{base_url}/")

        # Click Health link in navigation
        health_link = page.locator("a[href='/health-checks']")
        await health_link.click()

        # Verify we're on the health checks page
        await expect(page).to_have_url(f"{base_url}/health-checks")
        await expect(page.locator("h1").nth(1)).to_contain_text("🏥 System Health Checks")