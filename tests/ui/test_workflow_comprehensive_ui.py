"""
UI tests for Workflow page comprehensive functionality using Playwright.
Tests workflow configuration, executions, and queue management features.

Trimmed to regression-only tests. Config form, agent toggles, autosave,
collapsible panels, and modal behavior are covered by Playwright TS specs
(agent_config_*.spec.ts, collapsible_sections.spec.ts, workflow_*.spec.ts).
"""

import json
import os
import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

# Operator Console: steps use #sN + .section-header; Extract sub-agents use #sa-* + .sa-body
_SUBAGENT_TO_SA_BLOCK = {
    "cmdlineextract": "sa-cmdline",
    "proctreeextract": "sa-proctree",
    "huntqueriesextract": "sa-huntqueries",
}


def _open_operator_step(page: Page, step_id: str) -> None:
    section = page.locator(f"#{step_id}")
    if "open" not in (section.get_attribute("class") or ""):
        page.locator(f"#{step_id} .section-header").click()
        page.wait_for_timeout(300)


class TestWorkflowTabNavigation:
    """Test workflow tab navigation functionality."""

    @pytest.mark.ui
    @pytest.mark.ui_smoke
    @pytest.mark.workflow
    @pytest.mark.parametrize(
        "tab_id,content_id,hidden_ids",
        [
            ("tab-config", "tab-content-config", ["tab-content-executions", "tab-content-queue"]),
            ("tab-executions", "tab-content-executions", ["tab-content-config", "tab-content-queue"]),
            ("tab-queue", "tab-content-queue", ["tab-content-config", "tab-content-executions"]),
        ],
    )
    def test_tab_navigation(self, page: Page, tab_id: str, content_id: str, hidden_ids: list):
        """Test switching between workflow tabs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        tab = page.locator(f"#{tab_id}")
        expect(tab).to_be_visible()
        tab.click()
        page.wait_for_timeout(200)

        content = page.locator(f"#{content_id}")
        expect(content).to_be_visible()
        expect(content).not_to_have_class("hidden")

        for hid in hidden_ids:
            expect(page.locator(f"#{hid}")).to_have_class(re.compile(r"hidden"))


class TestWorkflowExecutionsTabStatistics:
    """Test execution statistics display."""

    @pytest.mark.ui
    @pytest.mark.workflow
    @pytest.mark.parametrize(
        "stat_id",
        [
            "totalExecutions",
            "runningExecutions",
            "completedExecutions",
            "failedExecutions",
        ],
    )
    def test_execution_stat_display(self, page: Page, stat_id: str):
        """Test execution statistics are visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(1000)

        stat = page.locator(f"#{stat_id}")
        expect(stat).to_be_visible()


# ---------------------------------------------------------------------------
# Consolidated regression tests (from single-file tests pruned in UI test diet)
# ---------------------------------------------------------------------------

_EDIT_MARKER = "\n# LGTEST_EDIT_SURVIVES_LOAD_QUEUE\n"

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


