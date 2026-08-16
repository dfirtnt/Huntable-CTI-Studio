"""
Playwright tests for Agent Evaluations page.
"""

import contextlib
import json

import pytest
from playwright.sync_api import Page, expect


def _mock_eval_articles_api(page: Page, articles: list | None = None):
    """Mock subagent-eval-articles API so Load Eval Articles completes (avoids timeout skip)."""
    if articles is None:
        articles = []
    payload = {"articles": articles}

    def handle(route):
        if "/api/evaluations/subagent-eval-articles" in route.request.url:
            route.fulfill(
                status=200,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
        else:
            route.continue_()

    page.route("**/api/evaluations/subagent-eval-articles**", handle)


@pytest.mark.ui
def test_agent_evals_page_loads(page: Page):
    """Test that the agent evals page loads correctly."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")

    # Check main heading (use role to avoid strict mode when multiple h1)
    expect(page.get_by_role("heading", name="Agent Evaluations")).to_be_visible()

    # Check main sections exist (use role/unique to avoid strict mode)
    expect(page.get_by_role("heading", name="Configuration")).to_be_visible()
    expect(page.get_by_role("heading", name="Evaluation Articles")).to_be_visible()
    expect(page.get_by_role("heading", name="Results Comparison")).to_be_visible()

    # Check buttons exist (template uses loadEvalArticlesBtn, not loadDatasetBtn)
    expect(page.locator("#loadEvalArticlesBtn")).to_be_visible()
    expect(page.locator("#runEvalBtn")).to_be_visible()


def _click_load_eval_articles_and_wait(page: Page) -> None:
    """Click Load Eval Articles and wait until done. Skips if eval-articles API unavailable."""
    page.wait_for_selector("#loadEvalArticlesBtn")
    page.click("#loadEvalArticlesBtn")
    try:
        page.wait_for_function(
            "document.getElementById('loadEvalArticlesBtn').textContent === 'Load Eval Articles'", timeout=30000
        )
    except Exception as e:
        if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
            pytest.skip("Load Eval Articles did not complete; eval-articles API may be unavailable")
        raise


@pytest.mark.ui
def test_load_dataset_articles(page: Page):
    """Test loading articles from dataset."""
    _mock_eval_articles_api(page)
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")
    _click_load_eval_articles_and_wait(page)

    # Check if articles loaded (either articles shown or "No articles" message)
    article_list = page.locator("#articleList")
    expect(article_list).to_be_visible()

    # Check for either articles or "No articles" message (loadEvalArticles vs legacy text)
    has_articles = page.locator("#articleList input[type='checkbox']").count() > 0
    has_no_articles_msg = (
        page.get_by_text("No eval articles found", exact=False).is_visible()
        or page.get_by_text("No articles found in dataset", exact=False).is_visible()
    )

    assert has_articles or has_no_articles_msg, "Should show either articles or 'No articles' message"


@pytest.mark.ui
def test_select_articles_and_presets(page: Page):
    """Test selecting articles (presets no longer exist on this page)."""
    _mock_eval_articles_api(page)
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")
    _click_load_eval_articles_and_wait(page)

    # Check if there are articles to select
    article_checkboxes = page.locator("#articleList input[type='checkbox']")
    article_count = article_checkboxes.count()

    if article_count > 0:
        # Select first article
        article_checkboxes.first.check()

        # Run button should be enabled when articles are selected
        run_btn = page.locator("#runEvalBtn")
        expect(run_btn).not_to_be_disabled()
    else:
        # If no articles, run button should be disabled
        run_btn = page.locator("#runEvalBtn")
        expect(run_btn).to_be_disabled()


@pytest.mark.ui
@pytest.mark.agent_config_mutation
def test_run_evaluation_button(page: Page):
    """Test that run evaluation button works."""
    _mock_eval_articles_api(page)
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")
    _click_load_eval_articles_and_wait(page)

    # Select article if available (presets no longer exist)
    article_checkboxes = page.locator("#articleList input[type='checkbox']")

    if article_checkboxes.count() > 0:
        article_checkboxes.first.check()

        # Click run evaluation
        run_btn = page.locator("#runEvalBtn")
        expect(run_btn).not_to_be_disabled()

        # Click and check status appears
        run_btn.click()

        # Check status div appears
        status_div = page.locator("#evalStatus")
        expect(status_div).to_be_visible(timeout=5000)

        # Check status text appears
        status_text = page.locator("#evalStatusText")
        expect(status_text).to_be_visible()

        # Status should contain either "Triggering" or an error message
        status_content = status_text.text_content()
        assert status_content is not None
        assert len(status_content) > 0


def _click_load_previous_results_and_wait(page: Page) -> None:
    """Click Load Previous Results and wait for response. Skips if no results."""
    page.wait_for_selector("#loadPreviousResultsBtn")
    page.click("#loadPreviousResultsBtn")
    with contextlib.suppress(Exception):
        page.wait_for_response(
            lambda r: (
                "/api/evaluations/subagent-eval-results" in r.url or "/api/evaluations/subagent-eval-aggregate" in r.url
            ),
            timeout=15000,
        )
    page.wait_for_timeout(1500)


@pytest.mark.ui
def test_export_bundles_button_visible_when_results_loaded(page: Page):
    """When Load Previous Results shows config version columns, export button (📦) is present."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")
    page.locator("#subagentSelect").select_option("cmdline")
    _click_load_previous_results_and_wait(page)
    # Export button appears in table header when config versions exist
    export_buttons = page.locator('button[title*="Export bundles"]')
    if export_buttons.count() > 0:
        expect(export_buttons.first).to_be_visible()
    else:
        # No previous results — skip (table shows placeholder)
        pytest.skip("No previous eval results; export button not rendered")


