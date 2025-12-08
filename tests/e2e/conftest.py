import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="session")
def browser_context_args():
    """Browser context arguments for Playwright tests"""
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
        "record_video_dir": "test-results/videos/",
        "record_video_size": {"width": 1280, "height": 720},
    }

@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Browser launch arguments"""
    return {
        "headless": True,
        "slow_mo": 100,  # Slow down actions for better debugging
    }

@pytest.fixture(scope="session")
def playwright_context():
    """Playwright context for session-scoped tests"""
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser(playwright_context):
    """Browser instance for session-scoped tests"""
    browser = playwright_context.chromium.launch(headless=True)
    yield browser
    browser.close()

@pytest.fixture(scope="session")
def context(browser):
    """Browser context for session-scoped tests"""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
        record_video_dir="test-results/videos/",
    )
    yield context
    context.close()

@pytest.fixture
def page(context):
    """Page instance for each test"""
    page = context.new_page()
    yield page
    page.close()

@pytest.fixture
def firefox_page(playwright_context):
    """Firefox browser page for multi-browser testing"""
    browser = playwright_context.firefox.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    page = context.new_page()
    yield page
    page.close()
    context.close()
    browser.close()

@pytest.fixture
def webkit_page(playwright_context):
    """WebKit (Safari) browser page for multi-browser testing"""
    browser = playwright_context.webkit.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
    )
    page = context.new_page()
    yield page
    page.close()
    context.close()
    browser.close()