class TestWorkflowQueueRegressions:
    """Queue-tab regression tests (consolidated from single-file tests)."""

    @pytest.fixture(autouse=True)
    def close_modals_after_test(self, page: Page):
        """Close ruleModal/enrichModal after each test.

        The class-scoped page is reused across tests and goto is deduplicated
        (path-only comparison ignores ?query and #fragment), so modal state
        opened by one test persists into the next test's setup.
        """
        yield
        try:
            page.evaluate(
                "() => { ['ruleModal','enrichModal'].forEach(id => {"
                " const el = document.getElementById(id); if (el) el.classList.add('hidden'); }); }"
            )
        except Exception:
            pass

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_shows_observables_used_count_column(self, page: Page):
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
        expect(page.locator("#tab-content-queue th", has_text="Job ID")).to_be_visible()
        row = page.locator("#queueTableBody tr").first
        expect(row.locator("td.q-cell-obs")).to_have_text("3")
        expect(row.locator("td.q-cell-job")).to_contain_text("123")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_table_displays_naive_created_at_as_local_time(self, page: Page):
        """Timezone-less queue timestamps should render without a UTC offset shift."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        mock_queue = [
            {
                "id": 91002,
                "article_id": 1,
                "article_title": "Queue Local Time Check",
                "workflow_execution_id": 123,
                "rule_yaml": "title: Test\ndetection:\n  condition: true\n",
                "rule_metadata": {"title": "Local Time Rule"},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2026-04-24T11:16:00",
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
        page.goto(f"{base_url}/workflow#queue")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(800)

        created_cell = page.locator("#queueTableBody tr").first.locator("td.q-cell-date")
        expect(created_cell).to_contain_text("11:16 AM")
        expect(created_cell).not_to_contain_text("7:16 AM")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_table_no_horizontal_overflow_actions_visible(self, page: Page):
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
                    body=json.dumps({"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}),
                )
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(800)

        tbody = page.locator("#queueTableBody")
        expect(tbody.locator("tr")).to_have_count(1)
        expect(tbody).to_contain_text("90001")

        scroll_wrap = page.locator("#tab-content-queue .q-table-wrap").first
        expect(scroll_wrap).to_be_visible()
        overflow_ok = scroll_wrap.evaluate("""(el) => el.scrollWidth <= el.clientWidth + 4""")
        assert overflow_ok, "queue table should not require horizontal scroll at 1280px"

        article_td = tbody.locator("tr").first.locator("td.q-cell-article")
        article_link = article_td.locator("a").first
        expect(article_link).to_be_visible()
        overflow_a = article_td.evaluate("(el) => getComputedStyle(el).overflow")
        text_overflow_a = article_td.evaluate("(el) => getComputedStyle(el).textOverflow")
        assert overflow_a in ("hidden", "clip"), f"expected overflow hidden/clip on article cell, got {overflow_a}"
        assert text_overflow_a == "ellipsis", f"expected text-overflow ellipsis on article cell, got {text_overflow_a}"
        title_attr = article_link.get_attribute("title") or ""
        assert long_article[:20] in title_attr or len(title_attr) >= len(long_article) - 5

        rule_td = tbody.locator("tr").first.locator("td.q-cell-title")
        expect(rule_td).to_be_visible()
        overflow_r = rule_td.evaluate("(el) => getComputedStyle(el).overflow")
        text_overflow_r = rule_td.evaluate("(el) => getComputedStyle(el).textOverflow")
        assert overflow_r in ("hidden", "clip"), f"expected overflow hidden/clip on rule title cell, got {overflow_r}"
        assert text_overflow_r == "ellipsis", (
            f"expected text-overflow ellipsis on rule title cell, got {text_overflow_r}"
        )
        rule_title_attr = rule_td.get_attribute("title") or ""
        assert long_rule[:20] in rule_title_attr or len(rule_title_attr) >= len(long_rule) - 5

        reject_btn = tbody.locator('button:has-text("Reject")').first
        expect(reject_btn).to_be_visible()
        box = reject_btn.bounding_box()
        assert box is not None
        vp = page.viewport_size
        assert box["x"] + box["width"] <= (vp or {}).get("width", 1280) + 2, "Reject should sit in viewport"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_preview_edits_survive_load_queue(self, page: Page):
        """Periodic loadQueue + previewId must not exit YAML edit mode or wipe the textarea."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _stub_sigma_queue_list(page)
        page.goto(f"{base_url}/workflow?previewId=1#queue")
        page.wait_for_load_state("load")

        # Open rule modal
        page.wait_for_selector("#queueTableBody", timeout=15000)
        _trigger_load_queue(page)
        preview_btn = page.locator('#queueTableBody button:has-text("Preview")').first
        expect(preview_btn).to_be_visible(timeout=20000)
        rule_modal = page.locator("#ruleModal")
        if rule_modal.evaluate("el => el.classList.contains('hidden')"):
            preview_btn.click()
        expect(rule_modal).not_to_have_class("hidden", timeout=15000)

        # Enter edit mode and append marker
        rule_modal.locator('button[onclick="enableEditMode()"]').click()
        page.wait_for_timeout(900)
        editor = rule_modal.locator("#yamlEditor")
        expect(editor).to_be_visible(timeout=5000)
        merged = editor.evaluate(
            "(el) => { const m = " + json.dumps(_EDIT_MARKER) + "; el.value = (el.value || '') + m; return el.value; }",
        )
        assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in merged
        assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in editor.input_value()

        # Trigger loadQueue and verify edits survive
        _trigger_load_queue(page)
        page.wait_for_timeout(400)

        editor = page.locator("#ruleModal #yamlEditor")
        expect(editor).to_be_visible(timeout=3000)
        assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in editor.input_value()
        save_btn = page.locator("#ruleModal").get_by_role("button", name="Save Changes")
        expect(save_btn).to_be_visible(timeout=2000)

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_enrich_modal_original_rule_uses_yaml_not_observable_code(self, page: Page):
        """The Enrich modal's Original Rule must be populated from the YAML block, not the first <code>."""
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

        expect(rule_modal).to_contain_text("cmd0")
        expect(rule_modal).to_contain_text("cmd1")

        rule_modal.locator('button:has-text("Enrich")').first.click()

        enrich_modal = page.locator("#enrichModal")
        expect(enrich_modal).to_be_visible(timeout=5000)

        original_textarea = page.locator("#enrichOriginalRule")
        expect(original_textarea).to_be_visible(timeout=3000)
        original_yaml = original_textarea.input_value()

        assert "title: Test Rule" in original_yaml
        assert "detection:" in original_yaml
        assert "cmd0" not in original_yaml


