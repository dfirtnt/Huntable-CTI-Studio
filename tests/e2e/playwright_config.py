from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    """Run Playwright tests with configuration"""
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
        record_video_dir="test-results/videos/",
    )
    page = context.new_page()

    # Test basic functionality
    page.goto("http://localhost:8001")
    page.wait_for_load_state("networkidle")

    # Take screenshot
    page.screenshot(path="test-results/screenshot.png")

    context.close()
    browser.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
