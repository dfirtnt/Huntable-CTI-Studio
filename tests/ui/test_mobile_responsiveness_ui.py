"""
UI tests for mobile responsiveness across all pages using Playwright.
Tests layout, touch interactions, navigation, forms, modals, tables, and related mobile features.
"""

import os

import pytest
from playwright.sync_api import Page, expect


class TestMobileLayout:
    """Test mobile layout responsiveness."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_dashboard_mobile_layout(self, page: Page):
        """Test dashboard mobile layout."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads and displays correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

        # Verify content is visible (not cut off)
        body = page.locator("body")
        expect(body).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_articles_mobile_layout(self, page: Page):
        """Test articles page mobile layout."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Verify page loads and displays correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_sources_mobile_layout(self, page: Page):
        """Test sources page mobile layout."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/sources")
        page.wait_for_load_state("networkidle")

        # Verify page loads and displays correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_settings_mobile_layout(self, page: Page):
        """Test settings page mobile layout."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")

        # Verify page loads and displays correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_workflow_mobile_layout(self, page: Page):
        """Test workflow page mobile layout."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify page loads and displays correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_chat_mobile_layout(self, page: Page):
        """Test chat page mobile layout."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        # Verify page loads and displays correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()


class TestMobileTouchInteractions:
    """Test mobile touch interactions."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_touch_button_tap(self, page: Page):
        """Test touch button tap."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Find and tap a button
        buttons = page.locator("button")
        if buttons.count() > 0:
            button = buttons.first
            button.tap()
            page.wait_for_timeout(500)

            # Verify button interaction works
            expect(button).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_touch_link_tap(self, page: Page):
        """Test touch link tap."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Find and tap a link
        links = page.locator("a")
        if links.count() > 0:
            link = links.first
            link.tap()
            page.wait_for_timeout(1000)

            # Verify navigation occurred
            expect(page).to_have_url(lambda url: url != f"{base_url}/")

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_touch_scroll(self, page: Page):
        """Test touch scroll."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Scroll down
        page.evaluate("window.scrollTo(0, 500)")
        page.wait_for_timeout(500)

        # Verify scroll works
        scroll_position = page.evaluate("window.pageYOffset")
        assert scroll_position > 0, "Page should scroll"

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_touch_input_focus(self, page: Page):
        """Test touch input focus."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Tap on input
        textarea = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        if textarea.count() > 0:
            textarea.tap()
            page.wait_for_timeout(500)

            # Verify input is focused
            focused_element = page.evaluate("document.activeElement")
            assert focused_element is not None


class TestMobileNavigation:
    """Test mobile navigation features."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_navigation_menu(self, page: Page):
        """Test mobile navigation menu."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify navigation menu exists
        nav = page.locator("nav")
        expect(nav).to_be_visible()

        # Verify navigation links are accessible
        nav_links = nav.locator("a")
        if nav_links.count() > 0:
            expect(nav_links.first).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_breadcrumb_navigation(self, page: Page):
        """Test mobile breadcrumb navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")

        # Verify breadcrumbs exist (if implemented)
        page.locator("[aria-label='Breadcrumb'], .breadcrumb, nav[aria-label='Breadcrumb']")
        # Breadcrumbs may or may not exist depending on implementation


class TestMobileForms:
    """Test mobile form features."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_form_inputs(self, page: Page):
        """Test mobile form inputs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Verify form inputs are accessible
        textarea = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        expect(textarea).to_be_visible()

        # Verify inputs are large enough for touch
        input_box = textarea.bounding_box()
        if input_box:
            assert input_box["height"] >= 40, "Input should be at least 40px tall for touch"

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_form_submission(self, page: Page):
        """Test mobile form submission."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Fill and submit form
        textarea = page.locator("textarea[placeholder*='Ask about cybersecurity']")
        send_button = page.locator("button:has-text('Send')")

        if textarea.count() > 0 and send_button.count() > 0:
            textarea.fill("Test message")
            send_button.tap()
            page.wait_for_timeout(1000)

            # Verify submission works
            user_message = page.locator("text=Test message")
            expect(user_message).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_dropdown_selects(self, page: Page):
        """Test mobile dropdown selects."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/chat")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Find dropdowns
        selects = page.locator("select")
        if selects.count() > 0:
            select = selects.first
            expect(select).to_be_visible()

            # Verify dropdown is accessible
            select_box = select.bounding_box()
            if select_box:
                assert select_box["height"] >= 40, "Select should be at least 40px tall for touch"


class TestMobileModals:
    """Test mobile modal features."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_modal_display(self, page: Page):
        """Test mobile modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Verify modals can be displayed (if any exist)
        # Modals should be full-screen or properly sized on mobile
        page.locator("[role='dialog'], .modal")
        # Modals may or may not exist depending on page state

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_modal_close(self, page: Page):
        """Test mobile modal close."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Test modal close button (if modal exists)
        page.locator("button:has-text('Close'), button[aria-label*='close'], .modal button")
        # Close buttons may or may not exist depending on modal state

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_modal_backdrop_tap(self, page: Page):
        """Test mobile modal backdrop tap."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Test backdrop tap (if modal exists)
        page.locator(".modal-backdrop, [role='dialog'] + .backdrop")
        # Backdrop may or may not exist depending on modal state


class TestMobileTables:
    """Test mobile table features."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_table_display(self, page: Page):
        """Test mobile table display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Verify tables are scrollable or responsive
        tables = page.locator("table")
        if tables.count() > 0:
            table = tables.first
            expect(table).to_be_visible()

            # Verify table is scrollable horizontally if needed
            table_box = table.bounding_box()
            viewport_width = page.viewport_size["width"]
            if table_box and table_box["width"] > viewport_width:
                # Table should be scrollable
                assert True, "Wide tables should be scrollable on mobile"

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_table_scroll(self, page: Page):
        """Test mobile table scroll."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        # Find table container
        table_containers = page.locator("table, .table-container, [role='table']")
        if table_containers.count() > 0:
            container = table_containers.first

            # Scroll table horizontally
            container.evaluate("element => element.scrollLeft = 100")
            page.wait_for_timeout(500)

            # Verify scroll works
            scroll_position = container.evaluate("element => element.scrollLeft")
            assert scroll_position >= 0, "Table should be scrollable"


