"""
Smoke tests: /workflow sub-pages actually render inner content.

Gap this closes:
    Existing tests (tests/ui/test_workflow_tabs.py and
    tests/ui/test_workflow_comprehensive_ui.py::TestWorkflowTabNavigation)
    assert the tab *panel* container becomes visible and loses the `hidden`
    class when a tab is clicked. They do NOT assert that any inner content
    inside the panel is rendered. A panel can be visible while containing
    zero rendered children -- which is the user-reported failure mode:
    navigating to /workflow#queue (and the sibling #config, #executions
    sub-pages) shows no content.

    These smoke tests:
      1. Exercise direct hash-URL entry (e.g. /workflow#queue) -- its own
         code path through the tab-init JS distinct from a click.
      2. Assert inner content markers unique to each sub-page's template.
      3. Capture BOTH synchronous uncaught exceptions AND unhandled promise
         rejections -- the latter is the common root cause of empty panels
         (e.g. an async DOMContentLoaded handler whose sync body throws
         shows up in the browser console as "Uncaught (in promise) ..."
         and is NOT caught by Playwright's ``page.on('pageerror')``).
      4. Assert the old panel gets hidden when switching tabs -- a stricter
         signal than "new panel becomes visible", because a mid-function
         abort in switchTab() leaves the hide step applied but the show
         step skipped, so only the round-trip catches it.

Requires a running app on CTI_SCRAPER_URL (default http://localhost:8001).
"""

from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")


# Injected before any page script runs. Captures both synchronous errors and
# unhandled promise rejections into a global array that the test reads back
# via page.evaluate(). Playwright's ``page.on('pageerror')`` only fires for
# synchronous throws in the main execution context; ``unhandledrejection``
# events (which wrap sync throws inside an async context such as an async
# DOMContentLoaded listener) do not. Without this, a SyntaxError thrown
# inside a forEach called from an async init handler slips past silently.
_ERROR_CAPTURE_INIT_SCRIPT = """
(() => {
    if (window.__workflowTestErrors) return;
    const errors = [];
    window.__workflowTestErrors = errors;
    window.addEventListener('error', (e) => {
        errors.push({kind: 'error', message: (e.error && (e.error.stack || e.error.message)) || e.message || String(e)});
    });
    window.addEventListener('unhandledrejection', (e) => {
        const r = e.reason;
        errors.push({kind: 'unhandledrejection', message: (r && (r.stack || r.message)) || String(r)});
    });
})();
"""


def _collect_page_errors(page: Page) -> list[str]:
    """Attach listeners for sync uncaught exceptions.

    Also injects an init-script to capture unhandled promise rejections
    (see _ERROR_CAPTURE_INIT_SCRIPT).
    """
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.add_init_script(_ERROR_CAPTURE_INIT_SCRIPT)
    return errors


def _read_in_page_errors(page: Page) -> list[dict]:
    """Read the unhandled-rejection / error log captured inside the page."""
    try:
        return page.evaluate("() => window.__workflowTestErrors || []") or []
    except Exception:
        return []


def _assert_no_js_errors(page: Page, sync_errors: list[str], context: str) -> None:
    """Combine Playwright-side and in-page error captures, fail if any."""
    in_page = _read_in_page_errors(page)
    all_errors = sync_errors + [f"{e['kind']}: {e['message']}" for e in in_page]
    assert not all_errors, f"JS errors on {context}: {all_errors}"


def _goto_workflow(fresh_page: Page, hash_fragment: str) -> list[str]:
    """Navigate to /workflow with a hash fragment and wait for load.

    Uses fresh_page so each test starts from about:blank -- the tab-init JS
    is hash-driven on initial load, so reusing a page would mask regressions.
    """
    errors = _collect_page_errors(fresh_page)
    fresh_page.goto(f"{BASE_URL}/workflow{hash_fragment}", wait_until="domcontentloaded")
    fresh_page.wait_for_load_state("load")
    # Give any async init handlers time to settle so unhandledrejection events fire.
    fresh_page.wait_for_timeout(500)
    return errors


