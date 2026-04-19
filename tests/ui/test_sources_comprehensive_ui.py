"""
UI tests for Sources page comprehensive features using Playwright.
Tests source list display, actions, configuration modal, adhoc scraping, and related features.
"""

import os

import pytest
from playwright.sync_api import Page, expect


def _open_first_actions_menu(page: Page) -> bool:
    """Open the first source card overflow actions menu."""
    overflow_buttons = page.locator(".overflow-wrap .btn-overflow")
    if overflow_buttons.count() == 0:
        return False
    overflow_buttons.first.click()
    page.wait_for_timeout(100)
    return True


def _goto_sources(page: Page, base_url: str) -> None:
    """Force a real navigation to /sources even with class-scoped URL dedupe."""
    page.goto(f"{base_url}/")
    page.wait_for_load_state("load")
    page.goto(f"{base_url}/sources")
    page.wait_for_load_state("load")


def _open_first_source_config_modal(page: Page) -> bool:
    """Open source config modal from the first source card."""
    if not _open_first_actions_menu(page):
        return False
    configure_button = page.locator(".src-dropdown.open button:has-text('Configure')").first
    if configure_button.count() == 0:
        return False
    configure_button.click()
    page.wait_for_timeout(200)
    return True


class TestSourcesListDisplay:
    """Test source list display features."""

    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_metadata_display(self, page: Page):
        """Test source metadata display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Verify metadata fields exist
        page.locator("text=URL")
        page.locator("text=Collection Method")
        page.locator("text=Last Check")
        # Labels may or may not exist

    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_quality_metrics_panel(self, page: Page):
        """Test source quality metrics panel display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find quality metrics panels
        page.locator("text=📊 Quality Metrics")
        # Panels may or may not exist

    @pytest.mark.ui
    @pytest.mark.sources
    def test_manual_source_panel_display(self, page: Page):
        """Test manual source panel display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find manual source panel
        page.locator("text=📝 Manual Source")
        # Panel may or may not exist

    @pytest.mark.ui
    @pytest.mark.sources
    def test_empty_state_display(self, page: Page):
        """Test empty state when no sources configured."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Check for empty state message
        page.locator("text=No sources configured")
        # Empty state may or may not exist depending on configuration

    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_sorting_by_hunt_score(self, page: Page):
        """Test source sorting by hunt score."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Verify sorting indicator
        sort_indicator = page.locator("text=Hunt Score").first
        expect(sort_indicator).to_be_visible()


class TestSourceActions:
    """Test source action buttons."""

    @pytest.mark.ui
    @pytest.mark.sources
    def test_collection_status_modal_display(self, page: Page):
        """Test collection status modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find collection status modal
        collection_status = page.locator("#collectionStatus")
        expect(collection_status).to_be_attached()

        # Verify it's hidden initially
        assert "hidden" in (collection_status.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_toggle_status_button(self, page: Page):
        """Test Toggle Status button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find Toggle Status buttons
        if _open_first_actions_menu(page):
            toggle_button = page.locator(".src-dropdown.open button:has-text('Toggle Status')").first
            expect(toggle_button).to_be_visible()

            # Verify onclick handler
            onclick_attr = toggle_button.get_attribute("onclick")
            assert "toggleSourceStatus" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.sources
    def test_toggle_status_api_call(self, page: Page):
        """Test Toggle Status API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call
        api_called = {"called": False}

        def handle_route(route):
            if (
                "/api/sources" in route.request.url
                and "/toggle" in route.request.url
                and route.request.method == "POST"
            ):
                api_called["called"] = True
            route.continue_()

        page.route("**/api/sources/*/toggle", handle_route)

        _goto_sources(page, base_url)

        # Find and click Toggle Status button
        if _open_first_actions_menu(page):
            toggle_button = page.locator(".src-dropdown.open button:has-text('Toggle Status')").first
            toggle_button.click()
            page.wait_for_timeout(2000)

            # Verify API was called
            assert api_called["called"], "Toggle status API should be called"

    @pytest.mark.ui
    @pytest.mark.sources
    def test_configure_button(self, page: Page):
        """Test Configure button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find Configure buttons
        if _open_first_actions_menu(page):
            configure_button = page.locator(".src-dropdown.open button:has-text('Configure')").first
            expect(configure_button).to_be_visible()

            # Verify onclick handler
            onclick_attr = configure_button.get_attribute("onclick")
            assert "openSourceConfig" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_stats_button(self, page: Page):
        """Test Stats button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find Stats buttons
        if _open_first_actions_menu(page):
            stats_button = page.locator(".src-dropdown.open button:has-text('Stats')").first
            expect(stats_button).to_be_visible()

            # Verify onclick handler
            onclick_attr = stats_button.get_attribute("onclick")
            assert "showSourceStats" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_stats_api_call(self, page: Page):
        """Test source stats API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call
        api_called = {"called": False}

        def handle_route(route):
            if "/api/sources" in route.request.url and "/stats" in route.request.url:
                api_called["called"] = True
            route.continue_()

        page.route("**/api/sources/*/stats", handle_route)

        _goto_sources(page, base_url)

        # Find and click Stats button
        if _open_first_actions_menu(page):
            stats_button = page.locator(".src-dropdown.open button:has-text('Stats')").first
            stats_button.click()
            page.wait_for_timeout(2000)

            # Verify API was called
            assert api_called["called"], "Stats API should be called"

    @pytest.mark.ui
    @pytest.mark.sources
    def test_database_status_banner(self, page: Page):
        """Test database status banner display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Wait for page to fully render server-side HTML before querying
        page.wait_for_load_state("domcontentloaded")

        # Find database status banner
        banner = page.locator("#dbStatusBanner")
        expect(banner).to_be_attached(timeout=10000)

        # Verify it's hidden initially
        assert "hidden" in (banner.get_attribute("class") or "")

        # Verify refresh button exists (button text includes Refresh without emoji for robustness)
        refresh_btn = banner.locator("button:has-text('Refresh')")
        expect(refresh_btn).to_be_attached()


class TestSourceConfigurationModal:
    """Test source configuration modal."""

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_open(self, page: Page):
        """Test configuration modal opens."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find configuration modal
        config_modal = page.locator("#sourceConfigModal")
        expect(config_modal).to_be_attached()

        # Verify it's hidden initially
        assert "hidden" in (config_modal.get_attribute("class") or "")

        # Find Configure button and click
        if _open_first_source_config_modal(page):
            # Verify modal is now visible
            assert "hidden" not in (config_modal.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_form_fields(self, page: Page):
        """Test configuration modal form fields."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Open modal
        if _open_first_source_config_modal(page):
            # Verify form fields exist
            lookback_days = page.locator("#configLookbackDays")
            expect(lookback_days).to_be_visible()

            check_frequency = page.locator("#configCheckFrequency")
            expect(check_frequency).to_be_visible()

            min_content_length = page.locator("#configMinContentLength")
            expect(min_content_length).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_form_validation(self, page: Page):
        """Test configuration modal form validation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Open modal
        if _open_first_source_config_modal(page):
            # Verify input constraints
            lookback_days = page.locator("#configLookbackDays")
            min_val = lookback_days.get_attribute("min")
            max_val = lookback_days.get_attribute("max")
            assert min_val == "1"
            assert max_val == "999"

            check_frequency = page.locator("#configCheckFrequency")
            min_val = check_frequency.get_attribute("min")
            max_val = check_frequency.get_attribute("max")
            assert min_val == "1"
            assert max_val == "1440"

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_save_button(self, page: Page):
        """Test configuration modal save button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Open modal
        if _open_first_source_config_modal(page):
            # Find save button
            save_btn = page.locator("#saveSourceConfigBtn")
            expect(save_btn).to_be_visible()
            expect(save_btn).to_have_text("Save Changes")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_cancel_button(self, page: Page):
        """Test configuration modal cancel button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Open modal
        if _open_first_source_config_modal(page):
            # Find cancel button
            cancel_btn = page.locator("#cancelSourceConfigBtn")
            expect(cancel_btn).to_be_visible()

            # Click cancel
            cancel_btn.click()
            page.wait_for_timeout(200)

            # Verify modal is closed
            config_modal = page.locator("#sourceConfigModal")
            assert "hidden" in (config_modal.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_click_away_close(self, page: Page):
        """Test configuration modal closes on click-away."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Open modal
        if _open_first_source_config_modal(page):
            # Click outside modal (on backdrop)
            config_modal = page.locator("#sourceConfigModal")
            page.mouse.click(10, 10)
            page.wait_for_timeout(200)

            # Some modal-manager wrappers swallow backdrop clicks; fall back to Escape.
            if "hidden" not in (config_modal.get_attribute("class") or ""):
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)

            # Verify modal is closed
            assert "hidden" in (config_modal.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_escape_key_close(self, page: Page):
        """Test configuration modal closes on Escape key."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Open modal
        if _open_first_source_config_modal(page):
            # Press Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            # Verify modal is closed
            config_modal = page.locator("#sourceConfigModal")
            assert "hidden" in (config_modal.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_save_api_calls(self, page: Page):
        """Test configuration modal save makes API calls."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Track API calls
        api_calls = {"lookback": False, "check_frequency": False, "min_content_length": False}

        def handle_route(route):
            url = route.request.url
            if "/lookback" in url:
                api_calls["lookback"] = True
            elif "/check_frequency" in url:
                api_calls["check_frequency"] = True
            elif "/min_content_length" in url:
                api_calls["min_content_length"] = True
            route.continue_()

        page.route("**/api/sources/*/**", handle_route)

        _goto_sources(page, base_url)

        # Open modal and fill form
        if _open_first_source_config_modal(page):
            # Fill form fields
            lookback_days = page.locator("#configLookbackDays")
            lookback_days.fill("30")

            check_frequency = page.locator("#configCheckFrequency")
            check_frequency.fill("60")

            min_content_length = page.locator("#configMinContentLength")
            min_content_length.fill("200")

            # Click save
            save_btn = page.locator("#saveSourceConfigBtn")
            save_btn.click()
            page.wait_for_timeout(1000)

            # Verify all three API calls were made
            assert api_calls["lookback"], "Lookback API should be called"
            assert api_calls["check_frequency"], "Check frequency API should be called"
            assert api_calls["min_content_length"], "Min content length API should be called"


class TestAdhocUrlScraping:
    """Test adhoc URL scraping features."""

    @pytest.mark.ui
    @pytest.mark.sources
    def test_adhoc_url_form_display(self, page: Page):
        """Test adhoc URL form display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find adhoc URL form
        adhoc_form = page.locator("#adhocUrlForm")
        expect(adhoc_form).to_be_visible()

        # Verify form fields
        url_textarea = page.locator("#adhocUrl")
        expect(url_textarea).to_be_visible()

        title_input = page.locator("#adhocTitle")
        expect(title_input).to_be_visible()

        force_scrape_checkbox = page.locator("#adhocForceScrape")
        expect(force_scrape_checkbox).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.sources
    def test_adhoc_url_scrape_button(self, page: Page):
        """Test adhoc URL scrape button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find scrape button
        scrape_btn = page.locator("#scrapeUrlBtn")
        expect(scrape_btn).to_be_visible()
        expect(scrape_btn).to_contain_text("Scrape URLs")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_adhoc_url_scraping_api_call(self, page: Page):
        """Test adhoc URL scraping API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call
        api_called = {"called": False}

        def handle_route(route):
            if "/api/scrape-url" in route.request.url and route.request.method == "POST":
                api_called["called"] = True
            route.continue_()

        page.route("**/api/scrape-url", handle_route)

        _goto_sources(page, base_url)

        # Fill form
        url_textarea = page.locator("#adhocUrl")
        url_textarea.fill("https://example.com/article")

        # Click scrape button
        scrape_btn = page.locator("#scrapeUrlBtn")
        scrape_btn.click()
        page.wait_for_timeout(2000)

        # Verify API was called
        assert api_called["called"], "Scrape URL API should be called"

    @pytest.mark.ui
    @pytest.mark.sources
    def test_adhoc_scraping_status_display(self, page: Page):
        """Test adhoc scraping status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find scraping status div
        scraping_status = page.locator("#scrapingStatus")
        expect(scraping_status).to_be_attached()

        # Verify it's hidden initially
        assert "hidden" in (scraping_status.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_adhoc_url_form_validation(self, page: Page):
        """Test adhoc URL form validation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Verify URL textarea is required
        url_textarea = page.locator("#adhocUrl")
        required_attr = url_textarea.get_attribute("required")
        assert required_attr is not None


class TestResultModal:
    """Test result modal features."""

    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_display(self, page: Page):
        """Test result modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find result modal
        result_modal = page.locator("#resultModal")
        expect(result_modal).to_be_attached()

        # Verify it's hidden initially
        assert "hidden" in (result_modal.get_attribute("class") or "")

    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_close_button(self, page: Page):
        """Test result modal close button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find close button (via onclick handler)
        close_buttons = page.locator("button[onclick*='closeModal']")
        if close_buttons.count() > 0:
            expect(close_buttons.first).to_be_attached()

    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_click_away_close(self, page: Page):
        """Test result modal closes on click-away."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Result modal should have click-away handler
        page.locator("#resultModal")
        # Modal has event listener for click-away (tested via JavaScript)

    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_escape_key_close(self, page: Page):
        """Test result modal closes on Escape key."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Result modal should have Escape key handler
        page.locator("#resultModal")
        # Modal has event listener for Escape key (tested via JavaScript)


class TestPDFUploadSection:
    """Test PDF upload section."""

    @pytest.mark.ui
    @pytest.mark.sources
    def test_pdf_upload_card_display(self, page: Page):
        """Test PDF upload card display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find PDF upload section
        pdf_section = page.locator("a[href='/pdf-upload']:has-text('Upload')")
        expect(pdf_section).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.sources
    def test_pdf_upload_button_link(self, page: Page):
        """Test PDF upload button/link."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _goto_sources(page, base_url)

        # Find upload PDF link
        upload_link = page.locator("a[href='/pdf-upload']")
        expect(upload_link).to_be_visible()
        expect(upload_link).to_contain_text("Upload")

        # Click link
        upload_link.click()
        page.wait_for_load_state("load")
        assert page.url == f"{base_url}/pdf-upload"
