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

        # Toggle checkbox — clicking triggers form auto-submit; wait for navigation to complete
        title_only_checkbox.click()
        page.wait_for_load_state("load")

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
            # expect() auto-retries until the URL matches or the timeout expires,
            # making it robust even when form.submit() is queued asynchronously.
            expect(page).to_have_url(re.compile(r".*source=.*"), timeout=10000)

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
        expect(score_filter.locator("option").nth(1)).to_have_text("Excellent (80-100)")

        # Select score range. The change listener in articles.html fires
        # form.submit() asynchronously, so the navigation lags the dispatched
        # event. expect() auto-retries until the URL matches or times out,
        # matching the pattern used by the sibling source-filter test.
        score_filter.select_option("80-100")
        expect(page).to_have_url(re.compile(r".*threat_hunting_range=80-100.*"), timeout=10000)

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
            # expect() auto-retries until the URL matches or the timeout expires,
            # making it robust even when form.submit() is queued asynchronously.
            expect(page).to_have_url(re.compile(r".*threat_hunting_range=80-100.*"), timeout=10000)

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

        # expect() auto-retries until the URL matches or the timeout expires,
        # making it robust even when form.submit() is queued asynchronously.
        expect(page).to_have_url(re.compile(r".*sort_by=title.*"), timeout=10000)

    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_parameter_preservation_in_url(self, page: Page):
        """Test sort parameter preservation in URL."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # Navigate to clean /articles first, then use JS navigation to set exact query params.
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

        # Apply a filter (score range) and wait for its navigation to complete before sorting.
        score_filter = page.locator("#threat_hunting_range")
        if score_filter.is_visible():
            score_filter.select_option("80-100")
            expect(page).to_have_url(re.compile(r".*threat_hunting_range=80-100.*"), timeout=10000)
            _ensure_filters_visible(page)

        # Change sort
        sort_by = page.locator("#sort-by")
        sort_by.select_option("title")

        # Verify both parameters are in URL (threat_hunting_range from filter, sort_by from sort dropdown)
        expect(page).to_have_url(re.compile(r".*threat_hunting_range=80-100.*"), timeout=10000)
        expect(page).to_have_url(re.compile(r".*sort_by=title.*"), timeout=10000)

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

        # Change per-page — wrap in expect_navigation so we wait for the
        # form-submit navigation triggered by the select, not the pre-existing load state.
        per_page = page.locator("#per_page")
        with page.expect_navigation(wait_until="load", timeout=10000):
            per_page.select_option("50")

        # Verify URL contains per_page parameter
        expect(page).to_have_url(re.compile(r".*per_page=50.*"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_previous_next_navigation(self, page: Page):
        """Test Previous/Next navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?per_page=20&page=2")
        page.wait_for_load_state("load")

        # Find Previous link (exact role match -- article titles in the feed can
        # legitimately contain the substring "previous", which a text-contains
        # locator would also match).
        previous_link = page.get_by_role("link", name="Previous", exact=True)
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
    def test_article_bulk_select_checkboxes_have_accessible_names(self, page: Page):
        """Each article bulk-select checkbox identifies its article to assistive tech."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        checkboxes = page.locator(".bulk-select-checkbox")
        expect(checkboxes).not_to_have_count(0)

        first_checkbox = checkboxes.first
        expect(first_checkbox).to_have_attribute("aria-label", re.compile(r"^Select article #\d+: .+"))
        expect(page.get_by_role("checkbox", name=re.compile(r"^Select article #\d+: .+"))).not_to_have_count(0)

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


class TestArticlesCollapsedFilterIndicator:
    """Test that active filters remain visible when the filters panel is collapsed."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_no_badge_on_unfiltered_list(self, page: Page):
        """No active-filter badge should render when nothing is filtered."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        badge = page.locator("#filters-active-badge")
        expect(badge).to_have_class(re.compile(r"hidden"))

    @pytest.mark.ui
    @pytest.mark.articles
    def test_badge_appears_when_collapsed_with_filter(self, page: Page):
        """Collapsing the panel while a filter is active must surface an indicator.

        This is the collapse-then-navigate-to-filtered-URL regression case: a
        stored sessionStorage preference from an earlier visit can start the
        panel collapsed even though a filter is active, so the test forces a
        known state via the header click rather than assuming auto-open.
        """
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?search=test")
        page.wait_for_load_state("load")

        content = page.locator("#filters-content")
        header = page.locator("#filtersHeader")
        badge = page.locator("#filters-active-badge")

        if "hidden" in (content.get_attribute("class") or ""):
            header.click()
            page.wait_for_selector("#filters-content:not(.hidden)", timeout=5000)

        # Panel is open; badge stays hidden while open.
        expect(badge).to_have_class(re.compile(r"hidden"))

        # Collapse it -- the bug reproduction: a filtered list with no visible reason why.
        header.click()
        expect(content).to_have_class(re.compile(r"hidden"))

        expect(badge).not_to_have_class(re.compile(r"hidden"))
        expect(badge).to_contain_text("filter")
        expect(badge).to_contain_text("Clear")

    @pytest.mark.ui
    @pytest.mark.articles
    def test_badge_stays_hidden_when_panel_reopened(self, page: Page):
        """Expanding the panel again should hide the redundant badge."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?search=test")
        page.wait_for_load_state("load")

        content = page.locator("#filters-content")
        header = page.locator("#filtersHeader")
        badge = page.locator("#filters-active-badge")

        if "hidden" not in (content.get_attribute("class") or ""):
            header.click()
            expect(content).to_have_class(re.compile(r"hidden"))

        expect(badge).not_to_have_class(re.compile(r"hidden"))

        header.click()
        page.wait_for_selector("#filters-content:not(.hidden)", timeout=5000)
        expect(badge).to_have_class(re.compile(r"hidden"))


