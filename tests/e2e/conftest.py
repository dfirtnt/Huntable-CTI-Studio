"""
Conftest for E2E tests - handles Playwright browser availability checks.

Note: E2E tests require Playwright browsers to be installed.
Run 'playwright install' in the Docker container before running E2E tests.
These tests are marked with @pytest.mark.e2e and will be excluded from normal test runs.
"""

# E2E tests require Playwright browsers - they will error if browsers aren't installed
# This is expected behavior. To run E2E tests:
# 1. Install Playwright browsers: `playwright install` (in Docker container)
# 2. Ensure web server is running on localhost:8001
# 3. Run with: `pytest -m e2e`