@pytest.mark.ui
@pytest.mark.ui_smoke
@pytest.mark.workflow
def test_workflow_config_subpage_renders_inner_content(fresh_page: Page):
    """/workflow#config: panel visible AND inner config form + pipeline rail rendered."""
    errors = _goto_workflow(fresh_page, "#config")

    panel = fresh_page.locator("#tab-content-config")
    panel.wait_for(state="visible", timeout=10000)

    # Inner-content assertions -- these are what the existing tab-visibility
    # tests do NOT check. An empty panel would pass those but fail these.
    form = fresh_page.locator("#workflowConfigForm")
    expect(form).to_be_visible()

    # First pipeline step (OS Detection) is the canonical "config content rendered" marker.
    first_step = fresh_page.locator("#s0")
    expect(first_step).to_be_visible()
    expect(first_step).not_to_have_count(0)

    # Sanity: the panel should contain more than a trivial amount of text.
    # Empty/broken render typically produces <100 chars of whitespace.
    text = panel.inner_text()
    assert len(text.strip()) > 200, f"Config panel rendered but appears empty (len={len(text.strip())})"

    _assert_no_js_errors(fresh_page, errors, "/workflow#config")


@pytest.mark.ui
@pytest.mark.ui_smoke
@pytest.mark.workflow
def test_workflow_executions_subpage_renders_inner_content(fresh_page: Page):
    """/workflow#executions: panel visible AND stats grid + table body rendered."""
    errors = _goto_workflow(fresh_page, "#executions")

    panel = fresh_page.locator("#tab-content-executions")
    panel.wait_for(state="visible", timeout=10000)

    # Stats cards present (IDs populated by JS; element existence proves template rendered).
    expect(fresh_page.locator("#executionStats")).to_be_visible()
    expect(fresh_page.locator("#totalExecutions")).to_be_visible()

    # Table shell renders even before data loads (the "Loading..." placeholder row).
    table_body = fresh_page.locator("#executionsTableBody")
    expect(table_body).to_be_visible()
    expect(table_body.locator("tr")).not_to_have_count(0)

    # Command-strip actions are part of the template; visible proves content region rendered.
    expect(fresh_page.get_by_role("button", name=re.compile(r"Refresh", re.I)).first).to_be_visible()

    _assert_no_js_errors(fresh_page, errors, "/workflow#executions")


@pytest.mark.ui
@pytest.mark.ui_smoke
@pytest.mark.workflow
def test_workflow_queue_subpage_renders_inner_content(fresh_page: Page):
    """/workflow#queue: panel visible AND stats grid + queue table rendered.

    This is the exact URL the user reported as broken.
    """
    errors = _goto_workflow(fresh_page, "#queue")

    panel = fresh_page.locator("#tab-content-queue")
    panel.wait_for(state="visible", timeout=10000)

    # Stats cards present.
    expect(fresh_page.locator("#queueStats")).to_be_visible()
    expect(fresh_page.locator("#pendingCount")).to_be_visible()

    # Table shell must render (even if "Loading..." placeholder is the only row).
    table_body = fresh_page.locator("#queueTableBody")
    expect(table_body).to_be_visible()
    expect(table_body.locator("tr")).not_to_have_count(0)

    # Submit-PR button is unique to the queue sub-page -- proves queue template, not a sibling, rendered.
    expect(fresh_page.locator("#submitPRBtn")).to_be_visible()

    _assert_no_js_errors(fresh_page, errors, "/workflow#queue")


