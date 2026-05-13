"""
Conftest for E2E tests - handles Playwright browser availability checks.

Note: E2E tests require Playwright browsers to be installed.
Run 'playwright install' in the Docker container before running E2E tests.
These tests are marked with @pytest.mark.e2e and will be excluded from normal test runs.

The asyncio running-loop cleanup fixture lives in tests/conftest.py (root conftest)
so it applies to all sync-playwright tests across the entire test suite.
"""

import pytest


@pytest.fixture(autouse=True)
def _e2e_page_timeout(page):
    """Set a 20-second action/navigation timeout on every e2e page fixture.

    The CTI Studio app has persistent SSE/polling connections that keep the network
    active indefinitely.  Without an explicit cap, page.click() can block forever
    waiting for a post-click navigation to 'settle'.  20 s is enough for any real
    load; anything beyond that is a hung test, not a slow server.
    """
    page.set_default_timeout(20000)
    page.set_default_navigation_timeout(20000)
    yield
