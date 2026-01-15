"""Template for Playwright E2E tests.

Playwright tests:
- Full analyst workflows
- UI behavior testing
- Cross-component integration

These tests require:
- Web server running on port 8002 (test environment)
- APP_ENV=test
- Test containers running (make test-up)
"""

import pytest
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_workflow_example(page: Page):
    """Example Playwright E2E test."""
    # Navigate to page
    page.goto("http://localhost:8002/articles")
    
    # Interact with UI
    # ... test logic ...
    
    # Assert results
    expect(page.locator("h1")).to_contain_text("Articles")
