import json
import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.sources
def test_healing_history_shows_runtime_errors_as_details(page: Page):
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

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
                }
            ),
        )

    page.route("**/api/sources/*/healing-history", handle_history)
    page.goto(f"{base_url}/sources")
    page.wait_for_load_state("load")

    history_buttons = page.locator("button[aria-label^='View healing history for ']")
    expect(history_buttons.first).to_be_visible()
    history_buttons.first.click()

    expect(page.locator("#healingPanelTitle")).to_contain_text("Healing History")
    expect(page.locator("#healingPanelBody")).to_contain_text("Details:")
    expect(page.locator("#healingPanelBody")).to_contain_text("No address associated with hostname")
    expect(page.locator("#healingPanelBody")).not_to_contain_text("Validation fetch:")
