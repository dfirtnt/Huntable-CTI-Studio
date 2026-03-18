"""UI: SIGMA queue table fits viewport; Article/Rule Title truncate; Actions visible."""

import json
import os
import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_queue_table_no_horizontal_overflow_actions_visible(page: Page):
    """Long article + rule titles must not push Actions off-screen at ~1280px width."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    page.set_viewport_size({"width": 1280, "height": 800})

    long_article = ("Handala Hack " * 8) + "Unveiling Group Modus Operandi Extended Title Text"
    long_rule = ("WMIC Command Execution " * 6) + "For File Copy And Shadow Volume Detection"

    mock_queue = [
        {
            "id": 90001,
            "article_id": 1,
            "article_title": long_article,
            "workflow_execution_id": None,
            "rule_yaml": "title: Test\ndetection:\n  condition: true\n",
            "rule_metadata": {"title": long_rule},
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
                body=json.dumps(
                    {"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}
                ),
            )
        else:
            route.continue_()

    page.route("**/api/sigma-queue/list*", handle_route)
    page.goto(f"{base_url}/workflow")
    page.wait_for_load_state("networkidle")
    page.locator("#tab-queue").click()
    page.wait_for_timeout(800)

    tbody = page.locator("#queueTableBody")
    expect(tbody.locator("tr")).to_have_count(1)
    expect(tbody).to_contain_text("90001")

    scroll_wrap = page.locator("#tab-content-queue .overflow-x-auto").first
    expect(scroll_wrap).to_be_visible()
    overflow_ok = scroll_wrap.evaluate(
        """(el) => el.scrollWidth <= el.clientWidth + 4"""
    )
    assert overflow_ok, "queue table should not require horizontal scroll at 1280px"

    article_link = tbody.locator("tr").first.locator("td").nth(1).locator("a")
    expect(article_link).to_have_class(re.compile(r"truncate"))
    title_attr = article_link.get_attribute("title") or ""
    assert long_article[:20] in title_attr or len(title_attr) >= len(long_article) - 5

    rule_cell = tbody.locator("tr").first.locator("td").nth(2).locator("span")
    expect(rule_cell).to_have_class(re.compile(r"truncate"))

    reject_btn = tbody.locator('button:has-text("Reject")').first
    expect(reject_btn).to_be_visible()
    box = reject_btn.bounding_box()
    assert box is not None
    vp = page.viewport_size
    assert box["x"] + box["width"] <= (vp or {}).get("width", 1280) + 2, "Reject should sit in viewport"
