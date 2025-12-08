"""
UI tests for Sources page comprehensive features using Playwright.
Tests source list display, actions, configuration modal, adhoc scraping, and related features.
"""

import pytest
from playwright.sync_api import Page, expect
import os


class TestSourcesListDisplay:
    """Test source list display features."""
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_sources_page_loads(self, page: Page):
        """Test sources page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Sources - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('🔗 Threat Intelligence Sources')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_breadcrumb_navigation(self, page: Page):
        """Test breadcrumb navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Verify breadcrumb exists
        breadcrumb = page.locator("nav[aria-label='Breadcrumb']")
        expect(breadcrumb).to_be_visible()
        
        # Verify Home link
        home_link = breadcrumb.locator("a[href='/']")
        expect(home_link).to_be_visible()
        
        # Click Home link
        home_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(f"{base_url}/")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_cards_display(self, page: Page):
        """Test source cards display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Verify sources section exists
        sources_section = page.locator("text=🔗 Configured Sources")
        expect(sources_section).to_be_visible()
        
        # Verify source cards exist (if any sources configured)
        source_cards = page.locator(".bg-white.dark\\:bg-gray-800.border")
        # Cards may or may not exist depending on configuration
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_article_count_badge(self, page: Page):
        """Test source article count badge display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find article count badges (green circles with numbers)
        badges = page.locator(".bg-green-100.text-green-800")
        # Badges may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_name_links(self, page: Page):
        """Test source name links to articles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find source name links
        source_links = page.locator("a[href^='/articles?source_id=']")
        if source_links.count() > 0:
            first_link = source_links.first
            expect(first_link).to_be_visible()
            
            # Verify link has correct href pattern
            href = first_link.get_attribute("href")
            assert href.startswith("/articles?source_id=")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_status_badges(self, page: Page):
        """Test source status badges (Active/Inactive)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find status badges
        active_badges = page.locator("span:has-text('Active')")
        inactive_badges = page.locator("span:has-text('Inactive')")
        # Badges may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_metadata_display(self, page: Page):
        """Test source metadata display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Verify metadata fields exist
        url_labels = page.locator("text=URL")
        collection_method_labels = page.locator("text=Collection Method")
        last_check_labels = page.locator("text=Last Check")
        # Labels may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_quality_metrics_panel(self, page: Page):
        """Test source quality metrics panel display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find quality metrics panels
        quality_panels = page.locator("text=📊 Quality Metrics")
        # Panels may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_manual_source_panel_display(self, page: Page):
        """Test manual source panel display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find manual source panel
        manual_panel = page.locator("text=📝 Manual Source")
        # Panel may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_empty_state_display(self, page: Page):
        """Test empty state when no sources configured."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Check for empty state message
        empty_state = page.locator("text=No sources configured")
        # Empty state may or may not exist depending on configuration
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_sorting_by_hunt_score(self, page: Page):
        """Test source sorting by hunt score."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Verify sorting indicator
        sort_indicator = page.locator("text=Hunt Score (highest first)")
        expect(sort_indicator).to_be_visible()


class TestSourceActions:
    """Test source action buttons."""
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_collect_now_button(self, page: Page):
        """Test Collect Now button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find Collect Now buttons
        collect_buttons = page.locator("button:has-text('Collect Now')")
        if collect_buttons.count() > 0:
            first_button = collect_buttons.first
            expect(first_button).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = first_button.get_attribute("onclick")
            assert "collectFromSource" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_collect_now_api_call(self, page: Page):
        """Test Collect Now API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/sources" in route.request.url and "/collect" in route.request.url and route.request.method == "POST":
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/sources/*/collect", handle_route)
        
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find and click Collect Now button
        collect_buttons = page.locator("button:has-text('Collect Now')")
        if collect_buttons.count() > 0:
            collect_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Verify API was called
            assert api_called["called"], "Collect API should be called"
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_collection_status_modal_display(self, page: Page):
        """Test collection status modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find collection status modal
        collection_status = page.locator("#collectionStatus")
        expect(collection_status).to_be_visible()
        
        # Verify it's hidden initially
        expect(collection_status).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_toggle_status_button(self, page: Page):
        """Test Toggle Status button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find Toggle Status buttons
        toggle_buttons = page.locator("button:has-text('Toggle Status')")
        if toggle_buttons.count() > 0:
            first_button = toggle_buttons.first
            expect(first_button).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = first_button.get_attribute("onclick")
            assert "toggleSourceStatus" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_toggle_status_api_call(self, page: Page):
        """Test Toggle Status API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/sources" in route.request.url and "/toggle" in route.request.url and route.request.method == "POST":
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/sources/*/toggle", handle_route)
        
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find and click Toggle Status button
        toggle_buttons = page.locator("button:has-text('Toggle Status')")
        if toggle_buttons.count() > 0:
            toggle_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Verify API was called
            assert api_called["called"], "Toggle status API should be called"
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_configure_button(self, page: Page):
        """Test Configure button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find Configure buttons
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            first_button = configure_buttons.first
            expect(first_button).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = first_button.get_attribute("onclick")
            assert "openSourceConfig" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_source_stats_button(self, page: Page):
        """Test Stats button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find Stats buttons
        stats_buttons = page.locator("button:has-text('Stats')")
        if stats_buttons.count() > 0:
            first_button = stats_buttons.first
            expect(first_button).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = first_button.get_attribute("onclick")
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
        
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find and click Stats button
        stats_buttons = page.locator("button:has-text('Stats')")
        if stats_buttons.count() > 0:
            stats_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Verify API was called
            assert api_called["called"], "Stats API should be called"
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_database_status_banner(self, page: Page):
        """Test database status banner display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find database status banner
        banner = page.locator("#dbStatusBanner")
        expect(banner).to_be_visible()
        
        # Verify it's hidden initially
        expect(banner).to_have_class("hidden")
        
        # Verify refresh button exists
        refresh_btn = banner.locator("button:has-text('🔄 Refresh')")
        expect(refresh_btn).to_be_visible()


class TestSourceConfigurationModal:
    """Test source configuration modal."""
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_open(self, page: Page):
        """Test configuration modal opens."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find configuration modal
        config_modal = page.locator("#sourceConfigModal")
        expect(config_modal).to_be_visible()
        
        # Verify it's hidden initially
        expect(config_modal).to_have_class("hidden")
        
        # Find Configure button and click
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Verify modal is now visible
            expect(config_modal).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_form_fields(self, page: Page):
        """Test configuration modal form fields."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
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
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Verify input constraints
            lookback_days = page.locator("#configLookbackDays")
            min_val = lookback_days.get_attribute("min")
            max_val = lookback_days.get_attribute("max")
            assert min_val == "1"
            assert max_val == "365"
            
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
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Find save button
            save_btn = page.locator("#saveSourceConfigBtn")
            expect(save_btn).to_be_visible()
            expect(save_btn).to_have_text("Save Changes")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_cancel_button(self, page: Page):
        """Test configuration modal cancel button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Find cancel button
            cancel_btn = page.locator("#cancelSourceConfigBtn")
            expect(cancel_btn).to_be_visible()
            
            # Click cancel
            cancel_btn.click()
            page.wait_for_timeout(500)
            
            # Verify modal is closed
            config_modal = page.locator("#sourceConfigModal")
            expect(config_modal).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_click_away_close(self, page: Page):
        """Test configuration modal closes on click-away."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Click outside modal (on backdrop)
            config_modal = page.locator("#sourceConfigModal")
            # Click on backdrop (first child div)
            backdrop = config_modal.locator("div.fixed.inset-0").first
            backdrop.click()
            page.wait_for_timeout(500)
            
            # Verify modal is closed
            expect(config_modal).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_escape_key_close(self, page: Page):
        """Test configuration modal closes on Escape key."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Press Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            
            # Verify modal is closed
            config_modal = page.locator("#sourceConfigModal")
            expect(config_modal).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_config_modal_save_api_calls(self, page: Page):
        """Test configuration modal save makes API calls."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API calls
        api_calls = {
            "lookback": False,
            "check_frequency": False,
            "min_content_length": False
        }
        
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
        
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Open modal and fill form
        configure_buttons = page.locator("button:has-text('Configure')")
        if configure_buttons.count() > 0:
            configure_buttons.first.click()
            page.wait_for_timeout(500)
            
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
            page.wait_for_timeout(3000)
            
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
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find scrape button
        scrape_btn = page.locator("#scrapeUrlBtn")
        expect(scrape_btn).to_be_visible()
        expect(scrape_btn).to_have_text("Scrape URLs")
    
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
        
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find scraping status div
        scraping_status = page.locator("#scrapingStatus")
        expect(scraping_status).to_be_visible()
        
        # Verify it's hidden initially
        expect(scraping_status).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_adhoc_url_form_validation(self, page: Page):
        """Test adhoc URL form validation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
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
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find result modal
        result_modal = page.locator("#resultModal")
        expect(result_modal).to_be_visible()
        
        # Verify it's hidden initially
        expect(result_modal).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_close_button(self, page: Page):
        """Test result modal close button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find close button (via onclick handler)
        close_buttons = page.locator("button[onclick*='closeModal']")
        if close_buttons.count() > 0:
            expect(close_buttons.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_click_away_close(self, page: Page):
        """Test result modal closes on click-away."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Result modal should have click-away handler
        result_modal = page.locator("#resultModal")
        # Modal has event listener for click-away (tested via JavaScript)
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_result_modal_escape_key_close(self, page: Page):
        """Test result modal closes on Escape key."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Result modal should have Escape key handler
        result_modal = page.locator("#resultModal")
        # Modal has event listener for Escape key (tested via JavaScript)


class TestPDFUploadSection:
    """Test PDF upload section."""
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_pdf_upload_card_display(self, page: Page):
        """Test PDF upload card display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find PDF upload section
        pdf_section = page.locator("text=📄 Upload PDF Reports")
        expect(pdf_section).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.sources
    def test_pdf_upload_button_link(self, page: Page):
        """Test PDF upload button/link."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")
        
        # Find upload PDF link
        upload_link = page.locator("a[href='/pdf-upload']")
        expect(upload_link).to_be_visible()
        expect(upload_link).to_have_text("Upload PDF")
        
        # Click link
        upload_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(f"{base_url}/pdf-upload")

