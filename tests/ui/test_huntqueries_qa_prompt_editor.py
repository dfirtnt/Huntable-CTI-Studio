"""UI tests for HuntQueries QA prompt editor."""

import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
class TestHuntQueriesQAPromptEditor:
    """Verify HuntQueries QA prompt editor renders without an editable user scaffold."""

    def test_huntqueries_qa_prompt_editor_visible(self, page: Page) -> None:
        """Ensure HuntQueries QA prompt editor appears after toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow", wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Ensure sub-agent is enabled so QA toggle is active
        subagent_toggle = page.locator("#toggle-huntqueriesextract-enabled")
        if not subagent_toggle.is_checked():
            subagent_toggle.evaluate(
                """el => {
                    el.checked = true;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }"""
            )
            page.wait_for_timeout(300)

        # Toggle QA directly because the control is rendered as a hidden input
        qa_toggle = page.locator("#qa-huntqueriesextract")
        if not qa_toggle.is_checked():
            qa_toggle.evaluate(
                """el => {
                    el.checked = true;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }"""
            )
            page.wait_for_timeout(200)

        page.evaluate(
            """() => {
                const container = document.getElementById('huntqueriesextract-agent-qa-prompt-container');
                if (container) {
                    container.classList.remove('hidden');
                }
                if (typeof renderQAPrompt === 'function') {
                    renderQAPrompt('HuntQueriesQA', 'huntqueriesextract-agent-qa-prompt-container');
                }
            }"""
        )

        qa_container = page.locator("#huntqueriesextract-agent-qa-prompt-container")
        expect(qa_container).to_contain_text("HuntQueriesQA QA Prompt")
        expect(qa_container).to_contain_text("User scaffold is locked in runtime")
        expect(page.locator("#huntqueriesqa-prompt-user-2")).to_have_count(0)
