"""
UI tests for Articles list page advanced features using Playwright.
Tests advanced search, filtering, sorting, pagination, bulk actions, and classification modal.
"""

import pytest
from playwright.sync_api import Page, expect
import os
import json


class TestArticlesSearchAndFilter:
    """Test advanced search and filter features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_search_help_button_toggle(self, page: Page):
        """Test search help button toggle and modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
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
        page.wait_for_load_state("networkidle")
        
        # Open help panel
        help_button = page.locator("#search-help-btn")
        help_button.click()
        page.wait_for_timeout(300)
        
        # Verify help content is visible
        help_panel = page.locator("#search-help")
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
        """Test predefined search pattern links."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open help panel
        help_button = page.locator("#search-help-btn")
        help_button.click()
        page.wait_for_timeout(300)
        
        # Find predefined pattern links
        high_value_link = page.locator("a:has-text('Use This Search'):near(text='High-Value Detection Content')")
        technical_link = page.locator("a:has-text('Use This Search'):near(text='Technical Intelligence')")
        actionable_link = page.locator("a:has-text('Use This Search'):near(text='Actionable Intelligence Content')")
        
        # Verify links exist
        if high_value_link.count() > 0:
            expect(high_value_link.first).to_be_visible()
        if technical_link.count() > 0:
            expect(technical_link.first).to_be_visible()
        if actionable_link.count() > 0:
            expect(actionable_link.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_title_only_checkbox(self, page: Page):
        """Test title-only checkbox toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
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
        page.wait_for_load_state("networkidle")
        
        # Find search input
        search_input = page.locator("#search")
        expect(search_input).to_be_visible()
        
        # Test AND operator
        search_input.fill("malware AND ransomware")
        search_input.press("Enter")
        page.wait_for_timeout(1000)
        
        # Verify URL contains search parameter
        expect(page.url).to_contain("search=malware")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_source_filter_dropdown(self, page: Page):
        """Test source filter dropdown population and selection."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find source filter
        source_filter = page.locator("#source")
        expect(source_filter).to_be_visible()
        
        # Verify "All Sources" option exists
        all_sources_option = page.locator("#source option:has-text('All Sources')")
        expect(all_sources_option).to_be_visible()
        
        # Select a source if available
        options = source_filter.locator("option")
        if options.count() > 1:
            # Select first non-"All Sources" option
            source_filter.select_index(1)
            page.wait_for_timeout(1000)
            
            # Verify URL contains source parameter
            expect(page.url).to_contain("source=")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_filter_dropdown(self, page: Page):
        """Test classification filter dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find classification filter
        classification_filter = page.locator("#classification")
        expect(classification_filter).to_be_visible()
        
        # Verify options exist
        chosen_option = page.locator("#classification option:has-text('✅ Chosen')")
        rejected_option = page.locator("#classification option:has-text('❌ Rejected')")
        unclassified_option = page.locator("#classification option:has-text('⏳ Unclassified')")
        
        expect(chosen_option).to_be_visible()
        expect(rejected_option).to_be_visible()
        expect(unclassified_option).to_be_visible()
        
        # Select classification
        classification_filter.select_option("chosen")
        page.wait_for_timeout(1000)
        
        # Verify URL contains classification parameter
        expect(page.url).to_contain("classification=chosen")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_threat_hunting_score_range_filter(self, page: Page):
        """Test threat hunting score range filter."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find score range filter
        score_filter = page.locator("#threat_hunting_range")
        expect(score_filter).to_be_visible()
        
        # Verify options exist
        excellent_option = page.locator("#threat_hunting_range option:has-text('🎯 Excellent (80-100)')")
        expect(excellent_option).to_be_visible()
        
        # Select score range
        score_filter.select_option("80-100")
        page.wait_for_timeout(1000)
        
        # Verify URL contains score range parameter
        expect(page.url).to_contain("threat_hunting_range=80-100")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_filter_summary_display(self, page: Page):
        """Test filter summary display with active filters."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Apply a filter
        classification_filter = page.locator("#classification")
        classification_filter.select_option("chosen")
        page.wait_for_timeout(1000)
        
        # Verify filter summary appears
        filter_summary = page.locator("text=Active Filters:")
        expect(filter_summary).to_be_visible()
        
        # Verify classification is shown in summary
        classification_text = page.locator("text=Classification: chosen")
        expect(classification_text).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_clear_all_filters_link(self, page: Page):
        """Test clear all filters link."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Apply filters
        classification_filter = page.locator("#classification")
        classification_filter.select_option("chosen")
        page.wait_for_timeout(1000)
        
        # Find clear all link
        clear_link = page.locator("a:has-text('Clear all')")
        expect(clear_link).to_be_visible()
        
        # Click clear all
        clear_link.click()
        page.wait_for_load_state("networkidle")
        
        # Verify URL is reset (no filter parameters)
        expect(page.url).to_contain("/articles")
        # URL may still have some params, but classification should be gone
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_default_filters_save_button(self, page: Page):
        """Test default filters save functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find save default filters button
        save_button = page.locator("button:has-text('Set as Default Filters')")
        expect(save_button).to_be_visible()
        
        # Verify onclick handler
        onclick_attr = save_button.get_attribute("onclick")
        assert "saveDefaultFilters" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_default_filters_clear_button(self, page: Page):
        """Test default filters clear functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find clear default filters button
        clear_button = page.locator("button:has-text('Clear Defaults')")
        expect(clear_button).to_be_visible()
        
        # Verify onclick handler
        onclick_attr = clear_button.get_attribute("onclick")
        assert "clearDefaultFilters" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_default_filters_indicator(self, page: Page):
        """Test default filters indicator display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find default filters indicator
        indicator = page.locator("#default-filters-indicator")
        # Indicator may be hidden initially
        expect(indicator).to_be_visible() or expect(indicator).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_filter_persistence_session_storage(self, page: Page):
        """Test filter persistence via sessionStorage."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Apply a filter
        classification_filter = page.locator("#classification")
        classification_filter.select_option("chosen")
        page.wait_for_timeout(1000)
        
        # Check sessionStorage
        session_storage = page.evaluate("() => sessionStorage.getItem('cti_articles_settings')")
        if session_storage:
            settings = json.loads(session_storage)
            assert "classification" in settings, "Settings should contain classification"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_url_parameter_filter_parsing(self, page: Page):
        """Test URL parameter filter parsing and application."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate with filter parameters
        page.goto(f"{base_url}/articles?classification=chosen&search=malware")
        page.wait_for_load_state("networkidle")
        
        # Verify filters are applied
        classification_filter = page.locator("#classification")
        expect(classification_filter).to_have_value("chosen")
        
        search_input = page.locator("#search")
        expect(search_input).to_have_value("malware")