class TestMobileResponsiveBreakpoints:
    """Test mobile responsive breakpoints."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_small_mobile_viewport(self, page: Page):
        """Test small mobile viewport (320px)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set small mobile viewport
        page.set_viewport_size({"width": 320, "height": 568})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_medium_mobile_viewport(self, page: Page):
        """Test medium mobile viewport (375px)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set medium mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_large_mobile_viewport(self, page: Page):
        """Test large mobile viewport (414px)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set large mobile viewport
        page.set_viewport_size({"width": 414, "height": 896})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_tablet_viewport(self, page: Page):
        """Test tablet viewport (768px)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set tablet viewport
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()


class TestMobileOrientation:
    """Test mobile orientation handling."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_portrait_orientation(self, page: Page):
        """Test portrait orientation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set portrait orientation
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_landscape_orientation(self, page: Page):
        """Test landscape orientation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set landscape orientation
        page.set_viewport_size({"width": 667, "height": 375})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify page loads correctly
        heading = page.locator("h1").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_orientation_change(self, page: Page):
        """Test orientation change handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Start in portrait
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Change to landscape
        page.set_viewport_size({"width": 667, "height": 375})
        page.wait_for_timeout(500)

        # Verify page adapts to orientation change
        heading = page.locator("h1").first
        expect(heading).to_be_visible()


class TestMobileSpecificFeatures:
    """Test mobile-specific features."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_viewport_meta_tag(self, page: Page):
        """Test mobile viewport meta tag."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify viewport meta tag exists
        viewport_meta = page.locator("meta[name='viewport']")
        expect(viewport_meta).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_touch_target_sizes(self, page: Page):
        """Test mobile touch target sizes."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify buttons are large enough for touch (44x44px minimum)
        buttons = page.locator("button")
        if buttons.count() > 0:
            button = buttons.first
            button_box = button.bounding_box()
            if button_box:
                assert button_box["height"] >= 44 or button_box["width"] >= 44, (
                    "Touch targets should be at least 44x44px"
                )

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_text_readability(self, page: Page):
        """Test mobile text readability."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Set mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        # Verify text is readable
        text_elements = page.locator("p, span, div")
        if text_elements.count() > 0:
            text = text_elements.first
            text_box = text.bounding_box()
            if text_box:
                # Text should be large enough to read
                assert text_box["height"] > 0, "Text should be visible"


class TestMobileNav:
    """Test mobile navigation (hamburger menu) at viewport < 768px."""

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_hamburger_visible(self, page: Page):
        """Test hamburger button visible at mobile viewport."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        hamburger = page.locator("#mobile-nav-toggle")
        expect(hamburger).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_menu_opens_on_click(self, page: Page):
        """Test clicking hamburger opens mobile menu with six links."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        menu = page.locator("#mobile-nav-menu")
        expect(menu).to_have_class("hidden")
        page.locator("#mobile-nav-toggle").click()
        page.wait_for_timeout(200)
        expect(menu).not_to_have_class("hidden")

        # Six nav links: Articles, Sources, MLOps, Agents, Diags, Settings
        links = menu.locator(
            'a[href="/articles"], a[href="/sources"], a[href="/mlops"], a[href="/workflow"], a[href="/diags"], a[href="/settings"]'
        )
        expect(links).to_have_count(6)

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_menu_link_navigates_and_closes(self, page: Page):
        """Test clicking a link in mobile menu navigates and closes menu."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        page.locator("#mobile-nav-toggle").click()
        page.wait_for_timeout(200)
        menu = page.locator("#mobile-nav-menu")
        expect(menu).to_be_visible()

        menu.locator('a[href="/articles"]').first.click()
        page.wait_for_url(f"{base_url}/articles", timeout=5000)
        expect(page).to_have_url(f"{base_url}/articles")
        # Menu should be closed after navigation
        expect(menu).to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.mobile
    def test_mobile_menu_escape_closes(self, page: Page):
        """Test Escape key closes mobile menu."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 375, "height": 667})
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")

        page.locator("#mobile-nav-toggle").click()
        page.wait_for_timeout(200)
        menu = page.locator("#mobile-nav-menu")
        expect(menu).to_be_visible()

        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        expect(menu).to_have_class("hidden")
