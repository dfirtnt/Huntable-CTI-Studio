"""
Playwright smoke tests for the observable training dashboard.
"""

import os
import pytest
from playwright.sync_api import Page, expect


class TestObservableTrainingUI:
    """UI tests for /observables-training."""

    @pytest.mark.ui
    def test_observable_training_page_loads(self, page: Page):
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/observables-training")
        page.wait_for_load_state("networkidle")

        heading = page.locator("text=Observable Extractor Training")
        expect(heading).to_be_visible()