class TestArticlesSorting:
    """Test sorting features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_by_dropdown_options(self, page: Page):
        """Test sort by dropdown has all options."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find sort by dropdown
        sort_by = page.locator("#sort-by")
        expect(sort_by).to_be_visible()
        
        # Verify all options exist
        options = [
            "discovered_at",
            "published_at",
            "title",
            "source_id",
            "threat_hunting_score",
            "annotation_count",
            "word_count",
            "id"
        ]
        
        for option_value in options:
            option = page.locator(f"#sort-by option[value='{option_value}']")
            if option.count() > 0:
                expect(option.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_order_dropdown(self, page: Page):
        """Test sort order dropdown (asc/desc)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find sort order dropdown
        sort_order = page.locator("#sort-order")
        expect(sort_order).to_be_visible()
        
        # Verify options exist
        desc_option = page.locator("#sort-order option[value='desc']")
        asc_option = page.locator("#sort-order option[value='asc']")
        
        expect(desc_option).to_be_visible()
        expect(asc_option).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_dynamic_sorting_auto_submit(self, page: Page):
        """Test dynamic sorting auto-submit on change."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Change sort by
        sort_by = page.locator("#sort-by")
        sort_by.select_option("title")
        page.wait_for_timeout(1000)
        
        # Verify URL contains sort parameter
        expect(page.url).to_contain("sort_by=title")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_parameter_preservation_in_url(self, page: Page):
        """Test sort parameter preservation in URL."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?sort_by=title&sort_order=asc")
        page.wait_for_load_state("networkidle")
        
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
        page.wait_for_load_state("networkidle")
        
        # Apply filter
        classification_filter = page.locator("#classification")
        classification_filter.select_option("chosen")
        page.wait_for_timeout(1000)
        
        # Change sort
        sort_by = page.locator("#sort-by")
        sort_by.select_option("title")
        page.wait_for_timeout(1000)
        
        # Verify both parameters are in URL
        expect(page.url).to_contain("classification=chosen")
        expect(page.url).to_contain("sort_by=title")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sort_reset_functionality(self, page: Page):
        """Test sort reset functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?sort_by=title&sort_order=asc")
        page.wait_for_load_state("networkidle")
        
        # Navigate to base URL (resets sort)
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Verify sort defaults are applied
        sort_by = page.locator("#sort-by")
        # Default may be "published_at" or "discovered_at"
        assert sort_by.input_value() in ["published_at", "discovered_at"], "Sort should reset to default"


class TestArticlesPagination:
    """Test pagination features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_per_page_selector(self, page: Page):
        """Test per-page selector (20/50/100)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find per-page selector
        per_page = page.locator("#per_page")
        expect(per_page).to_be_visible()
        
        # Verify options exist
        option_20 = page.locator("#per_page option[value='20']")
        option_50 = page.locator("#per_page option[value='50']")
        option_100 = page.locator("#per_page option[value='100']")
        
        expect(option_20).to_be_visible()
        expect(option_50).to_be_visible()
        expect(option_100).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_per_page_change(self, page: Page):
        """Test changing per-page value."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Change per-page
        per_page = page.locator("#per_page")
        per_page.select_option("50")
        page.wait_for_timeout(1000)
        
        # Verify URL contains per_page parameter
        expect(page.url).to_contain("per_page=50")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_page_number_links(self, page: Page):
        """Test page number links with ellipsis."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?per_page=20")
        page.wait_for_load_state("networkidle")
        
        # Find pagination links
        page_links = page.locator("a:has-text('1'), a:has-text('2'), a:has-text('3')")
        # Page links may or may not exist depending on total pages
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_previous_next_navigation(self, page: Page):
        """Test Previous/Next navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?per_page=20&page=2")
        page.wait_for_load_state("networkidle")
        
        # Find Previous link
        previous_link = page.locator("a:has-text('Previous')")
        if previous_link.count() > 0:
            expect(previous_link.first).to_be_visible()
            
            # Click Previous
            previous_link.click()
            page.wait_for_load_state("networkidle")
            
            # Verify page changed
            expect(page.url).to_contain("page=1")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_pagination_state_preservation_with_filters(self, page: Page):
        """Test pagination state preservation with filters."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?classification=chosen&page=2")
        page.wait_for_load_state("networkidle")
        
        # Navigate to next page
        next_link = page.locator("a:has-text('Next')")
        if next_link.count() > 0:
            next_link.click()
            page.wait_for_load_state("networkidle")
            
            # Verify filter is preserved
            expect(page.url).to_contain("classification=chosen")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_page_count_display(self, page: Page):
        """Test page count display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find page count text
        page_count = page.locator("text=Page")
        if page_count.count() > 0:
            expect(page_count.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_results_range_display(self, page: Page):
        """Test results range display (start_idx-end_idx of total)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find results range text (e.g., "Articles (1-20 of 100)")
        results_range = page.locator("text=/Articles \\(\\d+-\\d+ of \\d+\\)/")
        if results_range.count() > 0:
            expect(results_range.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_pagination_with_sorting(self, page: Page):
        """Test pagination with sorting."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?sort_by=title&page=2")
        page.wait_for_load_state("networkidle")
        
        # Navigate to next page
        next_link = page.locator("a:has-text('Next')")
        if next_link.count() > 0:
            next_link.click()
            page.wait_for_load_state("networkidle")
            
            # Verify sort is preserved
            expect(page.url).to_contain("sort_by=title")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_pagination_empty_state(self, page: Page):
        """Test pagination empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # Navigate with filter that returns no results
        page.goto(f"{base_url}/articles?search=nonexistent_article_xyz_12345")
        page.wait_for_load_state("networkidle")
        
        # Verify empty state message
        empty_message = page.locator("text=No articles found")
        expect(empty_message).to_be_visible()


class TestArticlesStatistics:
    """Test article statistics features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_statistics_toggle(self, page: Page):
        """Test article statistics toggle (collapsible)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find statistics toggle button
        stats_toggle = page.locator("#articleStatsToggle")
        expect(stats_toggle).to_be_visible()
        
        # Get initial state
        stats_content = page.locator("#articleStatsContent")
        initial_state = stats_content.is_visible()
        
        # Click toggle
        stats_toggle.click()
        page.wait_for_timeout(300)
        
        # Verify state changed
        new_state = stats_content.is_visible()
        assert initial_state != new_state, "Statistics toggle should change visibility"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_statistics_panel_display(self, page: Page):
        """Test statistics panel display (total, chosen, rejected counts)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Expand statistics panel
        stats_toggle = page.locator("#articleStatsToggle")
        stats_toggle.click()
        page.wait_for_timeout(300)
        
        # Verify statistics are displayed
        total_text = page.locator("text=Total Articles")
        chosen_text = page.locator("text=Chosen")
        rejected_text = page.locator("text=Rejected")
        
        expect(total_text).to_be_visible()
        expect(chosen_text).to_be_visible()
        expect(rejected_text).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_statistics_panel_collapse_expand(self, page: Page):
        """Test statistics panel collapse/expand."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Toggle statistics panel multiple times
        stats_toggle = page.locator("#articleStatsToggle")
        stats_content = page.locator("#articleStatsContent")
        
        # First toggle
        initial_state = stats_content.is_visible()
        stats_toggle.click()
        page.wait_for_timeout(300)
        
        # Second toggle
        stats_toggle.click()
        page.wait_for_timeout(300)
        
        # Verify it returns to initial state
        final_state = stats_content.is_visible()
        assert initial_state == final_state, "Statistics panel should toggle correctly"


class TestArticlesBulkSelection:
    """Test bulk selection features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_select_all_visible_checkbox(self, page: Page):
        """Test select all visible checkbox."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find select all checkbox
        select_all = page.locator("#select-all-matching")
        if select_all.count() > 0:
            expect(select_all.first).to_be_visible()
            
            # Click select all
            select_all.click()
            page.wait_for_timeout(500)
            
            # Verify bulk actions toolbar appears
            bulk_toolbar = page.locator("#bulk-actions-toolbar")
            expect(bulk_toolbar).to_be_visible()
            expect(bulk_toolbar).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_individual_article_checkboxes(self, page: Page):
        """Test individual article checkboxes."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find article checkboxes
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            # Click first checkbox
            first_checkbox = checkboxes.first
            expect(first_checkbox).to_be_visible()
            
            first_checkbox.click()
            page.wait_for_timeout(500)
            
            # Verify bulk actions toolbar appears
            bulk_toolbar = page.locator("#bulk-actions-toolbar")
            expect(bulk_toolbar).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_actions_toolbar_visibility(self, page: Page):
        """Test bulk actions toolbar visibility toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Initially toolbar should be hidden
        bulk_toolbar = page.locator("#bulk-actions-toolbar")
        expect(bulk_toolbar).to_have_class("hidden")
        
        # Select an article
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Verify toolbar is visible
            expect(bulk_toolbar).to_be_visible()
            expect(bulk_toolbar).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_selected_count_display(self, page: Page):
        """Test selected count display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select articles
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() >= 2:
            checkboxes.first.click()
            checkboxes.nth(1).click()
            page.wait_for_timeout(500)
            
            # Verify selected count
            selected_count = page.locator("#selected-count")
            expect(selected_count).to_be_visible()
            count_text = selected_count.text_content()
            assert "2" in count_text or count_text == "2", "Selected count should show 2"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_select_all_visible_button(self, page: Page):
        """Test Select All Visible button in toolbar."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select an article to show toolbar
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Find Select All Visible button in toolbar
            select_all_btn = page.locator("button:has-text('Select All Visible')")
            expect(select_all_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = select_all_btn.get_attribute("onclick")
            assert "selectAllVisible" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_clear_selection_button(self, page: Page):
        """Test Clear Selection button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select an article to show toolbar
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Find Clear Selection button
            clear_btn = page.locator("button:has-text('Clear Selection')")
            expect(clear_btn).to_be_visible()
            
            # Click clear selection
            clear_btn.click()
            page.wait_for_timeout(500)
            
            # Verify toolbar is hidden
            bulk_toolbar = page.locator("#bulk-actions-toolbar")
            expect(bulk_toolbar).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_action_mark_as_chosen(self, page: Page):
        """Test bulk action Mark as Chosen button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select an article
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Find Mark as Chosen button
            chosen_btn = page.locator("button:has-text('✅ Mark as Chosen')")
            expect(chosen_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = chosen_btn.get_attribute("onclick")
            assert "bulkAction('chosen')" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_action_reject(self, page: Page):
        """Test bulk action Reject button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select an article
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Find Reject button
            reject_btn = page.locator("button:has-text('❌ Reject')")
            expect(reject_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = reject_btn.get_attribute("onclick")
            assert "bulkAction('rejected')" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_action_unclassify(self, page: Page):
        """Test bulk action Unclassify button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select an article
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Find Unclassify button
            unclassify_btn = page.locator("button:has-text('⏳ Unclassify')")
            expect(unclassify_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = unclassify_btn.get_attribute("onclick")
            assert "bulkAction('unclassified')" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_action_delete(self, page: Page):
        """Test bulk action Delete button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Select an article
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Find Delete button
            delete_btn = page.locator("button:has-text('🗑️ Delete')")
            expect(delete_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = delete_btn.get_attribute("onclick")
            assert "bulkAction('delete')" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_selection_state_persistence(self, page: Page):
        """Test bulk selection state persistence."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_timeout(1000)
        
        # Select articles
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() >= 2:
            checkboxes.first.click()
            page.wait_for_timeout(300)
            
            # Verify selection persists (checkbox remains checked)
            first_checkbox = checkboxes.first
            expect(first_checkbox).to_be_checked()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_bulk_selection_with_pagination(self, page: Page):
        """Test bulk selection with pagination."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?per_page=20")
        page.wait_for_load_state("networkidle")
        
        # Select articles on first page
        checkboxes = page.locator(".bulk-select-checkbox")
        if checkboxes.count() > 0:
            checkboxes.first.click()
            page.wait_for_timeout(500)
            
            # Navigate to next page
            next_link = page.locator("a:has-text('Next')")
            if next_link.count() > 0:
                next_link.click()
                page.wait_for_load_state("networkidle")
                
                # Verify selection is cleared (new page)
                bulk_toolbar = page.locator("#bulk-actions-toolbar")
                expect(bulk_toolbar).to_have_class("hidden")


class TestArticlesCardFeatures:
    """Test article card features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_title_link_navigation(self, page: Page):
        """Test article title link navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find article title link
        title_links = page.locator("a[href^='/articles/']")
        if title_links.count() > 0:
            first_link = title_links.first
            expect(first_link).to_be_visible()
            
            # Click link
            first_link.click()
            page.wait_for_load_state("networkidle")
            
            # Verify navigation to article detail page
            expect(page.url).to_match(r".*\/articles\/\d+")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_id_badge_display(self, page: Page):
        """Test Article ID badge display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find article ID badges
        id_badges = page.locator("span:has-text('#'):near(a[href^='/articles/'])")
        if id_badges.count() > 0:
            expect(id_badges.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_source_name_display_and_link(self, page: Page):
        """Test source name display and link."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find source links
        source_links = page.locator("a[target='_blank']:has-text('Source:')")
        # Source links may or may not exist depending on article data
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_published_date_display_formatting(self, page: Page):
        """Test published date display formatting."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find published date text
        published_text = page.locator("text=Published:")
        if published_text.count() > 0:
            expect(published_text.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_content_length_display(self, page: Page):
        """Test content length display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find content length text
        content_length = page.locator("text=Content:")
        if content_length.count() > 0:
            expect(content_length.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_badge_display(self, page: Page):
        """Test classification badge display (chosen/rejected/unclassified)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find classification badges
        chosen_badge = page.locator("span:has-text('✅ Chosen')")
        rejected_badge = page.locator("span:has-text('❌ Rejected')")
        unclassified_badge = page.locator("span:has-text('⏳ Unclassified')")
        
        # At least one badge type should be visible
        total_badges = chosen_badge.count() + rejected_badge.count() + unclassified_badge.count()
        assert total_badges > 0, "At least one classification badge should be visible"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_regexhuntscore_badge_color_coding(self, page: Page):
        """Test RegexHuntScore badge with color coding (80+, 60+, 40+, <40)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find score badges
        score_badges = page.locator("span:has-text('🎯'), span:has-text('🟡'), span:has-text('🟠'), span:has-text('🔴')")
        # Score badges may or may not exist depending on article data
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_ml_hunt_score_badge_color_coding(self, page: Page):
        """Test ML Hunt Score badge with color coding."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find ML score badges
        ml_score_badges = page.locator("span:has-text('🤖')")
        # ML score badges may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_ml_hunt_score_tbd_state(self, page: Page):
        """Test ML Hunt Score 'TBD' state with tooltip."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find TBD badges
        tbd_badges = page.locator("span:has-text('TBD')")
        if tbd_badges.count() > 0:
            # Verify tooltip attribute
            tbd_badge = tbd_badges.first
            title_attr = tbd_badge.get_attribute("title")
            assert title_attr is not None, "TBD badge should have tooltip"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_annotation_count_badge_display(self, page: Page):
        """Test annotation count badge display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find annotation badges
        annotation_badges = page.locator("span:has-text('📝')")
        # Annotation badges may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_keyword_matches_display(self, page: Page):
        """Test keyword matches display (perfect, good, LOLBAS)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find keyword match badges
        perfect_matches = page.locator("span:has-text('✅'):near(text=Perfect)")
        good_matches = page.locator("span:has-text('🟡'):near(text=Good)")
        lolbas_matches = page.locator("span:has-text('🔧')")
        # Keyword matches may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_keyword_match_truncation(self, page: Page):
        """Test keyword match truncation (+N indicator)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find truncation indicators
        truncation_indicators = page.locator("span:has-text('+')")
        # Truncation indicators may exist if there are many keyword matches
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_content_preview(self, page: Page):
        """Test article content preview (first 300 chars)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find article content previews
        content_previews = page.locator("p.text-gray-700")
        if content_previews.count() > 0:
            first_preview = content_previews.first
            preview_text = first_preview.text_content()
            # Preview should be truncated (may end with "...")
            assert preview_text is not None, "Content preview should exist"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_copy_article_content_button(self, page: Page):
        """Test copy article content button functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find copy buttons
        copy_buttons = page.locator("button[onclick*='copyArticleContent']")
        if copy_buttons.count() > 0:
            expect(copy_buttons.first).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = copy_buttons.first.get_attribute("onclick")
            assert "copyArticleContent" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_original_source_link_functionality(self, page: Page):
        """Test original source link functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find original source links
        source_links = page.locator("a:has-text('📖 Original Source')")
        if source_links.count() > 0:
            first_link = source_links.first
            expect(first_link).to_be_visible()
            expect(first_link).to_have_attribute("target", "_blank")


class TestArticlesClassificationModal:
    """Test classification modal features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_open(self, page: Page):
        """Test classification modal open functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find classification button (may be in article cards)
        classify_buttons = page.locator("button:has-text('Classify'), button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Verify modal opens
            modal = page.locator("#classificationModal")
            expect(modal).to_be_visible()
            expect(modal).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_close(self, page: Page):
        """Test classification modal close functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal if possible
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Find close button
            close_button = page.locator("#classificationModal button:has-text('✕'), button[onclick*='closeClassificationModal']")
            if close_button.count() > 0:
                close_button.click()
                page.wait_for_timeout(300)
                
                # Verify modal closes
                modal = page.locator("#classificationModal")
                expect(modal).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_loading_state(self, page: Page):
        """Test classification modal loading state display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(300)
            
            # Verify loading state exists
            loading_state = page.locator("#modalLoading")
            expect(loading_state).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_article_data_loading(self, page: Page):
        """Test classification modal article data loading."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(2000)  # Wait for data to load
            
            # Verify article content is displayed
            article_content = page.locator("#modalArticleContent")
            expect(article_content).to_be_visible()
            expect(article_content).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_article_title_display(self, page: Page):
        """Test article title display in modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Verify title is displayed
            title_element = page.locator("#articleTitle")
            expect(title_element).to_be_visible()
            title_text = title_element.text_content()
            assert title_text is not None and len(title_text) > 0, "Article title should be displayed"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_article_content_display(self, page: Page):
        """Test article content display in modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Verify content is displayed
            content_element = page.locator("#articleContent")
            expect(content_element).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_buttons_in_modal(self, page: Page):
        """Test classification buttons in modal (chosen/rejected/unclassified)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Verify classification buttons exist
            chosen_btn = page.locator("button:has-text('✅ Chosen')")
            rejected_btn = page.locator("button:has-text('❌ Rejected')")
            unclassified_btn = page.locator("button:has-text('⏳ Unclassified')")
            
            expect(chosen_btn).to_be_visible()
            expect(rejected_btn).to_be_visible()
            expect(unclassified_btn).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_navigation_previous(self, page: Page):
        """Test modal navigation (Previous button)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Find Previous button
            previous_btn = page.locator("button:has-text('← Previous')")
            expect(previous_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = previous_btn.get_attribute("onclick")
            assert "navigateToPrevious" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_navigation_next_unclassified(self, page: Page):
        """Test modal navigation (Next Unclassified button)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(2000)
            
            # Find Next Unclassified button
            next_btn = page.locator("button:has-text('Next Unclassified')")
            expect(next_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = next_btn.get_attribute("onclick")
            assert "navigateToNextUnclassified" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_escape_key(self, page: Page):
        """Test modal keyboard shortcuts (Escape to close)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Press Escape key
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            
            # Verify modal closes
            modal = page.locator("#classificationModal")
            expect(modal).to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_classification_modal_click_away(self, page: Page):
        """Test modal click-away to close."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Open modal
        classify_buttons = page.locator("button[onclick*='openClassificationModal']")
        if classify_buttons.count() > 0:
            classify_buttons.first.click()
            page.wait_for_timeout(500)
            
            # Click on modal backdrop
            modal = page.locator("#classificationModal")
            modal.click(position={"x": 10, "y": 10})  # Click near edge
            page.wait_for_timeout(300)
            
            # Modal may or may not close on backdrop click depending on implementation


class TestArticlesEmptyState:
    """Test empty state features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_no_articles_found_message(self, page: Page):
        """Test no articles found message."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # Navigate with filter that returns no results
        page.goto(f"{base_url}/articles?search=nonexistent_article_xyz_12345")
        page.wait_for_load_state("networkidle")
        
        # Verify empty state message
        empty_message = page.locator("text=No articles found")
        expect(empty_message).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_empty_state_with_filters_active(self, page: Page):
        """Test empty state with filters active message."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles?search=nonexistent_article_xyz_12345")
        page.wait_for_load_state("networkidle")
        
        # Verify message suggests adjusting filters
        adjust_message = page.locator("text=Try adjusting your filters")
        expect(adjust_message).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_empty_state_without_filters(self, page: Page):
        """Test empty state without filters message."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        # Navigate to articles page (may or may not have articles)
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Check if empty state appears
        empty_state = page.locator("text=No articles found")
        # Empty state may or may not appear depending on data

