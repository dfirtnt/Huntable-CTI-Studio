"""Regression: workflow Enrich modal must use rule YAML, not an observable <code>."""

import json
import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_enrich_modal_original_rule_uses_yaml_not_observable_code(page: Page):
    """
    The workflow rule preview includes many <code> elements (notably under Observables Used).
    The Enrich modal's "Original Rule" must be populated from the YAML block, not the first <code>.
    """

    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    exec_id = 88801

    mock_queue = [
        {
            "id": 99902,
            "article_id": 1,
            "article_title": "Test Article",
            "workflow_execution_id": exec_id,
            "rule_yaml": (
                "title: Test Rule\nlogsource:\n  category: process_creation\n"
                "detection:\n  selection:\n    CommandLine|contains: net.exe\n  condition: selection\n"
            ),
            "rule_metadata": {"title": "Test Rule", "description": "Test", "observables_used": [0, 1]},
            "similarity_scores": [],
            "max_similarity": 0.0,
            "status": "pending",
            "reviewed_by": None,
            "review_notes": None,
            "pr_submitted": False,
            "pr_url": None,
            "created_at": "2025-02-02T12:00:00",
            "reviewed_at": None,
        }
    ]

    mock_observables = {
        "execution_id": exec_id,
        "observables": {
            "cmdline": [
                {"observable_value": "cmd0", "confidence_score": 0.9},
                {"observable_value": "cmd1", "confidence_score": 0.85},
                {"observable_value": "cmd2", "confidence_score": 0.8},
            ],
            "process_lineage": [],
            "hunt_queries": [],
        },
    }

    def handle_route(route):
        if "/api/sigma-queue/list" in route.request.url:
            payload = {"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
        elif f"/api/workflow/executions/{exec_id}/observables" in route.request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(mock_observables))
        else:
            route.continue_()

    page.route("**/api/sigma-queue/list*", handle_route)
    page.route(f"**/api/workflow/executions/{exec_id}/observables*", handle_route)

    page.goto(f"{base_url}/workflow")
    page.wait_for_load_state("load")
    page.locator("#tab-queue").click()
    page.wait_for_timeout(1000)

    page.locator('button:has-text("Preview")').first.click()
    rule_modal = page.locator("#ruleModal")
    expect(rule_modal).to_be_visible(timeout=5000)

    # Sanity: observables are present and include <code> entries like cmd0/cmd1.
    expect(rule_modal).to_contain_text("cmd0")
    expect(rule_modal).to_contain_text("cmd1")

    # Open enrich modal
    rule_modal.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first.click()

    enrich_modal = page.locator("#enrichModal")
    expect(enrich_modal).to_be_visible(timeout=5000)

    original_textarea = page.locator("#enrichOriginalRule")
    expect(original_textarea).to_be_visible(timeout=3000)
    original_yaml = original_textarea.input_value()

    assert "title: Test Rule" in original_yaml
    assert "detection:" in original_yaml
    assert "cmd0" not in original_yaml
