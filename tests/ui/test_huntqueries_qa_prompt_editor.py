"""UI tests for HuntQueries QA prompt editor."""

import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
class TestHuntQueriesQAPromptEditor:
    """Verify HuntQueries QA prompt editor renders when enabled."""

    def test_huntqueries_qa_prompt_editor_visible(self, page: Page) -> None:
        """Ensure HuntQueries QA prompt editor appears after toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("domcontentloaded")

        page.locator("#tab-config").click()
        page.wait_for_timeout(500)

        # Expand Extract Agent panel
        page.locator('[data-collapsible-panel="extract-agent-panel"]').click()
        page.wait_for_timeout(300)

        # Expand HuntQueriesExtract sub-agent panel
        page.locator('[data-collapsible-panel="huntqueriesextract-agent-panel"]').click()
        page.wait_for_timeout(300)

        # Ensure sub-agent is enabled so QA toggle is active
        subagent_toggle = page.locator("#toggle-huntqueriesextract-enabled")
        if not subagent_toggle.is_checked():
            page.locator("label:has(#toggle-huntqueriesextract-enabled)").click()
            page.wait_for_timeout(300)

        # Toggle QA via label wrapper to avoid hidden input click issues
        qa_toggle = page.locator("#qa-huntqueriesextract")
        if not qa_toggle.is_checked():
            page.locator("label:has(#qa-huntqueriesextract)").click()
            page.wait_for_timeout(500)

        qa_container = page.locator("#huntqueriesextract-agent-qa-prompt-container")
        expect(qa_container).to_be_visible()
        expect(qa_container).to_contain_text("HuntQueriesQA QA Prompt")
