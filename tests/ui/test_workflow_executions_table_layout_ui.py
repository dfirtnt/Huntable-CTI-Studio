"""UI: Executions table fits viewport; Article truncates; View/Trace (and Retry) visible."""

import json
import os
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_executions_table_no_horizontal_overflow_actions_visible(page: Page):
    """Long article titles must not push Actions off-screen at ~1280px width."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    page.set_viewport_size({"width": 1280, "height": 800})

    long_article = ("Vidar Stealer " * 10) + "Version Two Point Zero Campaign Analysis Report Title"

    mock_payload = {
        "executions": [
            {
                "id": 88001,
                "article_id": 101,
                "article_title": long_article,
                "status": "completed",
                "current_step": "promote_to_queue",
                "ranking_score": None,
                "created_at": "2025-03-01T10:00:00",
            },
            {
                "id": 88002,
                "article_id": 102,
                "article_title": "Short",
                "status": "failed",
                "current_step": "generate_sigma",
                "ranking_score": 8.2,
                "created_at": "2025-03-02T11:00:00",
            },
        ],
        "total": 2,
        "total_pages": 1,
        "running": 0,
        "completed": 1,
        "failed": 1,
    }

    def handle_route(route):
        u = urlparse(route.request.url)
        if u.path == "/api/workflow/executions":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(mock_payload),
            )
        else:
            route.continue_()

    page.route("**/api/workflow/executions*", handle_route)
    page.goto(f"{base_url}/workflow")
    page.wait_for_load_state("load")
    page.locator("#tab-executions").click()
    page.wait_for_timeout(1200)

    tbody = page.locator("#executionsTableBody")
    expect(tbody.locator("tr")).to_have_count(2)

    scroll_wrap = page.locator("#tab-content-executions .q-table-wrap").first
    expect(scroll_wrap).to_be_visible()
    overflow_ok = scroll_wrap.evaluate("(el) => el.scrollWidth <= el.clientWidth + 4")
    assert overflow_ok, "executions table should not require horizontal scroll at 1280px"

    first_article_td = tbody.locator("tr").first.locator("td.q-cell-article")
    first_article = first_article_td.locator("a")
    expect(first_article).to_be_visible()

    # Truncation is implemented via CSS (max-width + overflow hidden + ellipsis),
    # not a literal `truncate` class.
    overflow = first_article_td.evaluate("(el) => getComputedStyle(el).overflow")
    text_overflow = first_article_td.evaluate("(el) => getComputedStyle(el).textOverflow")
    assert overflow in ("hidden", "clip"), f"expected overflow hidden/clip, got {overflow}"
    assert text_overflow == "ellipsis", f"expected text-overflow ellipsis, got {text_overflow}"

    trace_first = tbody.locator("tr").first.locator('button:has-text("Trace")').first
    expect(trace_first).to_be_visible()
    box = trace_first.bounding_box()
    vp = page.viewport_size
    assert box and box["x"] + box["width"] <= (vp or {}).get("width", 1280) + 2

    retry_btn = tbody.locator("tr").nth(1).locator('button:has-text("Retry")').first
    expect(retry_btn).to_be_visible()


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_executions_table_header_alignment(page: Page):
    """Header th x-positions must align with first-row td x-positions."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    page.set_viewport_size({"width": 1280, "height": 800})

    mock_payload = {
        "executions": [
            {
                "id": 88001,
                "article_id": 101,
                "article_title": ("Vidar Stealer " * 10) + "Version Two Point Zero",
                "status": "completed",
                "current_step": "promote_to_queue",
                "ranking_score": None,
                "created_at": "2025-03-01T10:00:00",
            },
            {
                "id": 88002,
                "article_id": 102,
                "article_title": "Short",
                "status": "failed",
                "current_step": "generate_sigma",
                "ranking_score": 8.2,
                "created_at": "2025-03-02T11:00:00",
            },
        ],
        "total": 2,
        "total_pages": 1,
        "running": 0,
        "completed": 1,
        "failed": 1,
    }

    def handle_route(route):
        u = urlparse(route.request.url)
        if u.path == "/api/workflow/executions":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(mock_payload),
            )
        else:
            route.continue_()

    page.route("**/api/workflow/executions*", handle_route)
    page.goto(f"{base_url}/workflow")
    page.wait_for_load_state("load")
    page.locator("#tab-executions").click()
    page.wait_for_timeout(1200)

    tbody = page.locator("#executionsTableBody")
    expect(tbody.locator("tr")).to_have_count(2)

    header_ths = page.locator("#executionsHeaderRow th")
    body_tds_first_row = tbody.locator("tr").first.locator("td")

    header_count = header_ths.count()
    body_count = body_tds_first_row.count()
    assert header_count == body_count, f"header_count={header_count} body_count={body_count}"

    # Tolerance: sub-pixel rounding + font rendering can shift by 1-3px.
    # If headers are actually mapped to different columns, diffs become much larger.
    tolerance_px = 4
    scroll_wrap = page.locator("#tab-content-executions .q-table-wrap").first
    scroll_left = scroll_wrap.evaluate("(el) => el.scrollLeft")
    header_labels = [header_ths.nth(i).inner_text().strip() for i in range(header_count)]
    body_td_texts = [body_tds_first_row.nth(i).inner_text().strip() for i in range(body_count)]
    for i in range(header_count):
        th_box = header_ths.nth(i).bounding_box()
        td_box = body_tds_first_row.nth(i).bounding_box()
        assert th_box and td_box, f"missing box for column index {i}"

        dx = abs(th_box["x"] - td_box["x"])
        assert dx <= tolerance_px, (
            f"col[{i}] x mismatch: th_x={th_box['x']} td_x={td_box['x']} dx={dx}; "
            f"th='{header_labels[i]}' td='{body_td_texts[i]}'; "
            f"q-table-wrap.scrollLeft={scroll_left}"
        )
