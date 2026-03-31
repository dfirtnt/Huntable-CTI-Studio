import json
import os
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.workflow
def test_similar_rule_detail_shows_repo_origin_badge(page: Page):
    """Similar-rule detail modal must show SigmaHQ vs customer repo badge."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    execution_id = 88001

    similar_rule_title = "Repo-Origin Similar Rule"
    similar_rule_id = "cust-test-repo-rule-001"

    mock_executions_payload = {
        "executions": [
            {
                "id": execution_id,
                "article_id": 101,
                "article_title": "Test Article",
                "status": "completed",
                "current_step": "similarity_search",
                "ranking_score": None,
                "created_at": "2025-03-01T10:00:00",
            }
        ],
        "total": 1,
        "total_pages": 1,
        "running": 0,
        "completed": 1,
        "failed": 0,
        "pending": 0,
    }

    mock_execution_detail_payload = {
        "id": execution_id,
        "article_id": 101,
        "article_title": "Test Article",
        "status": "completed",
        "current_step": "similarity_search",
        "ranking_score": None,
        "config_snapshot": {"similarity_threshold": 0.5},
        "sigma_rules": [],
        "queued_rules_count": 0,
        "queued_rule_ids": [],
        "similarity_results": [
            {
                "rule_title": "Generated Rule 1",
                "max_similarity": 0.17,
                "similar_rules": [
                    {
                        "title": similar_rule_title,
                        "description": "desc",
                        "rule_id": similar_rule_id,
                        "file_path": "customer/windows/proc_creation.yml",
                        "status": "unknown",
                        "similarity": 0.17,
                        "tags": ["attack.execution"],
                        "logsource": {"product": "windows"},
                        "detection": {"selection": {"Image|contains": "wmic.exe"}},
                    }
                ],
            }
        ],
        "error_log": {},
    }

    def handle_route(route):
        u = urlparse(route.request.url)
        path = (u.path or "").rstrip("/")

        # Executions table list
        if path == "/api/workflow/executions":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(mock_executions_payload),
            )

        # Execution detail (match any execution id; frontend sometimes requests a different row id)
        elif path.startswith("/api/workflow/executions/") and not path.endswith("/observables"):
            parts = [p for p in path.split("/") if p]
            maybe_id = parts[-1] if parts else None
            try:
                requested_id = int(maybe_id) if maybe_id is not None else execution_id
            except ValueError:
                requested_id = execution_id

            payload = dict(mock_execution_detail_payload)
            payload["id"] = requested_id
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            )

        elif path == "/api/workflow/config":
            # viewExecution calls this but gracefully handles missing fields.
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"agent_models": {}}),
            )
        elif (
            path.endswith(f"/api/workflow/executions/{execution_id}/observables")
            or path == f"/api/workflow/executions/{execution_id}/observables"
        ):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"execution_id": execution_id, "observables": {}}),
            )
        else:
            route.continue_()

    page.route("**/api/workflow/executions*", handle_route)

    page.goto(f"{base_url}/workflow")
    page.wait_for_load_state("load")

    page_errors: list[str] = []
    console_msgs: list[str] = []

    def on_page_error(err):
        page_errors.append(str(err))

    def on_console(msg):
        # Store failures; useful if viewExecution throws before unhiding the modal.
        if msg.type in ("error", "warning"):
            console_msgs.append(f"{msg.type}: {msg.text}")

    page.on("pageerror", on_page_error)
    page.on("console", on_console)

    page.locator("#tab-executions").click()
    page.wait_for_timeout(200)

    tbody = page.locator("#executionsTableBody")
    expect(tbody).to_be_visible()

    view_btn = tbody.locator('button:has-text("View")').first
    expect(view_btn).to_be_visible()
    with page.expect_response(
        lambda resp: (
            resp.status == 200
            and (urlparse(resp.url).path or "").startswith("/api/workflow/executions/")
            and not (urlparse(resp.url).path or "").endswith("/observables")
        ),
        timeout=8000,
    ):
        view_btn.click()

    try:
        page.wait_for_function(
            "() => { const el = document.getElementById('executionModal'); return el && !el.classList.contains('hidden'); }",
            timeout=8000,
        )
    except Exception as e:
        raise AssertionError(
            f"executionModal did not open. page_errors={page_errors[:5]} console_msgs={console_msgs[:10]} err={e}"
        ) from e

    execution_modal = page.locator("#executionModal")
    expect(execution_modal).to_be_visible()

    # Click the similar rule card to open the "Similar Rule Details" modal.
    page.locator("#executionModal").locator(f"text={similar_rule_title}").first.click()

    similar_rule_modal = page.locator("#similarRuleModal")
    expect(similar_rule_modal).to_be_visible()
    expect(similar_rule_modal).to_contain_text("Your repo")
    expect(similar_rule_modal).not_to_contain_text("SigmaHQ")
