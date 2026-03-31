"""
Conftest for UI tests - handles Playwright browser availability checks.

Note: UI tests require Playwright browsers to be installed.
Run 'playwright install' in the Docker container before running UI tests.
These tests are marked with @pytest.mark.ui and will be excluded from normal test runs.
"""

from urllib.parse import urlparse

import pytest

# Try to import Playwright
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


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


# Check if Playwright browsers are installed (lazy check)
def check_playwright_browsers():
    """Check if Playwright browsers are installed"""
    if not PLAYWRIGHT_AVAILABLE:
        return False
    try:
        with sync_playwright() as p:
            # Try to get browser type - this will fail if browsers aren't installed
            _ = p.chromium
            return True
    except Exception as e:
        error_str = str(e)
        if "Executable doesn't exist" in error_str or "playwright install" in error_str.lower():
            return False
        # Re-raise other exceptions
        raise


class _UrlAwarePage:
    """Transparent proxy around a Playwright Page that deduplicates same-URL navigations.

    When multiple tests in the same class all call ``page.goto("/same/path")``,
    only the first navigation hits the network; subsequent calls return
    immediately because the browser tab is already at that URL.

    All other attributes and methods delegate transparently to the underlying
    Playwright Page, so no test code needs to change.

    ``wait_for_load_state()`` after a skipped goto is a no-op on an already-loaded
    page, so the guard idiom ``page.goto(url); page.wait_for_load_state("load")``
    remains safe without modification.
    """

    def __init__(self, pw_page):
        object.__setattr__(self, "_pw", pw_page)

    def goto(self, url, **kwargs):
        pw = object.__getattribute__(self, "_pw")
        try:
            current = urlparse(pw.url)
            target = urlparse(url)
            # Skip navigation when already on the same scheme+host+path.
            # Empty path ("about:blank") is never skipped.
            if (
                current.path
                and current.scheme == target.scheme
                and current.netloc == target.netloc
                and current.path == target.path
            ):
                return None
        except Exception:
            pass  # On any parse error fall through to real navigation
        return pw.goto(url, **kwargs)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_pw"), name)

    def __setattr__(self, name, value):
        if name == "_pw":
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_pw"), name, value)


@pytest.fixture(scope="class")
def page(context):
    """Class-scoped page shared across all tests in a test class.

    Overrides the function-scoped ``page`` fixture from the root conftest for
    UI tests.  One browser tab is reused for the lifetime of a test class,
    eliminating repeated same-URL navigations.

    ``page.goto(url)`` is deduplicated: if the tab is already at *url* (matching
    scheme + host + path, ignoring query and fragment) the navigation is skipped.
    This alone removes several hundred redundant page loads across the suite.

    Tests that genuinely need a blank slate between runs should use
    ``fresh_page`` instead.
    """
    pw_page = context.new_page()
    yield _UrlAwarePage(pw_page)
    pw_page.close()


@pytest.fixture
def fresh_page(context):
    """Function-scoped fresh page — a new browser tab for every test.

    Use this when a test must start from ``about:blank`` or when residual
    in-page state from a sibling test would break assertions.
    """
    p = context.new_page()
    yield p
    p.close()


@pytest.fixture(scope="class")
def class_page(context):
    """Class-scoped page for tests that navigate to the same URL in every test.

    Opt in by replacing ``page`` with ``class_page`` in the test class.
    The class is responsible for calling ``page.goto(...)`` once (e.g. in the
    first test or in a ``@pytest.fixture(autouse=True)`` on the class).
    Tests in the class share the same tab, so they must not mutate persistent
    state that would break subsequent tests in the class.

    Available from the root conftest (``context`` fixture is session-scoped).
    """
    try:
        p = context.new_page()
        yield p
        p.close()
    except Exception:
        yield None


# Per-test timeout (seconds). Prevents a single hung test from blocking the
# entire serial UI run.  Requires pytest-timeout (in requirements-test.txt).
# Override per-test with ``@pytest.mark.timeout(N)``.
_UI_TEST_TIMEOUT_SECONDS = 60

try:
    import pytest_timeout  # noqa: F401

    _TIMEOUT_PLUGIN_AVAILABLE = True
except ImportError:
    _TIMEOUT_PLUGIN_AVAILABLE = False


def pytest_itemcollected(item):
    """Apply a default timeout to every UI test that doesn't already have one."""
    if not _TIMEOUT_PLUGIN_AVAILABLE:
        return
    if not item.get_closest_marker("ui") and not item.get_closest_marker("ui_smoke"):
        return
    if item.get_closest_marker("timeout"):
        return
    item.add_marker(pytest.mark.timeout(_UI_TEST_TIMEOUT_SECONDS))


# Hook to skip tests at collection time if Playwright browsers aren't installed
def pytest_collection_modifyitems(config, items):
    """Skip UI tests if Playwright browsers aren't installed"""
    # Lazy check - only check when we have UI tests (including ui_smoke)
    ui_tests = [item for item in items if item.get_closest_marker("ui") or item.get_closest_marker("ui_smoke")]
    if not ui_tests:
        return

    # Check browser availability only if we have UI tests
    try:
        playwright_browsers_installed = check_playwright_browsers()
    except Exception:
        playwright_browsers_installed = False

    for item in ui_tests:
        if not PLAYWRIGHT_AVAILABLE:
            item.add_marker(pytest.mark.skip(reason="Playwright not available"))
        elif not playwright_browsers_installed:
            item.add_marker(
                pytest.mark.skip(
                    reason="Playwright browsers not installed. Run 'playwright install' in Docker container"
                )
            )
        elif not WEB_SERVER_AVAILABLE:
            item.add_marker(pytest.mark.skip(reason="Web server not accessible on localhost:8001"))