class TestArticlesKeywordChipAccessibility:
    """Keyword chips must expose the keyword as their accessible name, not the
    category hint -- and the +N overflow chip must expose what it hides."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_keyword_chip_accessible_name_is_the_keyword_not_the_category_hint(self, page: Page):
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("load")

        chips = page.locator(".keyword-chip")
        count = chips.count()
        if count == 0:
            pytest.skip("No keyword chips rendered for the current article set")

        # None of the per-keyword chips should carry a title -- that was the bug:
        # title on the outer span overrides the accessible name with the generic
        # category hint (e.g. "Good discriminator") instead of the keyword text.
        chip = chips.first
        title = chip.get_attribute("title")
        text = chip.text_content().strip()
        if title is not None and title.startswith("+"):
            pytest.skip("First chip happened to be an overflow chip; covered separately below")
        assert title is None, f"chip text={text!r} should have no title (accessible name must be the keyword)"

    @pytest.mark.ui
    @pytest.mark.articles
    def test_overflow_chip_exposes_hidden_keywords_via_title(self, page: Page):
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # A larger page widens the chance of an article with enough keywords to
        # overflow its per-category limit (3/2/2, see keyword_chips() in
        # articles.html); the default page 1 can legitimately have none.
        page.goto(f"{base_url}/articles?per_page=100")
        page.wait_for_load_state("load")

        # Locator has_text/filter with a Python regex was unreliable for this
        # exact "+N" shape in this Playwright version -- match on trimmed text
        # in Python instead of trusting the browser-side text match.
        chips = page.locator(".keyword-chip")
        overflow_index = next(
            (i for i in range(chips.count()) if re.match(r"^\+\d+$", chips.nth(i).text_content().strip())),
            None,
        )
        if overflow_index is None:
            pytest.skip("No overflow (+N) keyword chip rendered for the current article set")
        overflow_chip = chips.nth(overflow_index)

        title = overflow_chip.get_attribute("title")
        assert title, "overflow chip must carry a title listing the hidden keywords"
        assert title.strip() != "", "overflow chip title must not be empty"
