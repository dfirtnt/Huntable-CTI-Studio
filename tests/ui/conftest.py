"""
Conftest for UI tests - handles Playwright browser availability checks.

Note: UI tests require Playwright browsers to be installed.
Run 'playwright install' in the Docker container before running UI tests.
These tests are marked with @pytest.mark.ui and will be excluded from normal test runs.
"""
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
        result = sock.connect_ex(('localhost', 8001))
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
            item.add_marker(pytest.mark.skip(reason="Playwright browsers not installed. Run 'playwright install' in Docker container"))
        elif not WEB_SERVER_AVAILABLE:
            item.add_marker(pytest.mark.skip(reason="Web server not accessible on localhost:8001"))
