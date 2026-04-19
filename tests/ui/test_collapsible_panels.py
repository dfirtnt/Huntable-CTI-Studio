"""Tests for collapsible panel behavior on Settings page."""

import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.settings
class TestCollapsiblePanels:
    """Test settings page collapsible panel toggle behavior."""

    def test_settings_backup_panel_toggles(self, page: Page):
        """Test Settings Backup collapsible uses data-collapsible-panel and toggles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")
        header = page.locator('[data-collapsible-panel="backupConfig"]').first
        content = page.locator("#backupConfig-content").first
        header.scroll_into_view_if_needed()
        expect(header).to_be_visible(timeout=10000)
        expect(content).to_be_attached()
        initial_hidden = content.evaluate("el => el.classList.contains('hidden')")
        header.click()
        page.wait_for_timeout(200)
        after_hidden = content.evaluate("el => el.classList.contains('hidden')")
        assert initial_hidden != after_hidden

    def test_settings_agentic_workflow_panel_toggles(self, page: Page):
        """Test Settings Agentic Workflow collapsible toggles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")
        header = page.locator('[data-collapsible-panel="agenticWorkflowConfig"]').first
        content = page.locator("#agenticWorkflowConfig-content").first
        header.scroll_into_view_if_needed()
        expect(header).to_be_visible(timeout=10000)
        expect(content).to_be_attached()
        initial_hidden = content.evaluate("el => el.classList.contains('hidden')")
        header.click()
        page.wait_for_timeout(200)
        after_hidden = content.evaluate("el => el.classList.contains('hidden')")
        assert initial_hidden != after_hidden

    def test_settings_github_pr_panel_toggles(self, page: Page):
        """Test Settings GitHub PR collapsible toggles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")
        header = page.locator('[data-collapsible-panel="githubPRConfig"]').first
        content = page.locator("#githubPRConfig-content").first
        header.scroll_into_view_if_needed()
        expect(header).to_be_visible(timeout=10000)
        expect(content).to_be_attached()
        initial_hidden = content.evaluate("el => el.classList.contains('hidden')")
        header.click()
        page.wait_for_timeout(200)
        after_hidden = content.evaluate("el => el.classList.contains('hidden')")
        assert initial_hidden != after_hidden
