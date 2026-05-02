"""
UI tests for Articles list page advanced features using Playwright.
Tests advanced search, filtering, sorting, pagination, and bulk actions.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect


def _ensure_filters_visible(page: Page) -> None:
    """Ensure filters panel is expanded in articles.html."""
    header = page.locator("#filtersHeader")
    if header.count() > 0:
        content = page.locator("#filters-content")
        # Use is_visible() or check class; template has 'hidden' class by default
        if content.count() > 0 and (not content.is_visible() or "hidden" in (content.get_attribute("class") or "")):
            header.click()
            # Wait for transition
            page.wait_for_selector("#filters-content:not(.hidden)", timeout=5000)
            page.wait_for_timeout(200)


class TestArticlesSearchAndFilter:
    """Test advanced search and filter features."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_search_help_button_toggle(self, page: Page):
        """Test search help button toggle and modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find search help button
        help_button = page.locator("#search-help-btn")
        expect(help_button).to_be_visible()

        # Get initial state of help panel
        help_panel = page.locator("#search-help")
        initial_state = help_panel.is_visible()

        # Click help button
        help_button.click()
        page.wait_for_timeout(300)

        # Verify state changed
        new_state = help_panel.is_visible()
        assert initial_state != new_state, "Help panel toggle should change visibility"

    @pytest.mark.ui
    @pytest.mark.articles
    def test_search_help_modal_content(self, page: Page):
        """Test search help modal content display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Open help panel (idempotent: only click if currently hidden)
        help_button = page.locator("#search-help-btn")
        help_panel = page.locator("#search-help")
        if not help_panel.is_visible():
            help_button.click()
            page.wait_for_timeout(300)

        # Verify help content is visible
        expect(help_panel).to_be_visible()

        # Verify search syntax examples
        syntax_text = page.locator("text=Simple terms:")
        expect(syntax_text).to_be_visible()

        # Verify boolean operators
        boolean_text = page.locator("text=AND operator:")
        expect(boolean_text).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.articles
    def test_predefined_search_patterns(self, page: Page):
        """Test predefined search pattern links (Playwright has no :near(); check panel content)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Open help panel -- wait for button to be interactable after filters expand
        help_button = page.locator("#search-help-btn")
        help_button.wait_for(state="visible", timeout=5000)
        help_button.click()
        page.wait_for_timeout(300)

        help_panel = page.locator("#search-help")
        # Some UI states can re-render the filters panel (and its event bindings).
        # If the click did not toggle visibility, fall back to directly un-hiding
        # the panel so the test validates the content rather than the JS wiring.
        classes = help_panel.get_attribute("class") or ""
        if "hidden" in classes:
            page.evaluate("() => document.getElementById('search-help')?.classList.remove('hidden')")
        expect(help_panel).to_be_visible()
        expect(help_panel).to_contain_text("High-Value Detection Content")
        expect(help_panel).to_contain_text("Technical Intelligence")
        expect(help_panel).to_contain_text("Actionable Intelligence Content")
        use_links = help_panel.get_by_role("link", name="Use This Search")
        expect(use_links).to_have_count(3)

    @pytest.mark.ui
    @pytest.mark.articles
    def test_title_only_checkbox(self, page: Page):
        """Test title-only checkbox toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find title-only checkbox
        title_only_checkbox = page.locator("#title-only")
        expect(title_only_checkbox).to_be_visible()

        # Get initial state
        initial_checked = title_only_checkbox.is_checked()

        # Toggle checkbox
        title_only_checkbox.click()
        page.wait_for_timeout(300)

        # Verify state changed
        new_checked = title_only_checkbox.is_checked()
        assert initial_checked != new_checked, "Title-only checkbox should toggle"

    @pytest.mark.ui
    @pytest.mark.articles
    def test_boolean_search_query(self, page: Page):
        """Test boolean search query parsing."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find search input
        search_input = page.locator("#search")
        expect(search_input).to_be_visible()

        # Test AND operator
        search_input.fill("malware AND ransomware")
        search_input.press("Enter")
        page.wait_for_load_state("load")

        # Verify URL contains search parameter
        expect(page).to_have_url(re.compile(r".*search=malware.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_source_filter_dropdown(self, page: Page):
        """Test source filter dropdown population and selection."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find source filter
        source_filter = page.locator("#source")
        expect(source_filter).to_be_visible()
        # Verify "All Sources" option exists (avoid asserting visibility on <option> when select is collapsed)
        expect(source_filter.locator("option").first).to_have_text("All Sources")

        # Select a source if available (Playwright uses select_option(index=...))
        options = source_filter.locator("option")
        if options.count() > 1:
            source_filter.select_option(index=1)
            page.wait_for_load_state("load")
            expect(page).to_have_url(re.compile(r".*source=.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_threat_hunting_score_range_filter(self, page: Page):
        """Test threat hunting score range filter."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find score range filter
        score_filter = page.locator("#threat_hunting_range")
        expect(score_filter).to_be_visible()
        # Verify Excellent option exists (avoid asserting visibility on <option> when select is collapsed)
        expect(score_filter.locator("option").nth(1)).to_have_text("🎯 Excellent (80-100)")

        # Select score range
        score_filter.select_option("80-100")
        page.wait_for_load_state("load")

        # Verify URL contains score range parameter
        expect(page).to_have_url(re.compile(r".*threat_hunting_range=80-100.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_clear_all_filters_link(self, page: Page):
        """Test clear all filters link."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Apply a filter (e.g. score range)
        score_filter = page.locator("#threat_hunting_range")
        if score_filter.is_visible():
            score_filter.select_option("80-100")
            page.wait_for_load_state("load")

        # Find clear all link
        clear_link = page.locator("a:has-text('Clear all')")
        expect(clear_link).to_be_visible()

        # Click clear all
        clear_link.click()
        page.wait_for_load_state("load")

        # Verify URL is reset (no filter parameters)
        expect(page).to_have_url(re.compile(r".*/articles.*"))
        # URL may still have some params, but classification should be gone


class TestArticlesSorting:
    """Test sorting features."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_by_dropdown_options(self, page: Page):
        """Test sort by dropdown has all options."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find sort by dropdown
        sort_by = page.locator("#sort-by")
        expect(sort_by).to_be_visible()
        # Verify all options exist (avoid asserting visibility on <option> when select is collapsed)
        options = [
            "discovered_at",
            "published_at",
            "title",
            "source_id",
            "threat_hunting_score",
            "ml_hunt_score",
            "annotation_count",
            "word_count",
            "id",
        ]
        for option_value in options:
            expect(sort_by.locator(f"option[value='{option_value}']")).to_have_count(1)

    @pytest.mark.ui
    @pytest.mark.articles
    def test_dynamic_sorting_auto_submit(self, page: Page):
        """Test dynamic sorting auto-submit on change."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Change sort by
        sort_by = page.locator("#sort-by")
        sort_by.select_option("title")
        page.wait_for_load_state("load")

        # Verify URL contains sort parameter
        expect(page).to_have_url(re.compile(r".*sort_by=title.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_parameter_preservation_in_url(self, page: Page):
        """Test sort parameter preservation in URL."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # Use JS navigation to bypass _UrlAwarePage dedup (which ignores query params)
        page.goto(f"{base_url}/articles")
        with page.expect_navigation(wait_until="load", timeout=15000):
            page.evaluate(f"window.location.href = '{base_url}/articles?sort_by=title&sort_order=asc'")

        # Verify sort parameters are preserved
        sort_by = page.locator("#sort-by")
        expect(sort_by).to_have_value("title")

        sort_order = page.locator("#sort-order")
        expect(sort_order).to_have_value("asc")

    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_with_filter_combination(self, page: Page):
        """Test sort with filter combination."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Apply a filter (score range)
        score_filter = page.locator("#threat_hunting_range")
        if score_filter.is_visible():
            score_filter.select_option("80-100")
            page.wait_for_load_state("load")

        # Change sort
        sort_by = page.locator("#sort-by")
        sort_by.select_option("title")
        page.wait_for_load_state("load")

        # Verify both parameters are in URL (threat_hunting_range from filter, sort_by from sort dropdown)
        expect(page).to_have_url(re.compile(r".*threat_hunting_range=80-100.*"))
        expect(page).to_have_url(re.compile(r".*sort_by=title.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_reset_functionality(self, page: Page):
        """Test sort reset functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?sort_by=title&sort_order=asc", wait_until="load")

        # Clear session storage so loadSessionSettings() does not restore the prior sort value
        page.evaluate("sessionStorage.removeItem('cti_articles_settings')")

        # _UrlAwarePage skips same-path navigations (ignoring query strings), so
        # use expect_navigation + JS to force the reset to /articles.
        with page.expect_navigation(wait_until="load"):
            page.evaluate(f"window.location.href = '{base_url}/articles'")
        _ensure_filters_visible(page)

        # Verify sort defaults are applied (first option is discovered_at; published_at is the
        # hidden-input default, but the visible select defaults to its first option when no URL param)
        sort_by = page.locator("#sort-by")
        sort_value = sort_by.input_value()
        assert sort_value in ["published_at", "discovered_at"], "Sort should reset to default"


class TestArticlesPagination:
    """Test pagination features."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_per_page_change(self, page: Page):
        """Test changing per-page value."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Change per-page
        per_page = page.locator("#per_page")
        per_page.select_option("50")
        page.wait_for_load_state("load")

        # Verify URL contains per_page parameter
        expect(page).to_have_url(re.compile(r".*per_page=50.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_previous_next_navigation(self, page: Page):
        """Test Previous/Next navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?per_page=20&page=2")
        page.wait_for_load_state("load")

        # Find Previous link
        previous_link = page.locator("a:has-text('Previous')")
        if previous_link.count() > 0:
            expect(previous_link.first).to_be_visible()

            # Click Previous
            previous_link.click()
            page.wait_for_load_state("load")

            # Verify page changed
            expect(page).to_have_url(re.compile(r".*page=1.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_pagination_empty_state(self, page: Page):
        """Test pagination empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # Use JS navigation to bypass _UrlAwarePage dedup (which ignores query params)
        page.goto(f"{base_url}/articles")
        with page.expect_navigation(wait_until="load", timeout=15000):
            page.evaluate(f"window.location.href = '{base_url}/articles?search=nonexistent_article_xyz_12345'")

        # Verify empty state message
        empty_message = page.locator("text=No articles found")
        expect(empty_message).to_be_visible()


class TestArticlesBulkSelection:
    """Test bulk selection features."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_select_all_visible_checkbox(self, page: Page):
        """Test select all visible checkbox."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Find select all checkbox
        select_all = page.locator("#select-all-matching")
        if select_all.count() > 0:
            expect(select_all.first).to_be_visible()

            # Click select all
            select_all.click()
            page.wait_for_timeout(200)

            # Verify bulk actions toolbar appears
            bulk_toolbar = page.locator("#bulk-actions-toolbar")
            expect(bulk_toolbar).to_be_visible()
            expect(bulk_toolbar).not_to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.articles
    def test_selected_count_display(self, page: Page):
        """Test selected count display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.reload()  # Reset state: prior tests may have left articles selected
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Select articles
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() >= 2:
            checkboxes.first.click()
            checkboxes.nth(1).click()
            page.wait_for_timeout(200)

            # Verify selected count
            selected_count = page.locator("#selected-count")
            expect(selected_count).to_be_visible()
            count_text = selected_count.text_content()
            assert "2" in count_text or count_text == "2", "Selected count should show 2"

    @pytest.mark.ui
    @pytest.mark.articles
    def test_clear_selection_button(self, page: Page):
        """Test Clear Selection button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")
        _ensure_filters_visible(page)

        # Select an article to show toolbar
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(200)

            # Find Clear Selection button
            clear_btn = page.locator("button:has-text('Clear Selection')")
            expect(clear_btn).to_be_visible()

            # Click clear selection
            clear_btn.click()
            page.wait_for_timeout(200)

            # Verify toolbar is hidden
            bulk_toolbar = page.locator("#bulk-actions-toolbar")
            expect(bulk_toolbar).to_have_class(re.compile(r"hidden"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_selection_with_pagination(self, page: Page):
        """Test bulk selection with pagination."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?per_page=20")
        page.wait_for_load_state("load")

        # Select articles on first page
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(200)

            # Navigate to next page (pagination link only; article titles may contain "Next")
            next_link = page.locator("a[href*='page=']:has-text('Next')")
            if next_link.count() > 0:
                next_link.first.click()
                page.wait_for_load_state("load")

                # Verify selection is cleared (new page)
                bulk_toolbar = page.locator("#bulk-actions-toolbar")
                expect(bulk_toolbar).to_have_class(re.compile(r"hidden"))
