"""Playwright UI tests for dynamic-modal ARIA semantics (commit ca6f14a1).

These exercise the real browser path: ModalManager.prompt()/confirm() build a modal
at runtime and must present as a dialog to assistive tech (role=dialog, aria-modal=true,
and a label derived from the title). This is the repo-conventional UI-level coverage that
complements tests/static/js/test_modal_aria_jsdom.py (fast, no-browser regression checks).

Skips automatically when no web server / Playwright browsers (see tests/ui/conftest.py).
Run in CI via: python3 run_tests.py ui
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
def test_modal_manager_prompt_modal_exposes_aria(page: Page):
    """ModalManager.prompt() must render an ARIA dialog with a title-derived label."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")

    # Build a prompt modal exactly as the app does at runtime.
    page.evaluate(
        "ModalManager.prompt('Rename rule?', '', { title: 'Rename Rule', required: true })"
        ".catch(() => {})"
    )
    modal = page.locator('[role="dialog"]').first
    expect(modal).to_be_visible()
    assert modal.get_attribute("role") == "dialog"
    assert modal.get_attribute("aria-modal") == "true"
    assert modal.get_attribute("aria-label") == "Rename Rule"
    # Tear down so it does not leak into sibling tests.
    page.evaluate("() => { const m = document.querySelector('[role=\"dialog\"]'); if (m) m.remove(); }")


@pytest.mark.ui
def test_modal_manager_confirm_modal_exposes_aria(page: Page):
    """ModalManager.confirm() must render an ARIA dialog with a title-derived label."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    page.wait_for_load_state("load")

    page.evaluate(
        "ModalManager.confirm('Delete this rule?', { title: 'Delete Rule' }).catch(() => {})"
    )
    modal = page.locator('[role="dialog"]').first
    expect(modal).to_be_visible()
    assert modal.get_attribute("role") == "dialog"
    assert modal.get_attribute("aria-modal") == "true"
    assert modal.get_attribute("aria-label") == "Delete Rule"
    page.evaluate("() => { const m = document.querySelector('[role=\"dialog\"]'); if (m) m.remove(); }")
