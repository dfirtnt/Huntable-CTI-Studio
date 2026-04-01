import json
import os

import pytest
from playwright.sync_api import Page, expect


def _dashboard_payload(status: str, uptime: float) -> dict:
    return {
        "health": {
            "uptime": uptime,
            "status": status,
            "label": status.title(),
            "total_sources": 12,
            "monitored_sources": 10,
            "healthy_sources": 8,
            "warning_sources": 2 if status == "degraded" else 0,
            "critical_sources": 0,
            "avg_response_time": 1.42,
        },
        "volume": {
            "daily": {"2026-03-30": 1, "2026-03-31": 2, "2026-04-01": 3},
            "hourly": {"00": 0, "01": 1, "02": 0},
        },
        "failing_sources": [],
        "top_articles": [],
        "recent_activities": [],
        "stats": {
            "total_articles": 100,
            "active_sources": 10,
            "avg_hunt_score": 55.2,
            "filter_efficiency": 66.7,
        },
        "healing_enabled": False,
    }


@pytest.mark.ui
@pytest.mark.dashboard
def test_dashboard_uses_api_health_status_not_only_uptime_threshold(page: Page):
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

    def handle_dashboard_data(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_dashboard_payload("degraded", 75.0)),
        )

    page.route("**/api/dashboard/data", handle_dashboard_data)
    page.goto(f"{base_url}/")
    page.wait_for_load_state("load")

    expect(page.locator("#uptime-value")).to_have_text("75.0%")
    expect(page.locator("#health-status-text")).to_have_text("Degraded")
