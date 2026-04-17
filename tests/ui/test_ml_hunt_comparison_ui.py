"""
UI regression tests for the ML Hunt Comparison page.
"""

import os

import pytest
from playwright.sync_api import Page, expect


class TestMlHuntComparisonTooltip:
    """Verify help overlays on the ML Hunt Comparison page render cleanly."""

    @pytest.mark.ui
    def test_eligible_articles_tooltip_renders_outside_card(self, page: Page):
        """The Eligible Articles help tooltip must not be clipped by the KPI card."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        page.goto(f"{base_url}/ml-hunt-comparison")
        page.wait_for_load_state("load")

        card = page.locator("#eligibleArticlesCard")
        help_button = page.locator("#eligibleArticlesHelpButton")
        tooltip = page.locator("#eligibleArticlesHelpTooltip")

        expect(card).to_be_visible()
        expect(help_button).to_be_visible()

        help_button.hover()
        expect(tooltip).to_be_visible()

        card_box = card.bounding_box()
        tooltip_box = tooltip.bounding_box()

        assert card_box is not None, "Eligible Articles KPI card should have a bounding box"
        assert tooltip_box is not None, "Eligible Articles tooltip should have a bounding box"
        assert tooltip_box["y"] + tooltip_box["height"] > card_box["y"] + card_box["height"], (
            "Tooltip should extend beyond the KPI card bounds instead of being clipped inside the card"
        )

    @pytest.mark.ui
    def test_model_retraining_tooltip_renders_outside_panel(self, page: Page):
        """The Model Retraining help tooltip must not be clipped by the panel container."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        page.goto(f"{base_url}/ml-hunt-comparison")
        page.wait_for_load_state("load")

        panel = page.locator("#modelRetrainingPanel")
        help_button = page.locator("#modelRetrainingHelpButton")
        tooltip = page.locator("#modelRetrainingHelpTooltip")

        expect(panel).to_be_visible()
        expect(help_button).to_be_visible()

        help_button.hover()
        expect(tooltip).to_be_visible()

        panel_box = panel.bounding_box()
        tooltip_box = tooltip.bounding_box()

        assert panel_box is not None, "Model Retraining panel should have a bounding box"
        assert tooltip_box is not None, "Model Retraining tooltip should have a bounding box"
        assert tooltip_box["y"] + tooltip_box["height"] > panel_box["y"] + panel_box["height"], (
            "Model Retraining tooltip should extend beyond the panel bounds instead of being clipped"
        )

    @pytest.mark.ui
    def test_metrics_help_tooltip_stays_within_viewport(self, page: Page):
        """The chart metrics tooltip should open fully inside the viewport."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        page.goto(f"{base_url}/ml-hunt-comparison")
        page.wait_for_load_state("load")

        help_button = page.locator("#metricsHelpButton")
        tooltip = page.locator("#metricsHelpTooltip")

        expect(help_button).to_be_visible()

        help_button.click()
        expect(tooltip).to_be_visible()

        tooltip_box = tooltip.bounding_box()
        viewport = page.viewport_size

        assert viewport is not None, "Playwright viewport should be available"
        assert tooltip_box is not None, "Metrics tooltip should have a bounding box"
        assert tooltip_box["x"] >= 0, "Metrics tooltip should not extend off the left edge of the viewport"
        assert tooltip_box["x"] + tooltip_box["width"] <= viewport["width"], (
            "Metrics tooltip should stay within the viewport width"
        )

    @pytest.mark.ui
    def test_retrain_warning_tooltip_stays_within_viewport(self, page: Page):
        """The retrain warning tooltip should clamp to the viewport when shown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        page.goto(f"{base_url}/ml-hunt-comparison")
        page.wait_for_load_state("load")

        retrain_button = page.locator("#retrainModelBtn")
        expect(retrain_button).to_be_visible()

        page.evaluate("showRetrainHoverWarning()")

        tooltip = page.locator("#retrainTooltip")
        expect(tooltip).to_be_visible()

        tooltip_box = tooltip.bounding_box()
        viewport = page.viewport_size

        assert viewport is not None, "Playwright viewport should be available"
        assert tooltip_box is not None, "Retrain tooltip should have a bounding box"
        assert tooltip_box["x"] >= 0, "Retrain tooltip should not extend off the left edge"
        assert tooltip_box["x"] + tooltip_box["width"] <= viewport["width"], (
            "Retrain tooltip should stay within the viewport width"
        )
