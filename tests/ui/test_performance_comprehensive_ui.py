"""
UI tests for page load performance using Playwright.
Tests page load time, render time, and network request count.

Pruned from 18 tests to 7 -- removed tests with trivially-true assertions
(assert count >= 0), route handlers that measured nothing, and memory tests
that evaluated but never asserted.
"""

import os
import time

import pytest
from playwright.sync_api import Page


@pytest.mark.ui
@pytest.mark.performance
@pytest.mark.slow
class TestPageLoadTime:
    """Test page load time stays within bounds."""

    def test_dashboard_load_time(self, page: Page):
        """Dashboard loads within 5 seconds."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        start_time = time.time()
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")
        load_time = time.time() - start_time

        assert load_time < 5.0, f"Dashboard should load within 5 seconds, took {load_time:.2f}s"

    def test_articles_page_load_time(self, page: Page):
        """Articles page loads within 5 seconds."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        start_time = time.time()
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        load_time = time.time() - start_time

        assert load_time < 5.0, f"Articles page should load within 5 seconds, took {load_time:.2f}s"

    def test_workflow_page_load_time(self, page: Page):
        """Workflow page loads within 10 seconds."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        start_time = time.time()
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        load_time = time.time() - start_time

        assert load_time < 10.0, f"Workflow page should load within 10 seconds, took {load_time:.2f}s"

    def test_chat_page_load_time(self, page: Page):
        """Chat page loads within 10 seconds."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        start_time = time.time()
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("load")
        load_time = time.time() - start_time

        assert load_time < 10.0, f"Chat page should load within 10 seconds, took {load_time:.2f}s"


@pytest.mark.ui
@pytest.mark.performance
@pytest.mark.slow
class TestRenderPerformance:
    """Test rendering performance."""

    def test_initial_render_time(self, page: Page):
        """DOMContentLoaded fires within 2 seconds."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        start_time = time.time()
        page.goto(f"{base_url}/")
        page.wait_for_load_state("domcontentloaded")
        render_time = time.time() - start_time

        assert render_time < 2.0, f"Initial render should complete within 2 seconds, took {render_time:.2f}s"

    def test_chart_rendering_performance(self, page: Page):
        """Analytics page with charts loads within 10 seconds."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        start_time = time.time()
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("load")
        render_time = time.time() - start_time

        assert render_time < 10.0, f"Charts should render within 10 seconds, took {render_time:.2f}s"


@pytest.mark.ui
@pytest.mark.performance
@pytest.mark.slow
class TestNetworkPerformance:
    """Test network request count stays reasonable."""

    def test_network_request_count(self, page: Page):
        """Dashboard page makes fewer than 100 network requests."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        request_count = {"count": 0}

        def handle_route(route):
            request_count["count"] += 1
            route.continue_()

        page.route("**/*", handle_route)

        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        assert request_count["count"] > 0, "Page should make network requests"
        assert request_count["count"] < 100, f"Page should not make excessive requests ({request_count['count']})"