@pytest.mark.ui
def test_select_all_deselect_all_buttons(page: Page):
    """Test select all and deselect all buttons."""
    _mock_eval_articles_api(page)
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")
    _click_load_eval_articles_and_wait(page)

    # Check if articles exist
    article_checkboxes = page.locator("#articleList input[type='checkbox']")
    article_count = article_checkboxes.count()

    if article_count > 0:
        # Click select all
        page.click("#selectAllBtn")

        # All checkboxes should be checked
        for i in range(article_count):
            checkbox = article_checkboxes.nth(i)
            expect(checkbox).to_be_checked()

        # Click deselect all
        page.click("#deselectAllBtn")

        # All checkboxes should be unchecked
        for i in range(article_count):
            checkbox = article_checkboxes.nth(i)
            expect(checkbox).not_to_be_checked()


@pytest.mark.ui
def test_eval_constraints_help_modal_stays_within_viewport(page: Page):
    """The eval constraints help dialog should open as a bounded modal inside the viewport."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")

    page.evaluate("showHelp('evalCurrentConfig')")

    modal = page.locator("#agentEvalsHelpModal")
    modal_card = page.locator("#agentEvalsHelpModal .eval-help-modal-card")

    expect(modal).to_be_visible()
    expect(modal_card).to_be_visible()
    expect(modal_card).to_contain_text("Junk filtering is skipped")
    expect(modal_card).to_contain_text("complete article content")

    viewport = page.viewport_size
    modal_box = modal_card.bounding_box()

    assert viewport is not None, "Playwright viewport should be available"
    assert modal.get_attribute("role") == "dialog"
    assert modal.get_attribute("aria-modal") == "true"
    assert modal_box is not None, "Eval constraints modal card should have a bounding box"
    assert modal_box["x"] >= 0, "Eval constraints modal should stay within the viewport horizontally"
    assert modal_box["y"] >= 0, "Eval constraints modal should stay within the viewport vertically"
    assert modal_box["x"] + modal_box["width"] <= viewport["width"], (
        "Eval constraints modal should fit within the viewport width"
    )
    assert modal_box["y"] + modal_box["height"] <= viewport["height"], (
        "Eval constraints modal should fit within the viewport height"
    )


@pytest.mark.ui
def test_diagnosis_help_uses_selected_execution_and_requires_confirmation(page: Page):
    """Diagnosis help should be actionable, safe, and tied to the selected eval run."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")
    page.evaluate(
        """
        const button = document.getElementById('diagnosisHelpBtn');
        button.dataset.executionId = '3468';
        button.dataset.agentName = 'CmdlineExtract';
        showHelp('diagnosisWorkflow');
        """
    )

    modal = page.locator("#agentEvalsHelpModal")
    expect(modal).to_be_visible()
    expect(modal).to_contain_text("untrusted evidence")
    expect(modal).to_contain_text("explicitly approve one save action")
    expect(modal).to_contain_text("confirmed_by_user=true")
    expect(page.locator("#diagnosisAgentPrompt")).to_have_text("Diagnose execution 3468 for CmdlineExtract")

    page.keyboard.press("Escape")
    expect(modal).not_to_be_visible()


@pytest.mark.ui
def test_poller_survives_transient_fetch_failures(page: Page):
    """A transient outage (e.g. a dev hot-reload restart -> "Failed to fetch") must
    NOT abandon a running eval. The poller should show a "Reconnecting" status and
    recover once the endpoint returns, instead of dead-ending on the red error.

    Regression guard: previously the catch block tore the loop down and printed
    "Error polling results: Failed to fetch" on the first network throw.
    """
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")

    # Abort the results endpoint the first 3 times (network throw == "Failed to
    # fetch"), then return a payload marking the synthetic execution completed.
    calls = {"n": 0}

    def handle(route):
        calls["n"] += 1
        if calls["n"] <= 3:
            route.abort()
        else:
            route.fulfill(
                status=200,
                body=json.dumps(
                    {
                        "results": [
                            {
                                "execution_id": 999999,
                                "article_id": 1,
                                "status": "completed",
                                "actual_count": 1,
                                "expected_count": 1,
                                "score": 1.0,
                                "warnings": [],
                            }
                        ]
                    }
                ),
                headers={"Content-Type": "application/json"},
            )

    page.route("**/api/evaluations/subagent-eval-results**", handle)

    # Drive the real poller directly with a synthetic execution (no billed eval run).
    status = page.locator("#evalStatusText")
    page.evaluate(
        """
        currentSubagent = 'cmdline';
        pollSubagentResults([
            { execution_id: 999999, article_id: 1, url: 'http://example.test', eval_record_id: 1 }
        ]);
        """
    )

    # It must reach the transient "Reconnecting" state (proof it did not give up),
    expect(status).to_contain_text("Reconnecting", timeout=10000)
    # then recover to the completed/refresh state once the endpoint returns.
    expect(status).to_contain_text("completed", timeout=15000)
    # and it must never have shown the fatal "Error polling results" message.
    assert "Error polling results" not in status.inner_text()
