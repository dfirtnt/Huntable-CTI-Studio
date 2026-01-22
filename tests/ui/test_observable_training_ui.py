"""
Playwright smoke tests for the observable training dashboard.

DEPRECATED: HuggingFace connections/API keys and training are no longer used.
These tests are deprecated and will be removed in a future release.
"""

import os
import pytest
from playwright.sync_api import Page, expect


class TestObservableTrainingUI:
    """UI tests for /observables-training.
    
    DEPRECATED: Training functionality is no longer used.
    """

    @pytest.mark.ui
    @pytest.mark.skip(reason="DEPRECATED: Training functionality no longer used")
    def test_observable_training_page_loads(self, page: Page):
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/observables-training")
        page.wait_for_load_state("networkidle")

        # Verify inactive notice is present
        inactive_notice = page.locator("text=Feature Inactive - Planned for Future Release")
        expect(inactive_notice).to_be_visible()
        
        # Original heading should still be present
        heading = page.locator("text=Observable Extractor Training")
        expect(heading).to_be_visible()
