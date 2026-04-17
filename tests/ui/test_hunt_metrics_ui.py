"""
UI regression tests for hunt metrics help tooltips.
"""

import os

import pytest
from playwright.sync_api import Page, expect


class TestHuntMetricsTooltips:
    """Verify hunt metrics help tooltips stay usable after the tooltip audit."""

    @pytest.mark.ui
    def test_keyword_performance_help_tooltip_stays_within_viewport(self, page: Page):
        """The keyword performance help tooltip should not be clipped or overflow the viewport."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("load")

        card = page.locator("#keywordPerformanceCard")
        help_button = page.locator("#keywordPerformanceHelpButton")
        tooltip = page.locator("#keywordPerformanceHelpTooltip")

        expect(card).to_be_visible()
        expect(help_button).to_be_visible()

        help_button.focus()
        expect(tooltip).to_be_visible()

        tooltip_box = tooltip.bounding_box()
        viewport = page.viewport_size
        overflow = page.evaluate("() => getComputedStyle(document.getElementById('keywordPerformanceCard')).overflow")

        assert viewport is not None, "Playwright viewport should be available"
        assert tooltip_box is not None, "Keyword performance tooltip should have a bounding box"
        assert overflow == "visible", "Keyword performance card should allow visible overflow for its tooltip"
        assert tooltip_box["x"] >= 0, "Keyword performance tooltip should not extend off the left edge"
        assert tooltip_box["x"] + tooltip_box["width"] <= viewport["width"], (
            "Keyword performance tooltip should stay within the viewport width"
        )

    @pytest.mark.ui
    def test_quality_breakdown_help_tooltip_stays_within_viewport(self, page: Page):
        """The content quality help tooltip should not be clipped or overflow the viewport."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("load")

        card = page.locator("#qualityBreakdownCard")
        help_button = page.locator("#qualityBreakdownHelpButton")
        tooltip = page.locator("#qualityBreakdownHelpTooltip")

        expect(card).to_be_visible()
        expect(help_button).to_be_visible()

        help_button.focus()
        expect(tooltip).to_be_visible()

        tooltip_box = tooltip.bounding_box()
        viewport = page.viewport_size
        overflow = page.evaluate("() => getComputedStyle(document.getElementById('qualityBreakdownCard')).overflow")

        assert viewport is not None, "Playwright viewport should be available"
        assert tooltip_box is not None, "Quality breakdown tooltip should have a bounding box"
        assert overflow == "visible", "Quality breakdown card should allow visible overflow for its tooltip"
        assert tooltip_box["x"] >= 0, "Quality breakdown tooltip should not extend off the left edge"
        assert tooltip_box["x"] + tooltip_box["width"] <= viewport["width"], (
            "Quality breakdown tooltip should stay within the viewport width"
        )
