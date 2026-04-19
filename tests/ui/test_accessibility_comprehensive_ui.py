"""
UI tests for accessibility features using Playwright.
Tests ARIA labels, keyboard navigation, heading hierarchy, and landmark roles.

Pruned from 24 tests to 6 -- removed tests that asserted trivially-true
conditions (document.activeElement is not None) or located elements without
asserting on them.
"""

import os

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.accessibility
@pytest.mark.slow
class TestARIALabels:
    """Test ARIA labels on specific elements."""

    def test_nav_has_main_aria_label(self, page: Page):
        """Main nav has aria-label for screen readers."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")
        nav = page.locator('nav[aria-label="Main navigation"]')
        expect(nav).to_be_visible()

    def test_articles_search_help_aria_label(self, page: Page):
        """Articles search syntax help button has aria-label."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        filters_toggle = page.locator("#filters-toggle").or_(page.locator("[data-collapsible-panel='filters']"))
        if filters_toggle.count() > 0:
            filters_toggle.first.click()
        help_btn = page.locator('button[aria-label="Search syntax help"]')
        if help_btn.count() > 0:
            help_btn.first.wait_for(state="visible", timeout=5000)
            expect(help_btn.first).to_be_visible()

    def test_button_accessibility(self, page: Page):
        """Buttons have text content or aria-label (spot-check first 5)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        buttons = page.locator("button")
        button_count = buttons.count()

        if button_count > 0:
            for i in range(min(5, button_count)):
                button = buttons.nth(i)
                button_text = button.text_content()
                aria_label = button.get_attribute("aria-label")
                assert button_text or aria_label, f"Button {i} should have text or aria-label"


@pytest.mark.ui
@pytest.mark.accessibility
@pytest.mark.slow
class TestStructure:
    """Test document structure for screen readers."""

    def test_heading_hierarchy(self, page: Page):
        """Page has at least one h1 heading."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        h1 = page.locator("h1").first
        expect(h1).to_be_visible()

        h1_count = page.locator("h1").count()
        assert h1_count > 0, "Page should have at least one h1 heading"

    def test_navigation_landmark(self, page: Page):
        """Navigation landmark exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        nav = page.locator("nav, [role='navigation']")
        expect(nav).to_be_visible()

    def test_images_have_alt_text(self, page: Page):
        """Images have alt attribute (spot-check first 5)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("load")

        images = page.locator("img")
        image_count = images.count()

        if image_count > 0:
            for i in range(min(5, image_count)):
                img = images.nth(i)
                alt = img.get_attribute("alt")
                assert alt is not None, f"Image {i} should have alt attribute"
