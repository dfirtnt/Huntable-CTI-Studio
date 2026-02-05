"""
Mobile Playwright Configuration

Configuration for testing mobile features with device emulation
"""

import os

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright


class MobilePlaywrightConfig:
    """Mobile Playwright configuration and device presets"""

    # Mobile device presets
    DEVICES = {
        "iPhone_12_Pro": {
            "viewport": {"width": 390, "height": 844},
            "device_scale_factor": 3,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        },
        "iPhone_SE": {
            "viewport": {"width": 375, "height": 667},
            "device_scale_factor": 2,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        },
        "iPad_Pro": {
            "viewport": {"width": 1024, "height": 1366},
            "device_scale_factor": 2,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        },
        "Android_Pixel_5": {
            "viewport": {"width": 393, "height": 851},
            "device_scale_factor": 2.75,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36",
        },
    }

    @classmethod
    def create_mobile_context(cls, browser: Browser, device: str = "iPhone_12_Pro") -> BrowserContext:
        """Create mobile browser context with device emulation"""
        device_config = cls.DEVICES.get(device, cls.DEVICES["iPhone_12_Pro"])

        return browser.new_context(
            **device_config,
            locale="en-US",
            timezone_id="America/New_York",
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
            record_video_dir="test-results/videos/mobile/",
            record_video_size=device_config["viewport"],
            ignore_https_errors=True,
        )

    @classmethod
    def create_mobile_page(cls, browser: Browser, device: str = "iPhone_12_Pro") -> Page:
        """Create mobile page with device emulation"""
        context = cls.create_mobile_context(browser, device)
        return context.new_page()


@pytest.fixture(scope="session")
def mobile_browser(playwright: Playwright) -> Browser:
    """Mobile browser instance for testing"""
    browser = playwright.chromium.launch(
        headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
        args=[
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    )
    yield browser
    browser.close()


@pytest.fixture
def mobile_context(mobile_browser: Browser) -> BrowserContext:
    """Mobile browser context with iPhone emulation"""
    context = MobilePlaywrightConfig.create_mobile_context(mobile_browser, "iPhone_12_Pro")
    yield context
    context.close()


@pytest.fixture
def mobile_page(mobile_context: BrowserContext) -> Page:
    """Mobile page instance for testing"""
    page = mobile_context.new_page()
    yield page


@pytest.fixture
def iphone_se_page(mobile_browser: Browser) -> Page:
    """iPhone SE page for smaller screen testing"""
    context = MobilePlaywrightConfig.create_mobile_context(mobile_browser, "iPhone_SE")
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def ipad_page(mobile_browser: Browser) -> Page:
    """iPad page for tablet testing"""
    context = MobilePlaywrightConfig.create_mobile_context(mobile_browser, "iPad_Pro")
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture
def android_page(mobile_browser: Browser) -> Page:
    """Android page for cross-platform testing"""
    context = MobilePlaywrightConfig.create_mobile_context(mobile_browser, "Android_Pixel_5")
    page = context.new_page()
    yield page
    context.close()


class MobileTestHelpers:
    """Helper methods for mobile testing"""

    @staticmethod
    def simulate_long_press(page: Page, selector: str, duration: float = 0.6):
        """Simulate long press on mobile"""
        element = page.locator(selector)
        element.hover()
        page.mouse.down()
        page.wait_for_timeout(int(duration * 1000))
        page.mouse.up()

    @staticmethod
    def simulate_text_selection(page: Page, selector: str, start: int = 0, end: int = 50):
        """Simulate text selection on mobile"""
        page.evaluate(
            """
            (selector, start, end) => {
                const element = document.querySelector(selector);
                if (element) {
                    const textNode = element.childNodes[0];
                    if (textNode && textNode.textContent) {
                        const range = document.createRange();
                        range.setStart(textNode, start);
                        range.setEnd(textNode, Math.min(end, textNode.textContent.length));

                        const selection = window.getSelection();
                        selection.removeAllRanges();
                        selection.addRange(range);

                        // Trigger selection change event
                        const event = new Event('selectionchange');
                        document.dispatchEvent(event);
                    }
                }
            }
        """,
            selector,
            start,
            end,
        )

    @staticmethod
    def simulate_touch_events(page: Page, selector: str):
        """Simulate touch events on mobile"""
        page.evaluate(
            """
            (selector) => {
                const element = document.querySelector(selector);
                if (element) {
                    // Simulate touchstart
                    const touchStartEvent = new TouchEvent('touchstart', {
                        touches: [new Touch({
                            identifier: 1,
                            target: element,
                            clientX: 100,
                            clientY: 100
                        })]
                    });
                    element.dispatchEvent(touchStartEvent);

                    // Simulate touchend after delay
                    setTimeout(() => {
                        const touchEndEvent = new TouchEvent('touchend', {
                            changedTouches: [new Touch({
                                identifier: 1,
                                target: element,
                                clientX: 100,
                                clientY: 100
                            })]
                        });
                        element.dispatchEvent(touchEndEvent);
                    }, 100);
                }
            }
        """,
            selector,
        )

    @staticmethod
    def simulate_orientation_change(page: Page):
        """Simulate device orientation change"""
        page.evaluate("""
            () => {
                const event = new Event('orientationchange');
                window.dispatchEvent(event);
            }
        """)

    @staticmethod
    def check_mobile_detection(page: Page) -> bool:
        """Check if mobile device is properly detected"""
        return page.evaluate("""
            () => {
                return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
                       ('ontouchstart' in window) ||
                       (navigator.maxTouchPoints > 0);
            }
        """)

    @staticmethod
    def wait_for_annotation_menu(page: Page, timeout: int = 2000):
        """Wait for annotation menu to appear"""
        try:
            page.wait_for_selector(".annotation-menu", timeout=timeout)
            return True
        except Exception:
            return False

    @staticmethod
    def wait_for_mobile_instructions(page: Page, timeout: int = 5000):
        """Wait for mobile instructions to appear"""
        try:
            page.wait_for_selector("#mobile-annotation-instructions", timeout=timeout)
            return True
        except Exception:
            return False


# Export helpers for use in tests
@pytest.fixture
def mobile_helpers():
    """Mobile test helpers fixture"""
    return MobileTestHelpers