@pytest.mark.ui
@pytest.mark.ui_smoke
@pytest.mark.workflow
def test_workflow_default_entry_renders_config_content(fresh_page: Page):
    """/workflow with no hash: defaults to Configuration and renders its content.

    Separately covers the no-hash default path; the three hash-entry tests above
    only cover explicit fragments.
    """
    errors = _collect_page_errors(fresh_page)
    fresh_page.goto(f"{BASE_URL}/workflow", wait_until="domcontentloaded")
    fresh_page.wait_for_load_state("load")

    panel = fresh_page.locator("#tab-content-config")
    panel.wait_for(state="visible", timeout=10000)

    # Same inner-content marker as the #config test: form must render.
    expect(fresh_page.locator("#workflowConfigForm")).to_be_visible()
    expect(fresh_page.locator("#s0")).to_be_visible()

    _assert_no_js_errors(fresh_page, errors, "/workflow (default)")


@pytest.mark.ui
@pytest.mark.ui_smoke
@pytest.mark.workflow
def test_workflow_tab_switch_populates_target_panel_content(fresh_page: Page):
    """Click-based tab switch must reveal inner content AND hide the old panel.

    Mirrors the hash-entry tests but via click navigation to catch regressions
    where hash entry works but switchTab() leaves panels empty (or vice versa).

    Uses ``fresh_page`` (not the class-scoped ``page``) so the init-script that
    captures unhandledrejection events is installed *before* the page's own
    scripts run. The class-scoped page reuses a tab that has already loaded,
    which means add_init_script() would not apply to the current document.

    Asserts BOTH directions of every switch:
      * New panel becomes visible (post-throw work -- line 3074 in workflow.html)
      * Old panel gets the ``hidden`` class (pre-throw work -- line 3057-3059)
    A mid-function abort in switchTab() leaves the hide step applied but the
    show step skipped; round-tripping both catches it cleanly.
    """
    errors = _goto_workflow(fresh_page, "")

    config_panel = fresh_page.locator("#tab-content-config")
    exec_panel = fresh_page.locator("#tab-content-executions")
    queue_panel = fresh_page.locator("#tab-content-queue")

    # Initial state: config is the default; executions + queue are hidden.
    expect(config_panel).to_be_visible()
    expect(exec_panel).to_be_hidden()
    expect(queue_panel).to_be_hidden()

    # Click Executions: new panel visible, config panel hidden.
    fresh_page.locator("#tab-executions").click()
    expect(exec_panel).to_be_visible()
    expect(config_panel).to_be_hidden()
    expect(queue_panel).to_be_hidden()
    expect(fresh_page.locator("#totalExecutions")).to_be_visible()
    expect(fresh_page.locator("#executionsTableBody tr")).not_to_have_count(0)

    # Click Queue: new panel visible, executions panel hidden.
    fresh_page.locator("#tab-queue").click()
    expect(queue_panel).to_be_visible()
    expect(exec_panel).to_be_hidden()
    expect(config_panel).to_be_hidden()
    expect(fresh_page.locator("#pendingCount")).to_be_visible()
    expect(fresh_page.locator("#queueTableBody tr")).not_to_have_count(0)

    # Click Config: new panel visible, queue panel hidden.
    fresh_page.locator("#tab-config").click()
    expect(config_panel).to_be_visible()
    expect(queue_panel).to_be_hidden()
    expect(exec_panel).to_be_hidden()
    expect(fresh_page.locator("#workflowConfigForm")).to_be_visible()
    expect(fresh_page.locator("#s0")).to_be_visible()

    _assert_no_js_errors(fresh_page, errors, "/workflow click-switch round trip")


# ──────────────────────────────────────────────────────────────────────────
# Pipeline rail nav contract
#
# Invariant we assert:
#   - Exactly one step-section is `.open` at a time.
#   - The matching `.rail-item` is the only one with `.active`.
#   - All four input paths (rail click, header click, initial load, toggle-and-reload)
#     converge on this invariant. Prior to the unification there was an
#     IntersectionObserver path that could race with the accordion and leave
#     `.active` on a step other than the one open — this test locks that out.
# ──────────────────────────────────────────────────────────────────────────