class TestWorkflowExecutionsRegressions:
    """Executions-tab regression tests (consolidated from single-file tests)."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_no_horizontal_overflow_actions_visible(self, page: Page):
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

        overflow = first_article_td.evaluate("(el) => getComputedStyle(el).overflow")
        text_overflow = first_article_td.evaluate("(el) => getComputedStyle(el).textOverflow")
        assert overflow in ("hidden", "clip"), f"expected overflow hidden/clip, got {overflow}"
        assert text_overflow == "ellipsis", f"expected text-overflow ellipsis, got {text_overflow}"

        session_first = tbody.locator("tr").first.locator('button[onclick^="debugInAgentChat"]').first
        expect(session_first).to_be_visible()
        box = session_first.bounding_box()
        vp = page.viewport_size
        assert box and box["x"] + box["width"] <= (vp or {}).get("width", 1280) + 2

        retry_btn = tbody.locator("tr").nth(1).locator('button:has-text("Retry")').first
        expect(retry_btn).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_header_alignment(self, page: Page):
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

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_displays_naive_created_at_as_local_time(self, page: Page):
        """Timezone-less execution timestamps should render without a UTC offset shift."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        mock_payload = {
            "executions": [
                {
                    "id": 88003,
                    "article_id": 103,
                    "article_title": "Local Time Check",
                    "status": "running",
                    "current_step": "os_detection",
                    "ranking_score": None,
                    "created_at": "2026-04-27T15:04:00",
                }
            ],
            "total": 1,
            "total_pages": 1,
            "running": 1,
            "completed": 0,
            "failed": 0,
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

        created_cell = page.locator("#executionsTableBody tr").first.locator("td.q-cell-date")
        expect(created_cell).to_contain_text("3:04 PM")
        expect(created_cell).not_to_contain_text("11:04 AM")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_similar_rule_detail_shows_repo_origin_badge(self, page: Page):
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

            if path == "/api/workflow/executions":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(mock_executions_payload),
                )
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
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"agent_models": {}}),
                )
            elif path.endswith(f"/api/workflow/executions/{execution_id}/observables"):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"execution_id": execution_id, "observables": {}}),
                )
            else:
                route.continue_()

        page.route("**/api/workflow/executions**", handle_route)
        page.route("**/api/workflow/config", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")

        page_errors: list[str] = []
        console_msgs: list[str] = []

        def on_page_error(err):
            page_errors.append(str(err))

        def on_console(msg):
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

        # The execution modal uses a tabbed UI; similarity results are in the
        # "Similarity" tab panel which starts hidden (only the first panel is visible).
        # Click the Similarity tab to make its panel visible before clicking the rule.
        similarity_tab = page.locator("#exec-tab-strip button.exec-tab:has-text('Similarity')")
        if similarity_tab.count() > 0:
            similarity_tab.first.click()
            page.wait_for_timeout(200)

        page.locator("#executionModal").locator(f"text={similar_rule_title}").first.click()

        similar_rule_modal = page.locator("#similarRuleModal")
        expect(similar_rule_modal).to_be_visible()
        expect(similar_rule_modal).to_contain_text("Your repo")
        expect(similar_rule_modal).not_to_contain_text("SigmaHQ")


class TestWorkflowConfigRegressions:
    """Config-tab regression tests (consolidated from single-file tests)."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_huntqueries_qa_prompt_editor_visible(self, page: Page) -> None:
        """Ensure HuntQueries QA prompt editor appears after toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow", wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        subagent_toggle = page.locator("#toggle-huntqueriesextract-enabled")
        if not subagent_toggle.is_checked():
            subagent_toggle.evaluate(
                """el => {
                    el.checked = true;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }"""
            )
            page.wait_for_timeout(300)

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


# ---------------------------------------------------------------------------
# Enrich modal system prompt UI (rework: view/edit mode, validate, hardcoded
# instruction) -- tests the workflow.html enrich modal, not /sigma-queue.
# ---------------------------------------------------------------------------

_VALID_SYSTEM_PROMPT = (
    "You are a SIGMA rule enrichment agent. "
    "updated_sigma_yaml is required. "
    "Output only a JSON object with status pass|needs_revision|fail."
)

_PROMPT_LATEST_MOCK = {
    "success": True,
    "system_prompt": _VALID_SYSTEM_PROMPT,
    "user_instruction": "",
}


class TestWorkflowEnrichModalUI:
    """Tests for the reworked system prompt editor in the workflow enrich modal."""

    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Mock required APIs, navigate to workflow#queue, yield, then clean up."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        def handle_route(route):
            url = route.request.url
            if re.search(r"sigma-queue/list", url):
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
            elif re.search(r"sigma-queue/prompt/latest", url):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(_PROMPT_LATEST_MOCK),
                )
            else:
                route.continue_()

        page.route("**/*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(800)
        yield
        try:
            page.evaluate(
                "() => { ['ruleModal','enrichModal'].forEach(id => {"
                " const el = document.getElementById(id); if (el) el.classList.add('hidden'); }); }"
            )
        except Exception:
            pass

    def _dismiss_modals(self, page: Page):
        """Force-hide both overlay modals via JS so the queue table is interactable.

        Safe to call repeatedly -- idempotent. Used at the start of any test
        that needs to click queue-table rows, to avoid carry-over from the
        previous test leaving a modal open.

        Also clears ?previewId from the URL: the page fixture is class-scoped so
        page.goto() deduplication skips re-navigation when the path is unchanged,
        leaving ?previewId in the URL from a prior test.  checkAndTriggerPreview()
        then auto-opens ruleModal when loadQueue() fires, blocking queue clicks.
        """
        page.evaluate(
            "() => {"
            " ['ruleModal', 'enrichModal'].forEach(id => {"
            "  const el = document.getElementById(id);"
            "  if (el) { el.classList.add('hidden'); el.style.display = ''; }"
            " });"
            " const url = new URL(window.location.href);"
            " url.searchParams.delete('previewId');"
            " window.history.replaceState({}, '', url.toString());"
            "}"
        )
        page.wait_for_timeout(200)

    def _open_enrich_modal(self, page: Page):
        """Click Preview then Enrich; return enrich modal locator.

        Dismisses any lingering modals first so this helper is safe to call
        in back-to-back tests without manual teardown between them.
        """
        self._dismiss_modals(page)

        preview_btn = page.locator('#queueTableBody button:has-text("Preview")').first
        if not preview_btn.is_visible(timeout=10000):
            pytest.skip("No rules in queue to open enrich modal")
        preview_btn.click()
        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=5000)
        rule_modal.locator('button:has-text("Enrich")').first.click()
        enrich_modal = page.locator("#enrichModal")
        expect(enrich_modal).to_be_visible(timeout=5000)
        return enrich_modal

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_system_prompt_display_div_shown_in_view_mode(self, page: Page):
        """On open, display div is visible and textarea is hidden (view mode)."""
        self._open_enrich_modal(page)
        page.wait_for_timeout(500)

        display_div = page.locator("#enrichSystemPromptDisplay")
        textarea = page.locator("#enrichSystemPrompt")

        expect(display_div).to_be_visible(timeout=3000)
        expect(textarea).to_be_hidden(timeout=3000)
        # Display div should contain the loaded prompt text
        content = display_div.text_content()
        assert content and len(content.strip()) > 0, "Display div should show the system prompt text"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_user_instruction_field_is_hidden(self, page: Page):
        """enrichInstruction wrapper must carry the 'hidden' class in the DOM.

        The instruction is hardcoded in JS, so we verify via DOM inspection
        rather than opening the modal -- the class is baked into the HTML and
        does not require modal interaction to assert.
        """
        has_hidden = page.evaluate(
            """() => {
                const el = document.getElementById('enrichInstruction');
                if (!el) return null;
                // Walk up to find the wrapping div that carries the hidden class
                let node = el;
                while (node && node !== document.body) {
                    if (node.classList.contains('hidden')) return true;
                    node = node.parentElement;
                }
                return false;
            }"""
        )
        assert has_hidden is True, (
            "#enrichInstruction or its wrapper should have class 'hidden' "
            "(user instruction is hardcoded -- the field must not be shown)"
        )

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_edit_button_switches_to_edit_mode(self, page: Page):
        """Clicking Edit reveals the textarea and hides the display div."""
        self._open_enrich_modal(page)
        page.wait_for_timeout(300)

        page.locator("#enrichSPEditBtn").click()
        page.wait_for_timeout(200)

        expect(page.locator("#enrichSystemPrompt")).to_be_visible(timeout=3000)
        expect(page.locator("#enrichSystemPromptDisplay")).to_be_hidden(timeout=3000)
        expect(page.locator("#enrichSPSaveBtn")).to_be_visible(timeout=2000)
        expect(page.locator("#enrichSPCancelBtn")).to_be_visible(timeout=2000)

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_validate_clears_stale_result_on_modal_reopen(self, page: Page):
        """Validate result from a previous session must not show on fresh open."""
        enrich_modal = self._open_enrich_modal(page)
        page.wait_for_timeout(300)

        # Manually inject a stale result
        page.evaluate(
            """() => {
                const d = document.getElementById('enrichValidateResult');
                if (d) { d.style.display = ''; d.textContent = 'Stale result'; }
            }"""
        )

        # Close via the header X button; use nth(0) to avoid strict-mode violation
        # (.first property does not suppress strict mode in all Playwright versions)
        enrich_modal.locator('button[onclick="closeEnrichModal()"]').nth(0).click()
        page.wait_for_timeout(200)
        self._open_enrich_modal(page)
        page.wait_for_timeout(400)

        result_div = page.locator("#enrichValidateResult")
        # Should be hidden or empty after reopening
        is_hidden = not result_div.is_visible()
        is_empty = (result_div.text_content() or "").strip() == ""
        assert is_hidden or is_empty, "Stale validate result must be cleared on modal reopen"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_validate_passes_for_compliant_prompt(self, page: Page):
        """Clicking Validate with a prompt containing updated_sigma_yaml shows a pass result."""
        self._open_enrich_modal(page)
        page.wait_for_timeout(300)

        page.locator('button[onclick="validateEnrichSystemPrompt()"]').click()
        page.wait_for_timeout(200)

        result_div = page.locator("#enrichValidateResult")
        expect(result_div).to_be_visible(timeout=3000)
        content = result_div.text_content() or ""
        assert "passed" in content.lower() or "ready" in content.lower(), f"Expected pass message, got: {content!r}"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_validate_errors_on_missing_updated_sigma_yaml(self, page: Page):
        """A prompt without 'updated_sigma_yaml' produces an ERROR in the validate result."""
        self._open_enrich_modal(page)
        page.wait_for_timeout(300)

        # Enter edit mode and replace prompt with one missing updated_sigma_yaml
        page.locator("#enrichSPEditBtn").click()
        page.wait_for_timeout(200)
        textarea = page.locator("#enrichSystemPrompt")
        textarea.fill("You are a SIGMA agent. Output only JSON with status pass or fail.")

        page.locator('button[onclick="validateEnrichSystemPrompt()"]').click()
        page.wait_for_timeout(200)

        result_div = page.locator("#enrichValidateResult")
        expect(result_div).to_be_visible(timeout=3000)
        content = result_div.text_content() or ""
        assert "error" in content.lower(), f"Expected error about updated_sigma_yaml, got: {content!r}"
        assert "updated_sigma_yaml" in content

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_save_blocked_when_prompt_has_errors(self, page: Page):
        """Save must not proceed and must show validation errors when prompt is non-compliant."""
        # Intercept the save endpoint to detect any accidental call
        save_called = []

        def intercept_save(route):
            save_called.append(route.request.url)
            route.continue_()

        page.route("**/api/sigma-queue/prompt/save**", intercept_save)

        self._open_enrich_modal(page)
        page.wait_for_timeout(300)

        page.locator("#enrichSPEditBtn").click()
        page.wait_for_timeout(200)
        page.locator("#enrichSystemPrompt").fill("Short bad prompt")

        page.locator("#enrichSPSaveBtn").click()
        page.wait_for_timeout(400)

        # Validate result must show errors
        result_div = page.locator("#enrichValidateResult")
        expect(result_div).to_be_visible(timeout=3000)
        assert "error" in (result_div.text_content() or "").lower()

        # Must still be in edit mode (textarea visible, save btn visible)
        expect(page.locator("#enrichSystemPrompt")).to_be_visible(timeout=2000)
        expect(page.locator("#enrichSPSaveBtn")).to_be_visible(timeout=2000)

        # Save endpoint must NOT have been called
        assert not save_called, f"Save endpoint should not be called when validation fails: {save_called}"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_validate_rule_label_in_preview_modal(self, page: Page):
        """SIGMA Rule Preview action bar shows 'Validate Rule', not bare 'Validate'."""
        self._dismiss_modals(page)
        preview_btn = page.locator('#queueTableBody button:has-text("Preview")').first
        if not preview_btn.is_visible(timeout=10000):
            pytest.skip("No rules in queue to test")
        preview_btn.click()
        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=5000)

        # Should find 'Validate Rule' button
        validate_rule_btn = rule_modal.locator('button:has-text("Validate Rule")')
        expect(validate_rule_btn).to_be_visible(timeout=3000)

        # Must not have a button labelled exactly 'Validate' (without 'Rule')
        exact_validate = rule_modal.locator('button:text-is("Validate")')
        assert exact_validate.count() == 0, "Bare 'Validate' button should not exist; expected 'Validate Rule'"
