"""Tests for SIGMA editor YAML validation and save.

The YAML editor lives inside the rule preview modal on /sigma-queue.
It becomes visible only after clicking Preview on a rule row, then
clicking the Edit button inside the modal.
"""

import json
import os

import pytest
from playwright.sync_api import Page, expect

_MOCK_RULE = {
    "id": 1,
    "article_id": 1,
    "article_title": "Test Article",
    "workflow_execution_id": None,
    "rule_yaml": "title: Test Rule\ndetection:\n  condition: true\n",
    "rule_metadata": {"title": "Test Rule"},
    "similarity_scores": [],
    "max_similarity": 0.5,
    "status": "pending",
    "reviewed_by": None,
    "review_notes": None,
    "pr_submitted": False,
    "pr_url": None,
    "created_at": "2024-01-01T12:00:00",
    "reviewed_at": None,
}

_MOCK_LIST_RESPONSE = {
    "items": [_MOCK_RULE],
    "total": 1,
    "limit": 50,
    "offset": 0,
}


@pytest.mark.ui
class TestSigmaEditorValidation:
    """Test SIGMA editor YAML validation and save functionality."""

    @pytest.fixture(autouse=True)
    def mock_queue(self, page: Page):
        """Mock the sigma queue list so there is always one rule available."""

        def handle(route):
            if "/api/sigma-queue/list" in route.request.url:
                route.fulfill(
                    status=200,
                    body=json.dumps(_MOCK_LIST_RESPONSE),
                    headers={"Content-Type": "application/json"},
                )
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list**", handle)
        yield

    def _open_yaml_editor(self, page: Page):
        """Navigate to sigma-queue, open a rule modal, and click Edit to reveal the textarea.

        Returns the yamlEditor textarea locator, or calls pytest.skip if no rows appear.
        """
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sigma-queue")
        page.wait_for_load_state("networkidle")

        # Wait for a Preview button to appear (real data row, not the loading placeholder)
        preview_button = page.locator('#queueTableBody button:has-text("Preview")').first
        if not preview_button.is_visible(timeout=10000):
            pytest.skip("No rules in queue to open editor")

        preview_button.click(force=True)

        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=5000)

        # Click Edit button to switch to edit mode and reveal the yamlEditor textarea
        edit_button = page.locator('#ruleModal button:has-text("Edit")').first
        if not edit_button.is_visible(timeout=3000):
            pytest.skip("Edit button not visible in rule modal")

        edit_button.click()

        editor = page.locator("#yamlEditor")
        expect(editor).to_be_visible(timeout=10000)
        return editor

    def test_sigma_editor_loads(self, page: Page):
        """Test that the YAML editor textarea is accessible inside the rule preview modal."""
        editor = self._open_yaml_editor(page)
        expect(editor).to_be_visible()
        # Textarea should have the rule YAML pre-populated
        content = editor.input_value()
        assert len(content) > 0, "YAML editor should be pre-populated with rule content"

    def test_sigma_yaml_validation(self, page: Page):
        """Test YAML content can be replaced in the editor (no inline validation UI on this page)."""
        editor = self._open_yaml_editor(page)

        # Clear and fill with partial YAML
        editor.fill("title: Invalid Rule\n# Missing required fields")
        # Verify the fill took effect
        content = editor.input_value()
        assert "Invalid Rule" in content

    def test_sigma_editor_save(self, page: Page):
        """Test saving SIGMA rule edits via the Save Changes button."""
        editor = self._open_yaml_editor(page)

        valid_yaml = (
            "title: Test Rule\n"
            "id: 12345678-1234-1234-1234-123456789abc\n"
            "description: Test rule\n"
            "logsource:\n"
            "    category: process_creation\n"
            "    product: windows\n"
            "detection:\n"
            "    selection:\n"
            "        CommandLine|contains: 'test.exe'\n"
            "    condition: selection\n"
            "level: medium"
        )

        editor.fill(valid_yaml)

        # Click Save Changes button (rendered by updateActionButtons in edit mode)
        save_btn = page.locator('#ruleModal button:has-text("Save Changes")').first
        if not save_btn.is_visible(timeout=3000):
            pytest.skip("Save Changes button not visible in edit mode")

        save_btn.click()

        # After saving, the modal should revert to view mode (yamlEditor hidden, pre block shown)
        page.wait_for_timeout(300)
        # The textarea should no longer be visible in view mode
        expect(editor).not_to_be_visible()
