"""UI: workflow queue displays observables-used count per rule."""

import json
import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_queue_shows_observables_used_count_column(page: Page):
    """Queue table includes an Obs Used column populated from rule_metadata.observables_used."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    mock_queue = [
        {
            "id": 91001,
            "article_id": 1,
            "article_title": "Observable Count Test",
            "workflow_execution_id": 123,
            "rule_yaml": "title: Test\ndetection:\n  condition: true\n",
            "rule_metadata": {"title": "Count Test Rule", "observables_used": [0, 1, 1, 2]},
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

    def handle_route(route):
        if "/api/sigma-queue/list" in route.request.url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}),
            )
        else:
            route.continue_()

    page.route("**/api/sigma-queue/list*", handle_route)
    page.goto(f"{base_url}/workflow")
    page.wait_for_load_state("load")
    page.locator("#tab-queue").click()
    page.wait_for_timeout(800)

    expect(page.locator("#tab-content-queue th", has_text="Obs Used")).to_be_visible()
    row = page.locator("#queueTableBody tr").first
    expect(row.locator("td.q-cell-obs")).to_have_text("3")
