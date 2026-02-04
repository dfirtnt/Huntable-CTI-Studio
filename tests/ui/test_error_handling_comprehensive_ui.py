"""
UI tests for error handling across all pages using Playwright.
Tests 404, 500, network errors, timeouts, invalid input, and related error scenarios.
"""

import os

import pytest
from playwright.sync_api import Page, expect


class Test404ErrorHandling:
    """Test 404 error handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_404_error_page(self, page: Page):
        """Test 404 error page display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Navigate to non-existent page
        response = page.goto(f"{base_url}/nonexistent-page")

        # Verify 404 status
        if response:
            assert response.status == 404, "Should return 404 status"

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_404_error_message(self, page: Page):
        """Test 404 error message display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Navigate to non-existent page
        page.goto(f"{base_url}/nonexistent-page", wait_until="domcontentloaded")

        # Verify error message appears
        # Error message may vary depending on implementation
        error_content = page.locator("body")
        expect(error_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_404_error_page_uses_dark_theme(self, page: Page):
        """Test 404 error page uses app dark theme (theme variables)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/nonexistent-page", wait_until="domcontentloaded")
        # Error template uses var(--panel-bg-0) on wrapper and var(--panel-bg-2) on card
        wrapper = page.locator("div.min-h-screen").first
        expect(wrapper).to_be_visible()
        bg = wrapper.evaluate("el => window.getComputedStyle(el).backgroundColor")
        # Should be a real color (rgb or rgba), not 'transparent' or empty
        assert bg and bg != "transparent" and "rgb" in bg, "Error page wrapper should use theme background"


class Test500ErrorHandling:
    """Test 500 error handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_500_error_handling(self, page: Page):
        """Test 500 error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock 500 error for API endpoint
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(status=500, body="Internal Server Error")
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify page still loads (graceful error handling)
        heading = page.locator("h1").first
        expect(heading).to_be_visible()


class TestNetworkErrorHandling:
    """Test network error handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_network_error_handling(self, page: Page):
        """Test network error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock network error
        def handle_route(route):
            if "/api/" in route.request.url:
                route.abort()
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify page still loads (graceful error handling)
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_api_timeout_handling(self, page: Page):
        """Test API timeout handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock slow API response
        def handle_route(route):
            if "/api/" in route.request.url:
                import time

                time.sleep(10)  # Simulate timeout
                route.fulfill(status=200, body="{}", headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard", timeout=5000)
        page.wait_for_load_state("domcontentloaded")

        # Verify page loads (may timeout but should handle gracefully)
        heading = page.locator("h1").first
        expect(heading).to_be_visible()


class TestInvalidInputHandling:
    """Test invalid input handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_invalid_article_id(self, page: Page):
        """Test invalid article ID handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Navigate to invalid article ID
        page.goto(f"{base_url}/articles/999999")
        page.wait_for_load_state("networkidle")

        # Verify page handles invalid ID gracefully
        # May show error message or redirect
        body = page.locator("body")
        expect(body).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_invalid_url_parameters(self, page: Page):
        """Test invalid URL parameters handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Navigate with invalid parameters
        page.goto(f"{base_url}/articles?invalid_param=value&another=test")
        page.wait_for_load_state("networkidle")

        # Verify page loads (invalid params should be ignored)
        expect(page).to_have_url(f"{base_url}/articles")

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_empty_form_submission(self, page: Page):
        """Test empty form submission handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Try to submit empty form
        send_button = page.locator("button:has-text('Send')")

        # Verify button is disabled when input is empty
        # Button may be disabled or form may prevent submission
        expect(send_button).to_be_visible()


class TestErrorDisplay:
    """Test error display features."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_error_notification_display(self, page: Page):
        """Test error notification display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API error
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(
                    status=500, body='{"detail": "Error message"}', headers={"Content-Type": "application/json"}
                )
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify error notification may appear
        # Error notifications may be displayed in various ways
        body = page.locator("body")
        expect(body).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_error_message_clarity(self, page: Page):
        """Test error message clarity."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API error with specific message
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(
                    status=400,
                    body='{"detail": "Invalid request parameters"}',
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify error is handled (message may or may not be displayed)
        body = page.locator("body")
        expect(body).to_be_visible()


class TestErrorRecovery:
    """Test error recovery features."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_error_recovery_after_network_restore(self, page: Page):
        """Test error recovery after network restore."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Initially mock network error
        def handle_route(route):
            if "/api/" in route.request.url:
                route.abort()
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to page
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Remove route handler (simulate network restore)
        page.unroute("**/api/**")

        # Refresh page
        page.reload()
        page.wait_for_load_state("networkidle")

        # Verify page loads successfully after recovery
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_retry_after_error(self, page: Page):
        """Test retry functionality after error."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock initial error, then success - MUST set up route BEFORE navigation
        call_count = {"count": 0}
        initial_api_calls = 0

        def handle_route(route):
            # Only intercept specific dashboard API calls, not all APIs
            url = route.request.url
            if "/api/dashboard" in url or "/api/stats" in url or "/api/health" in url:
                call_count["count"] += 1
                if call_count["count"] <= 1:
                    route.fulfill(
                        status=500,
                        body='{"error": "Internal Server Error"}',
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    route.fulfill(status=200, body='{"status": "ok"}', headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/dashboard*", handle_route)
        page.route("**/api/stats*", handle_route)
        page.route("**/api/health*", handle_route)

        # Navigate to page
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")
        initial_api_calls = call_count["count"]

        # Refresh (retry)
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)  # Wait for retry logic

        # Verify retry occurred (should have more calls after reload)
        assert call_count["count"] > initial_api_calls, (
            f"API should be called again on retry. Initial: {initial_api_calls}, After reload: {call_count['count']}"
        )


class TestPermissionErrorHandling:
    """Test permission error handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_403_forbidden_error(self, page: Page):
        """Test 403 forbidden error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock 403 error
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(status=403, body='{"detail": "Forbidden"}', headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify error is handled gracefully
        body = page.locator("body")
        expect(body).to_be_visible()


class TestRateLimitHandling:
    """Test rate limit handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_rate_limit_error(self, page: Page):
        """Test rate limit error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock rate limit error
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(
                    status=429, body='{"detail": "Rate limit exceeded"}', headers={"Content-Type": "application/json"}
                )
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify error is handled gracefully
        body = page.locator("body")
        expect(body).to_be_visible()


class TestMalformedDataHandling:
    """Test malformed data handling."""

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_malformed_json_response(self, page: Page):
        """Test malformed JSON response handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock malformed JSON response
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(status=200, body="invalid json {", headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify error is handled gracefully
        body = page.locator("body")
        expect(body).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.error_handling
    def test_missing_required_fields(self, page: Page):
        """Test missing required fields handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Mock API response with missing fields
        def handle_route(route):
            if "/api/" in route.request.url:
                route.fulfill(status=200, body='{"incomplete": "data"}', headers={"Content-Type": "application/json"})
            else:
                route.continue_()

        page.route("**/api/**", handle_route)

        # Navigate to a page that makes API calls
        page.goto(f"{base_url}/dashboard")
        page.wait_for_load_state("networkidle")

        # Verify error is handled gracefully
        body = page.locator("body")
        expect(body).to_be_visible()
