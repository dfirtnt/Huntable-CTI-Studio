"""Regression: periodic loadQueue + previewId must not exit YAML edit mode or wipe the textarea.

Covers `/workflow` queue tab + rule modal (`checkAndTriggerPreview` + `isEditMode` guard). The
standalone `/sigma-queue` page reuses the same `loadQueue`/preview pattern; UI bootstrap for
that page is not exercised here (list mock + Refresh timing differ from the workflow shell).
"""

import json
import os
import re

import pytest
from playwright.sync_api import Page, expect

_MARK = "\n# LGTEST_EDIT_SURVIVES_LOAD_QUEUE\n"

# Single pending rule; id must match previewId deep links.
_SIGMA_QUEUE_LIST_MOCK = [
    {
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
]


def _stub_sigma_queue_list(page: Page) -> None:
    def handle(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": _SIGMA_QUEUE_LIST_MOCK,
                    "total": len(_SIGMA_QUEUE_LIST_MOCK),
                    "limit": 50,
                    "offset": 0,
                }
            ),
        )

    page.route(re.compile(r".*sigma-queue/list.*"), handle)


def _trigger_load_queue(page: Page) -> None:
    """Reload the queue list. Prefer Refresh when the rule modal is not blocking clicks."""
    modal = page.locator("#ruleModal")
    obscures = modal.evaluate("el => el && !el.classList.contains('hidden')")
    if obscures:
        page.evaluate("async () => { await window.loadQueue(); }")
    else:
        page.locator('button[onclick="loadQueue()"]').first.click()
    page.wait_for_timeout(200)


def _ensure_rule_modal_open(page: Page) -> None:
    page.wait_for_selector("#queueTableBody", timeout=15000)
    _trigger_load_queue(page)
    preview_btn = page.locator('#queueTableBody button:has-text("Preview")').first
    expect(preview_btn).to_be_visible(timeout=20000)
    rule_modal = page.locator("#ruleModal")
    if rule_modal.evaluate("el => el.classList.contains('hidden')"):
        preview_btn.click()
    expect(rule_modal).not_to_have_class("hidden", timeout=15000)


def _enter_edit_and_append_marker(page: Page) -> None:
    _ensure_rule_modal_open(page)
    rule_modal = page.locator("#ruleModal")
    rule_modal.locator('button[onclick="enableEditMode()"]').click()
    # renderRulePreview schedules validate-dropdown init (~250ms); that can replace DOM under #yamlEditor.
    page.wait_for_timeout(900)
    editor = rule_modal.locator("#yamlEditor")
    expect(editor).to_be_visible(timeout=5000)
    merged = editor.evaluate(
        "(el) => { const m = " + json.dumps(_MARK) + "; el.value = (el.value || '') + m; return el.value; }",
    )
    assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in merged
    assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in editor.input_value()


def _await_load_queue_deferred_preview(page: Page) -> None:
    """loadQueue finishes, then checkAndTriggerPreview schedules previewRule in ~100ms."""
    _trigger_load_queue(page)
    page.wait_for_timeout(400)


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_queue_preview_edits_survive_load_queue(page: Page) -> None:
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    _stub_sigma_queue_list(page)
    # previewId + queue tab: same deep-link path as production; Preview also sets previewId when opened via button.
    page.goto(f"{base_url}/workflow?previewId=1#queue")
    page.wait_for_load_state("load")

    _enter_edit_and_append_marker(page)
    _await_load_queue_deferred_preview(page)

    editor = page.locator("#ruleModal #yamlEditor")
    expect(editor).to_be_visible(timeout=3000)
    assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in editor.input_value()
    save_btn = page.locator("#ruleModal").get_by_role("button", name="Save Changes")
    expect(save_btn).to_be_visible(timeout=2000)