def _assert_single_open_matches_rail(page: Page, expected_index: int) -> None:
    """Exactly one .step-section is .open, and the matching rail item is .active."""
    open_ids = page.evaluate("() => Array.from(document.querySelectorAll('.step-section.open')).map(e => e.id)")
    assert open_ids == [f"s{expected_index}"], f"Expected only s{expected_index} open, got {open_ids}"
    active_indices = page.evaluate(
        "() => Array.from(document.querySelectorAll('.rail-item'))"
        "  .map((e, i) => e.classList.contains('active') ? i : -1)"
        "  .filter(i => i >= 0)"
    )
    assert active_indices == [expected_index], f"Expected rail index {expected_index} active, got {active_indices}"


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_config_rail_nav_contract(fresh_page: Page):
    """Rail click, section-header click, and initial state all honour the
    "one open step = one active rail item" invariant."""
    errors = _goto_workflow(fresh_page, "#config")
    fresh_page.locator("#tab-content-config").wait_for(state="visible", timeout=10000)

    # --- Initial state: rail collapsed by default; s0 open and active.
    rail = fresh_page.locator("#oc-rail")
    expect(rail).to_have_class(re.compile(r"\bcollapsed\b"))
    _assert_single_open_matches_rail(fresh_page, 0)

    # --- Every rail item has a title tooltip (the hover affordance that
    # makes the collapsed, digit-only rail discoverable).
    missing_titles = fresh_page.evaluate(
        "() => Array.from(document.querySelectorAll('.rail-item'))"
        "  .map((e, i) => ({i, t: e.getAttribute('title')}))"
        "  .filter(x => !x.t || !x.t.trim())"
    )
    assert missing_titles == [], f"Rail items without title: {missing_titles}"

    # --- Click a rail number -> that step opens, others close, rail follows.
    fresh_page.locator(".rail-item.c3").click()
    fresh_page.wait_for_timeout(150)  # smooth scroll + accordion settle
    _assert_single_open_matches_rail(fresh_page, 3)

    # --- Click a section header -> same contract as rail click.
    fresh_page.locator("#s1 .section-header").click()
    fresh_page.wait_for_timeout(150)
    _assert_single_open_matches_rail(fresh_page, 1)

    # --- Clicking the currently-open header must NOT close it (the prior
    # plain-accordion toggle behaviour would have left zero sections open,
    # breaking the invariant).
    fresh_page.locator("#s1 .section-header").click()
    fresh_page.wait_for_timeout(100)
    _assert_single_open_matches_rail(fresh_page, 1)

    _assert_no_js_errors(fresh_page, errors, "/workflow#config rail contract")


@pytest.mark.ui
@pytest.mark.workflow
def test_workflow_config_rail_collapse_persists(fresh_page: Page):
    """Toggling the rail writes to localStorage and a reload honours it."""
    errors = _goto_workflow(fresh_page, "#config")
    fresh_page.locator("#tab-content-config").wait_for(state="visible", timeout=10000)

    rail = fresh_page.locator("#oc-rail")
    expect(rail).to_have_class(re.compile(r"\bcollapsed\b"))

    # Expand via the toggle button; localStorage should record "0".
    fresh_page.locator(".oc-rail-toggle").click()
    fresh_page.wait_for_timeout(100)
    expect(rail).not_to_have_class(re.compile(r"\bcollapsed\b"))
    stored = fresh_page.evaluate("() => localStorage.getItem('oc-rail-collapsed')")
    assert stored == "0", f"Expected localStorage '0' after expand, got {stored!r}"

    # Reload: the IIFE restore block should honour the stored preference.
    fresh_page.reload(wait_until="domcontentloaded")
    fresh_page.wait_for_load_state("load")
    fresh_page.wait_for_timeout(300)
    expect(rail).not_to_have_class(re.compile(r"\bcollapsed\b"))

    _assert_no_js_errors(fresh_page, errors, "/workflow#config rail persistence")
