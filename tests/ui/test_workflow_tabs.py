"""
Smoke test: workflow (Agents) page tab navigation — Configuration, Executions, SIGMA Queue.

Requires the app to be running with the workflow tab fix (workflow.html: delegated click,
hash sync, type="button" on tab buttons). Run against a server that has loaded the latest template.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.ui_smoke
def test_workflow_tabs_navigation(page: Page):
    """Smoke: Configuration, Executions, and SIGMA Queue tabs are navigable and sync URL hash."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    page.goto(f"{base_url}/workflow", wait_until="domcontentloaded")
    page.wait_for_load_state("load")

    expect(page).to_have_url(re.compile(r".*/workflow.*"))
    config_panel = page.locator("#tab-content-config")
    executions_panel = page.locator("#tab-content-executions")
    queue_panel = page.locator("#tab-content-queue")

    # Wait for tab init (default tab is config)
    config_panel.wait_for(state="visible", timeout=10000)

    # Switch to Executions
    page.locator("#tab-executions").click()
    executions_panel.wait_for(state="visible", timeout=5000)
    expect(page).to_have_url(re.compile(r".*#executions"))
    expect(config_panel).to_be_hidden()
    expect(queue_panel).to_be_hidden()

    # Switch to SIGMA Queue
    page.locator("#tab-queue").click()
    queue_panel.wait_for(state="visible", timeout=5000)
    expect(page).to_have_url(re.compile(r".*#queue"))
    expect(config_panel).to_be_hidden()
    expect(executions_panel).to_be_hidden()

    # Switch back to Configuration
    page.locator("#tab-config").click()
    config_panel.wait_for(state="visible", timeout=5000)
    expect(page).to_have_url(re.compile(r".*#config"))
    expect(executions_panel).to_be_hidden()
    expect(queue_panel).to_be_hidden()
