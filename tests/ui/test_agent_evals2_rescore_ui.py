"""Playwright coverage for the Evals2 "Rescore Completed" flow and score-state UI.

Verifies the browser-visible pieces of the item-scoring restore:
  * the "Rescore Completed" control and the legend that distinguishes an
    unscored (has ground truth) row from a count-only (no ground truth) row;
  * the dry-run-first workflow -- clicking Rescore first asks the endpoint what
    *would* change (apply=false), shows a confirmation, and only issues the
    writing call (apply=true) after the operator confirms.

The rescore endpoint is mocked so the test is deterministic and never mutates
evaluation data or calls a provider.
"""

import json

import pytest
from playwright.sync_api import Page, expect

EVALS2_URL = "http://127.0.0.1:8001/mlops/agent-evals2"


def _mock_rescore_api(page: Page) -> None:
    """Mock the rescore endpoint: apply=false is the dry-run, apply=true writes."""

    def handle(route):
        url = route.request.url
        if "apply=true" in url:
            payload = {
                "success": True,
                "subagent": "cmdline",
                "apply": True,
                "dry_run": False,
                "candidates": 6,
                "scorable": 5,
                "unrepairable_no_output": 1,
                "updated": 5,
                "per_agent": {"cmdline": {"candidates": 6, "scorable": 5, "unrepairable_no_output": 1, "updated": 5}},
                "message": "Updated 5 record(s)",
            }
        else:
            payload = {
                "success": True,
                "subagent": "cmdline",
                "apply": False,
                "dry_run": True,
                "candidates": 6,
                "scorable": 5,
                "unrepairable_no_output": 1,
                "updated": 0,
                "per_agent": {"cmdline": {"candidates": 6, "scorable": 5, "unrepairable_no_output": 1, "updated": 0}},
                "message": "5 record(s) would be updated (1 lack retained output)",
            }
        route.fulfill(status=200, body=json.dumps(payload), headers={"Content-Type": "application/json"})

    page.route("**/api/evaluations/subagent-eval-rescore**", handle)


@pytest.mark.ui
def test_rescore_button_and_score_state_legend_present(page: Page):
    """The Rescore control is present and the legend documents both states."""
    page.goto(EVALS2_URL)
    page.wait_for_load_state("load")

    expect(page.locator("#rescoreEvalBtn")).to_be_visible()

    legend = page.locator("#resultsLegend")
    # Both score-state badges must be documented so operators can tell the
    # repairable "unscored" case from the legitimate "count only" case.
    expect(legend).to_contain_text("unscored")
    expect(legend).to_contain_text("count only")
    expect(legend).to_contain_text("Latest (all runs)")


@pytest.mark.ui
def test_rescore_is_dry_run_first_and_applies_only_after_confirm(page: Page):
    """Clicking Rescore runs a dry-run, then writes only after confirmation."""
    _mock_rescore_api(page)
    page.goto(EVALS2_URL)
    page.wait_for_load_state("load")

    # The dry-run fires on click (apply=false), and the confirm dialog appears.
    with page.expect_response(lambda r: "subagent-eval-rescore" in r.url and "apply=false" in r.url):
        page.click("#rescoreEvalBtn")

    confirm_btn = page.locator(".confirm-btn")
    expect(confirm_btn).to_be_visible(timeout=5000)
    # The dialog surfaces the dry-run result (scorable count) before any write.
    modal = page.locator("[id^='_confirm_']")
    expect(modal).to_contain_text("5")
    expect(modal).to_contain_text("Rescore")

    # Confirming issues the writing call (apply=true).
    with page.expect_response(lambda r: "subagent-eval-rescore" in r.url and "apply=true" in r.url):
        confirm_btn.click()

    expect(page.locator("#resultsTable")).to_contain_text("Updated 5 record(s)")


@pytest.mark.ui
def test_rescore_cancel_does_not_write(page: Page):
    """Cancelling the confirmation must not issue an apply=true call."""
    _mock_rescore_api(page)
    page.goto(EVALS2_URL)
    page.wait_for_load_state("load")

    applied = {"called": False}
    page.on(
        "request",
        lambda req: (
            applied.__setitem__("called", True)
            if ("subagent-eval-rescore" in req.url and "apply=true" in req.url)
            else None
        ),
    )

    with page.expect_response(lambda r: "subagent-eval-rescore" in r.url and "apply=false" in r.url):
        page.click("#rescoreEvalBtn")

    cancel_btn = page.locator(".cancel-btn")
    expect(cancel_btn).to_be_visible(timeout=5000)
    cancel_btn.click()

    expect(page.locator("#resultsTable")).to_contain_text("cancelled")
    assert applied["called"] is False, "Cancel must not trigger an apply=true write"
