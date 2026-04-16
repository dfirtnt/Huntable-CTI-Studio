import json
import os

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

_MOCK_EVENTS = [
    {
        "id": 1,
        "source_id": 17,
        "round_number": 1,
        "diagnosis": "HTTP 403 on main URL and RSS feed. Access is forbidden.",
        "actions_proposed": [],
        "actions_applied": [],
        "validation_success": None,
        "error_message": None,
        "created_at": "2026-04-14T01:00:00",
    },
    {
        "id": 2,
        "source_id": 17,
        "round_number": 2,
        "diagnosis": "Tried alternate RSS endpoint, still 403.",
        "actions_proposed": [],
        "actions_applied": [],
        "validation_success": None,
        "error_message": None,
        "created_at": "2026-04-14T02:00:00",
    },
]

_MOCK_HISTORY_IDLE = {
    "source_id": 17,
    "source_name": "Test Source",
    "events": _MOCK_EVENTS,
    "max_attempts": 8,
    "current_round": 2,
    "status": "idle",
    "healing_exhausted": False,
}


def _make_history_route(payload):
    def handler(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    return handler


@pytest.mark.ui
@pytest.mark.sources
def test_healing_history_shows_runtime_errors_as_details(page: Page):
    def handle_history(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "source_id": 17,
                    "source_name": "Sekoia.io Threat Research & Intelligence",
                    "events": [
                        {
                            "id": 999,
                            "source_id": 17,
                            "round_number": 2,
                            "diagnosis": "LLM call failed: ConnectError",
                            "actions_proposed": [],
                            "actions_applied": [],
                            "validation_success": None,
                            "error_message": "No address associated with hostname",
                            "created_at": "2026-04-01T01:05:00",
                        }
                    ],
                    "max_attempts": 8,
                    "current_round": 2,
                    "status": "idle",
                    "healing_exhausted": False,
                }
            ),
        )

    page.route("**/api/sources/*/healing-history", handle_history)
    page.goto(f"{BASE_URL}/sources")
    # networkidle ensures the initial updateHealingStatusBadges() batch finishes
    # before we interact with the panel, preventing concurrent route-handler
    # contention from leaving the panel fetch unfulfilled.
    page.wait_for_load_state("networkidle")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    expect(page.locator("#healingPanelTitle")).to_contain_text("Healing History")
    expect(page.locator("#healingPanelBody")).to_contain_text("Details:")
    expect(page.locator("#healingPanelBody")).to_contain_text("No address associated with hostname")
    expect(page.locator("#healingPanelBody")).not_to_contain_text("Validation fetch:")


@pytest.mark.ui
@pytest.mark.sources
def test_history_panel_toggle_survives_poll(page: Page):
    """Expanding 'Show LLM reasoning' must not collapse after the 3s poll re-render."""
    page.route("**/api/sources/*/healing-history", _make_history_route(_MOCK_HISTORY_IDLE))

    page.goto(f"{BASE_URL}/sources")
    page.wait_for_load_state("networkidle")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    # Wait for the panel to render the events
    diag_btn = page.locator("#healingPanelBody button", has_text="Show LLM reasoning").first
    expect(diag_btn).to_be_visible()
    diag_btn.click()
    expect(diag_btn).to_have_text("Hide LLM reasoning")

    # Wait for at least one poll cycle (interval is 3s)
    page.wait_for_timeout(3500)

    # Toggle must still be open after the re-render
    expect(diag_btn).to_have_text("Hide LLM reasoning")
    expect(page.locator("#healingPanelBody .heal-event-diagnosis.open").first).to_be_visible()


@pytest.mark.ui
@pytest.mark.sources
def test_history_panel_config_toggle_survives_poll(page: Page):
    """Expanding 'Show full config' must not collapse after the 3s poll re-render."""
    page.route("**/api/sources/*/healing-history", _make_history_route(_MOCK_HISTORY_IDLE))

    page.goto(f"{BASE_URL}/sources")
    page.wait_for_load_state("networkidle")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    config_btn = page.locator("#healingPanelBody button", has_text="Show full config").first
    expect(config_btn).to_be_visible()
    config_btn.click()
    expect(config_btn).to_have_text("Hide full config")

    page.wait_for_timeout(3500)

    expect(config_btn).to_have_text("Hide full config")


_MOCK_HISTORY_IN_PROGRESS = {
    "source_id": 17,
    "source_name": "Test Source",
    "events": _MOCK_EVENTS,
    "max_attempts": 8,
    "current_round": 2,
    "status": "in_progress",
    "healing_exhausted": False,
}

_MOCK_HISTORY_HEALED = {
    "source_id": 17,
    "source_name": "Test Source",
    "events": [
        {
            "id": 3,
            "source_id": 17,
            "round_number": 3,
            "diagnosis": "RSS endpoint changed. Updated rss_url.",
            "actions_proposed": [],
            "actions_applied": [],
            "validation_success": True,
            "error_message": None,
            "created_at": "2026-04-15T03:00:00",
        }
    ],
    "max_attempts": 8,
    "current_round": 3,
    "status": "healed",
    "healing_exhausted": False,
}

_MOCK_HISTORY_EXHAUSTED = {
    "source_id": 17,
    "source_name": "Test Source",
    "events": _MOCK_EVENTS,
    "max_attempts": 8,
    "current_round": 8,
    "status": "exhausted",
    "healing_exhausted": True,
}


@pytest.mark.ui
@pytest.mark.sources
def test_progress_container_renders_round_info(page: Page):
    """When events exist, the progress container shows round N of M and the status badge."""
    page.route("**/api/sources/*/healing-history", _make_history_route(_MOCK_HISTORY_IN_PROGRESS))

    page.goto(f"{BASE_URL}/sources")
    page.wait_for_load_state("networkidle")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    progress_label = page.locator("#healingPanelBody .healing-progress-label")
    expect(progress_label).to_be_visible()
    expect(progress_label).to_contain_text("2")
    expect(progress_label).to_contain_text("8")

    status_badge = page.locator("#healingPanelBody .healing-progress-status")
    expect(status_badge).to_be_visible()
    expect(status_badge).to_contain_text("In Progress")


@pytest.mark.ui
@pytest.mark.sources
def test_healed_completion_banner_shows_success(page: Page):
    """When status is 'healed', a success banner is rendered with the round number."""
    page.route("**/api/sources/*/healing-history", _make_history_route(_MOCK_HISTORY_HEALED))

    page.goto(f"{BASE_URL}/sources")
    page.wait_for_load_state("networkidle")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    banner = page.locator("#healingPanelBody .healing-completion-banner.success")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("successfully healed")
    expect(banner).to_contain_text("round 3")
    expect(page.locator("#healingPanelBody .healing-completion-banner.failure")).not_to_be_visible()


@pytest.mark.ui
@pytest.mark.sources
def test_exhausted_completion_banner_shows_failure(page: Page):
    """When status is 'exhausted', a failure banner is rendered with max_attempts."""
    page.route("**/api/sources/*/healing-history", _make_history_route(_MOCK_HISTORY_EXHAUSTED))

    page.goto(f"{BASE_URL}/sources")
    page.wait_for_load_state("networkidle")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    banner = page.locator("#healingPanelBody .healing-completion-banner.failure")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("Healing exhausted")
    expect(banner).to_contain_text("8 rounds")
    expect(page.locator("#healingPanelBody .healing-completion-banner.success")).not_to_be_visible()
