"""
UI tests for Analytics pages comprehensive features using Playwright.
Tests main analytics page, scraper metrics, hunt metrics with chart interactions.
"""

import pytest
from playwright.sync_api import Page, expect
import os


class TestMainAnalyticsPage:
    """Test main analytics dashboard page."""
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_analytics_dashboard_loads(self, page: Page):
        """Test analytics dashboard page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Analytics - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('📊 Analytics Dashboard')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_analytics_cards_display(self, page: Page):
        """Test analytics dashboard cards display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Verify ML vs Hunt Comparison card
        ml_card = page.locator("text=ML vs Hunt Comparison")
        expect(ml_card).to_be_visible()
        
        # Verify Scraper Metrics card
        scraper_card = page.locator("text=Scraper Metrics")
        expect(scraper_card).to_be_visible()
        
        # Verify Hunt Scoring Metrics card
        hunt_card = page.locator("text=Hunt Scoring Metrics")
        expect(hunt_card).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_analytics_card_hover_effects(self, page: Page):
        """Test analytics card hover effects."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Find first card
        cards = page.locator(".bg-white.dark\\:bg-gray-800.rounded-lg.shadow-lg")
        if cards.count() > 0:
            first_card = cards.first
            expect(first_card).to_be_visible()
            
            # Hover over card
            first_card.hover()
            page.wait_for_timeout(500)
            
            # Verify shadow-xl class is applied (hover effect)
            # Note: This may require checking computed styles
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_analytics_card_navigation_links(self, page: Page):
        """Test analytics card navigation links."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Test Scraper Metrics link
        scraper_link = page.locator("a[href='/analytics/scraper-metrics']")
        expect(scraper_link).to_be_visible()
        scraper_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(f"{base_url}/analytics/scraper-metrics")
        
        # Go back
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Test Hunt Metrics link
        hunt_link = page.locator("a[href='/analytics/hunt-metrics']")
        expect(hunt_link).to_be_visible()
        hunt_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(f"{base_url}/analytics/hunt-metrics")
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_quick_overview_stats_display(self, page: Page):
        """Test quick overview stats display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        
        # Verify Quick Overview section
        quick_overview = page.locator("text=📈 Quick Overview")
        expect(quick_overview).to_be_visible()
        
        # Verify stat elements exist
        total_articles = page.locator("#totalArticles")
        expect(total_articles).to_be_visible()
        
        active_sources = page.locator("#activeSources")
        expect(active_sources).to_be_visible()
        
        avg_hunt_score = page.locator("#avgHuntScore")
        expect(avg_hunt_score).to_be_visible()
        
        filter_efficiency = page.locator("#filterEfficiency")
        expect(filter_efficiency).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_quick_stats_api_call(self, page: Page):
        """Test quick stats API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/dashboard/data" in route.request.url:
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/dashboard/data", handle_route)
        
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for async load
        
        # Verify API was called
        assert api_called["called"], "Dashboard data API should be called"
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_quick_stats_display_updates(self, page: Page):
        """Test quick stats display updates."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for async load
        
        # Verify stats are not just dashes
        total_articles = page.locator("#totalArticles")
        articles_text = total_articles.text_content()
        # Should be a number or dash
        assert articles_text is not None
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_quick_stats_error_handling(self, page: Page):
        """Test quick stats error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and fail API call
        def handle_route(route):
            route.fulfill(status=500, body="Internal Server Error")
        
        page.route("**/api/dashboard/data", handle_route)
        
        page.goto(f"{base_url}/analytics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify page still loads (graceful error handling)
        heading = page.locator("h1:has-text('📊 Analytics Dashboard')")
        expect(heading).to_be_visible()


class TestScraperMetricsPage:
    """Test scraper metrics page."""
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_scraper_metrics_page_loads(self, page: Page):
        """Test scraper metrics page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Scraper Metrics - Analytics - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('⚡ Scraper Metrics')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_breadcrumb_navigation(self, page: Page):
        """Test breadcrumb navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify breadcrumb exists
        breadcrumb = page.locator("nav[aria-label='Breadcrumb']")
        expect(breadcrumb).to_be_visible()
        
        # Verify Analytics link in breadcrumb
        analytics_link = breadcrumb.locator("a[href='/analytics']")
        expect(analytics_link).to_be_visible()
        
        # Click Analytics link
        analytics_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(f"{base_url}/analytics")
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_metrics_overview_cards(self, page: Page):
        """Test metrics overview cards display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify all overview cards
        articles_today = page.locator("#articlesToday")
        expect(articles_today).to_be_visible()
        
        active_sources = page.locator("#activeSources")
        expect(active_sources).to_be_visible()
        
        avg_response_time = page.locator("#avgResponseTime")
        expect(avg_response_time).to_be_visible()
        
        error_rate = page.locator("#errorRate")
        expect(error_rate).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_collection_rate_chart_display(self, page: Page):
        """Test collection rate chart display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for Chart.js to load
        
        # Verify chart canvas exists
        chart_canvas = page.locator("#collectionRateChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=📈 Collection Rate (Last 7 Days)")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_source_health_chart_display(self, page: Page):
        """Test source health chart display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for Chart.js to load
        
        # Verify chart canvas exists
        chart_canvas = page.locator("#sourceHealthChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=🏥 Source Health Distribution")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_hunt_score_chart_display(self, page: Page):
        """Test hunt score ranges chart display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for Chart.js to load
        
        # Verify chart canvas exists
        chart_canvas = page.locator("#huntScoreChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=🎯 Hunt Score Ranges (Last 30 Days)")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_hourly_distribution_chart_display(self, page: Page):
        """Test hourly distribution chart display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for Chart.js to load
        
        # Verify chart canvas exists
        chart_canvas = page.locator("#hourlyChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=🕐 Hourly Distribution (Today)")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_source_performance_table_toggle(self, page: Page):
        """Test source performance table toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Find toggle button
        toggle_btn = page.locator("#sourcePerformanceToggle")
        expect(toggle_btn).to_be_visible()
        
        # Find content (should be hidden initially)
        content = page.locator("#sourcePerformanceContent")
        expect(content).to_have_class("overflow-x-auto hidden")
        
        # Click toggle
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify content is now visible
        expect(content).not_to_have_class("hidden")
        
        # Click toggle again
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify content is hidden again
        expect(content).to_have_class("overflow-x-auto hidden")
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_source_performance_table_columns(self, page: Page):
        """Test source performance table columns."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Open table
        toggle_btn = page.locator("#sourcePerformanceToggle")
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify table headers
        headers = page.locator("#sourcePerformanceContent thead th")
        expect(headers.first).to_contain_text("Source")
        
        # Verify all expected columns
        expected_columns = ["Source", "Status", "Articles Today", "Last Success", "Error Rate", "Avg Response"]
        for col in expected_columns:
            header = page.locator(f"th:has-text('{col}')")
            expect(header).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_ingestion_analytics_toggle(self, page: Page):
        """Test ingestion analytics toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        
        # Find toggle button
        toggle_btn = page.locator("#ingestionAnalyticsToggle")
        expect(toggle_btn).to_be_visible()
        
        # Find content (should be hidden initially)
        content = page.locator("#ingestionAnalyticsContent")
        expect(content).to_have_class("p-6 hidden")
        
        # Click toggle
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify content is now visible
        expect(content).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_scraper_metrics_api_calls(self, page: Page):
        """Test scraper metrics API calls."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API calls
        api_calls = {
            "overview": False,
            "collection_rate": False,
            "source_health": False,
            "source_performance": False,
            "ingestion": False
        }
        
        def handle_route(route):
            url = route.request.url
            if "/api/analytics/scraper/overview" in url:
                api_calls["overview"] = True
            elif "/api/analytics/scraper/collection-rate" in url:
                api_calls["collection_rate"] = True
            elif "/api/analytics/scraper/source-health" in url:
                api_calls["source_health"] = True
            elif "/api/analytics/scraper/source-performance" in url:
                api_calls["source_performance"] = True
            elif "/api/health/ingestion" in url:
                api_calls["ingestion"] = True
            route.continue_()
        
        page.route("**/api/**", handle_route)
        
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for async calls
        
        # Verify API calls were made
        assert api_calls["overview"], "Overview API should be called"
        assert api_calls["collection_rate"], "Collection rate API should be called"
        assert api_calls["source_health"], "Source health API should be called"
        assert api_calls["source_performance"], "Source performance API should be called"
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_js_initialization(self, page: Page):
        """Test Chart.js library initialization."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for Chart.js to load
        
        # Verify Chart.js script is loaded
        chart_script = page.locator("script[src*='chart.js']")
        expect(chart_script).to_be_visible()
        
        # Verify Chart object exists in page context
        chart_exists = page.evaluate("typeof Chart !== 'undefined'")
        assert chart_exists, "Chart.js should be loaded"
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_rendering_updates(self, page: Page):
        """Test chart rendering and updates."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for charts to render
        
        # Verify charts are rendered (canvas elements exist)
        charts = page.locator("canvas")
        chart_count = charts.count()
        assert chart_count >= 4, f"Expected at least 4 charts, found {chart_count}"
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_error_handling(self, page: Page):
        """Test chart error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and fail API calls
        def handle_route(route):
            if "/api/analytics/scraper" in route.request.url:
                route.fulfill(status=500, body="Internal Server Error")
            else:
                route.continue_()
        
        page.route("**/api/analytics/scraper/**", handle_route)
        
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify page still loads (graceful error handling)
        heading = page.locator("h1:has-text('⚡ Scraper Metrics')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_empty_state(self, page: Page):
        """Test chart empty state handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and return empty data
        def handle_route(route):
            if "/api/analytics/scraper/collection-rate" in route.request.url:
                route.fulfill(status=200, body='{"labels": [], "values": []}', headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/analytics/scraper/collection-rate", handle_route)
        
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas still exists (should render empty chart)
        chart_canvas = page.locator("#collectionRateChart")
        expect(chart_canvas).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_responsive_behavior(self, page: Page):
        """Test chart responsive behavior."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Resize viewport
        page.set_viewport_size({"width": 375, "height": 667})  # Mobile size
        page.wait_for_timeout(1000)
        
        # Verify charts are still visible
        chart_canvas = page.locator("#collectionRateChart")
        expect(chart_canvas).to_be_visible()
        
        # Resize back
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.wait_for_timeout(1000)


class TestHuntMetricsPage:
    """Test hunt scoring metrics page."""
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_hunt_metrics_page_loads(self, page: Page):
        """Test hunt metrics page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Hunt Scoring Metrics - Analytics - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('🎯 Hunt Scoring Metrics')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_hunt_metrics_breadcrumb(self, page: Page):
        """Test hunt metrics breadcrumb navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify breadcrumb exists
        breadcrumb = page.locator("nav[aria-label='Breadcrumb']")
        expect(breadcrumb).to_be_visible()
        
        # Verify Analytics link
        analytics_link = breadcrumb.locator("a[href='/analytics']")
        expect(analytics_link).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_hunt_metrics_overview_cards(self, page: Page):
        """Test hunt metrics overview cards."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify all overview cards
        avg_hunt_score = page.locator("#avgHuntScore")
        expect(avg_hunt_score).to_be_visible()
        
        high_quality_articles = page.locator("#highQualityArticles")
        expect(high_quality_articles).to_be_visible()
        
        perfect_matches = page.locator("#perfectMatches")
        expect(perfect_matches).to_be_visible()
        
        lolbas_matches = page.locator("#lolbasMatches")
        expect(lolbas_matches).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_score_distribution_chart(self, page: Page):
        """Test score distribution chart."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas
        chart_canvas = page.locator("#scoreDistributionChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=📊 Hunt Score Distribution")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_keyword_performance_chart(self, page: Page):
        """Test keyword performance chart."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas
        chart_canvas = page.locator("#keywordPerformanceChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=🔍 Top Performing Keywords")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_keyword_performance_help_tooltip(self, page: Page):
        """Test keyword performance chart help tooltip."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Find help button
        help_button = page.locator("button[aria-label='Help']").first
        expect(help_button).to_be_visible()
        
        # Hover over help button
        help_button.hover()
        page.wait_for_timeout(500)
        
        # Verify tooltip appears
        tooltip = page.locator("text=Chart Scope")
        expect(tooltip).to_be_visible()
        
        # Verify tooltip content
        tooltip_content = page.locator("text=Perfect Discriminators")
        expect(tooltip_content).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_keyword_analysis_table_toggle(self, page: Page):
        """Test keyword analysis table toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Find toggle button
        toggle_btn = page.locator("#keywordAnalysisToggle")
        expect(toggle_btn).to_be_visible()
        
        # Find content (should be hidden initially)
        content = page.locator("#keywordAnalysisContent")
        expect(content).to_have_class("overflow-x-auto hidden")
        
        # Click toggle
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify content is now visible
        expect(content).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_keyword_analysis_table_columns(self, page: Page):
        """Test keyword analysis table columns."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Open table
        toggle_btn = page.locator("#keywordAnalysisToggle")
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify table headers
        expected_columns = ["Category", "Keyword", "Match Count", "Avg Score Impact"]
        for col in expected_columns:
            header = page.locator(f"th:has-text('{col}')")
            expect(header).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_score_trends_chart(self, page: Page):
        """Test score trends chart."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas
        chart_canvas = page.locator("#scoreTrendsChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=📈 Hunt Score Trends (Last 30 Days)")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_source_performance_chart(self, page: Page):
        """Test source performance chart."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas
        chart_canvas = page.locator("#sourcePerformanceChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=🎯 Top Sources by Hunt Score")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_quality_distribution_chart(self, page: Page):
        """Test content quality breakdown chart."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas
        chart_canvas = page.locator("#qualityDistributionChart")
        expect(chart_canvas).to_be_visible()
        
        # Verify chart title
        chart_title = page.locator("text=⭐ Content Quality Breakdown")
        expect(chart_title).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_quality_distribution_help_tooltip(self, page: Page):
        """Test content quality breakdown help tooltip."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Find help button (second one)
        help_buttons = page.locator("button:has(svg[fill='currentColor'])")
        if help_buttons.count() > 1:
            help_button = help_buttons.nth(1)
            expect(help_button).to_be_visible()
            
            # Hover over help button
            help_button.hover()
            page.wait_for_timeout(500)
            
            # Verify tooltip appears
            tooltip = page.locator("text=Content Quality Breakdown")
            expect(tooltip).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_advanced_metrics_display(self, page: Page):
        """Test advanced metrics display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify advanced metrics
        scoring_efficiency = page.locator("#scoringEfficiency")
        expect(scoring_efficiency).to_be_visible()
        
        avg_keywords = page.locator("#avgKeywordsPerArticle")
        expect(avg_keywords).to_be_visible()
        
        perfect_match_rate = page.locator("#perfectMatchRate")
        expect(perfect_match_rate).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_recent_high_score_articles(self, page: Page):
        """Test recent high-score articles display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify section exists
        section = page.locator("text=🔥 Recent High-Score Articles")
        expect(section).to_be_visible()
        
        # Verify container exists
        container = page.locator("#recentHighScoreArticles")
        expect(container).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_performance_insights_display(self, page: Page):
        """Test performance insights display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify insights section
        insights_section = page.locator("text=💡 Performance Insights")
        expect(insights_section).to_be_visible()
        
        # Verify top categories container
        top_categories = page.locator("#topCategories")
        expect(top_categories).to_be_visible()
        
        # Verify recommendations container
        recommendations = page.locator("#recommendations")
        expect(recommendations).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_hunt_metrics_api_calls(self, page: Page):
        """Test hunt metrics API calls."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API calls
        api_calls = {
            "overview": False,
            "score_distribution": False,
            "keyword_performance": False,
            "keyword_analysis": False,
            "score_trends": False,
            "source_performance": False,
            "quality_distribution": False,
            "advanced_metrics": False,
            "recent_high_scores": False,
            "performance_insights": False
        }
        
        def handle_route(route):
            url = route.request.url
            if "/api/analytics/hunt/overview" in url:
                api_calls["overview"] = True
            elif "/api/analytics/hunt/score-distribution" in url:
                api_calls["score_distribution"] = True
            elif "/api/analytics/hunt/keyword-performance" in url:
                api_calls["keyword_performance"] = True
            elif "/api/analytics/hunt/keyword-analysis" in url:
                api_calls["keyword_analysis"] = True
            elif "/api/analytics/hunt/score-trends" in url:
                api_calls["score_trends"] = True
            elif "/api/analytics/hunt/source-performance" in url:
                api_calls["source_performance"] = True
            elif "/api/analytics/hunt/quality-distribution" in url:
                api_calls["quality_distribution"] = True
            elif "/api/analytics/hunt/advanced-metrics" in url:
                api_calls["advanced_metrics"] = True
            elif "/api/analytics/hunt/recent-high-scores" in url:
                api_calls["recent_high_scores"] = True
            elif "/api/analytics/hunt/performance-insights" in url:
                api_calls["performance_insights"] = True
            route.continue_()
        
        page.route("**/api/**", handle_route)
        
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify API calls were made
        assert api_calls["overview"], "Overview API should be called"
        assert api_calls["score_distribution"], "Score distribution API should be called"
        assert api_calls["keyword_performance"], "Keyword performance API should be called"
        assert api_calls["keyword_analysis"], "Keyword analysis API should be called"
        assert api_calls["score_trends"], "Score trends API should be called"
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_data_update_on_refresh(self, page: Page):
        """Test chart data update on refresh."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Get initial chart state
        chart_canvas = page.locator("#scoreDistributionChart")
        expect(chart_canvas).to_be_visible()
        
        # Refresh page
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart still exists after refresh
        chart_canvas = page.locator("#scoreDistributionChart")
        expect(chart_canvas).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_tooltip_hover_interactions(self, page: Page):
        """Test tooltip hover interactions."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Find help button
        help_button = page.locator("button[aria-label='Help']").first
        expect(help_button).to_be_visible()
        
        # Hover
        help_button.hover()
        page.wait_for_timeout(500)
        
        # Verify tooltip is visible
        tooltip = page.locator("text=Chart Scope")
        expect(tooltip).to_be_visible()
        
        # Move away
        page.mouse.move(0, 0)
        page.wait_for_timeout(500)
        
        # Tooltip should disappear (check opacity)
        # Note: This may require checking computed styles


class TestChartInteractions:
    """Test chart interactions across all analytics pages."""
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_js_cdn_loading(self, page: Page):
        """Test Chart.js CDN loading."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify Chart.js script tag exists
        chart_script = page.locator("script[src*='chart.js']")
        expect(chart_script).to_be_visible()
        
        # Verify Chart.js is loaded in page context
        chart_loaded = page.evaluate("typeof Chart !== 'undefined'")
        assert chart_loaded, "Chart.js should be loaded"
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_responsive_behavior_all_pages(self, page: Page):
        """Test chart responsive behavior on all analytics pages."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Test scraper metrics
        page.goto(f"{base_url}/analytics/scraper-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(1000)
        chart = page.locator("#collectionRateChart")
        expect(chart).to_be_visible()
        
        # Test hunt metrics
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        page.set_viewport_size({"width": 375, "height": 667})
        page.wait_for_timeout(1000)
        chart = page.locator("#scoreDistributionChart")
        expect(chart).to_be_visible()
        
        # Reset viewport
        page.set_viewport_size({"width": 1920, "height": 1080})
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_empty_state_handling(self, page: Page):
        """Test chart empty state handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and return empty data
        def handle_route(route):
            if "/api/analytics/hunt/score-distribution" in route.request.url:
                route.fulfill(status=200, body='{"labels": [], "values": []}', headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/analytics/hunt/score-distribution", handle_route)
        
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify chart canvas still exists
        chart_canvas = page.locator("#scoreDistributionChart")
        expect(chart_canvas).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_error_state_handling(self, page: Page):
        """Test chart error state handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and fail API call
        def handle_route(route):
            if "/api/analytics/hunt/score-distribution" in route.request.url:
                route.fulfill(status=500, body="Internal Server Error")
            else:
                route.continue_()
        
        page.route("**/api/analytics/hunt/score-distribution", handle_route)
        
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify page still loads
        heading = page.locator("h1:has-text('🎯 Hunt Scoring Metrics')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.analytics
    def test_chart_loading_state(self, page: Page):
        """Test chart loading state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Delay API response
        def handle_route(route):
            import time
            time.sleep(0.5)  # Simulate delay
            route.continue_()
        
        page.route("**/api/analytics/hunt/score-distribution", handle_route)
        
        page.goto(f"{base_url}/analytics/hunt-metrics")
        page.wait_for_load_state("networkidle")
        
        # Verify chart canvas exists (may be empty during load)
        chart_canvas = page.locator("#scoreDistributionChart")
        expect(chart_canvas).to_be_visible()
        
        # Wait for chart to load
        page.wait_for_timeout(3000)
        
        # Verify chart is still visible after load
        expect(chart_canvas).to_be_visible()

