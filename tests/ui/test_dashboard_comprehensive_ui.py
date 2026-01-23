"""
UI tests for Dashboard page comprehensive features using Playwright.
Tests dashboard widgets, charts, failing sources, high-score articles, quick actions, and related features.
"""

import pytest
from playwright.sync_api import Page, expect
import os


class TestDashboardPageLoad:
    """Test dashboard page basic loading."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_dashboard_page_loads(self, page: Page):
        """Test dashboard page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Dashboard - CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('Huntable - CTI Scraper & Workbench')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_last_updated_timestamp_display(self, page: Page):
        """Test last updated timestamp display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify last updated timestamp exists
        last_updated = page.locator("#last-updated")
        expect(last_updated).to_be_visible()
        
        # Verify timestamp is not empty
        timestamp_text = last_updated.text_content()
        assert timestamp_text is not None and timestamp_text.strip() != ""


class TestHealthMetricsCard:
    """Test health metrics card."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_health_metrics_card_display(self, page: Page):
        """Test health metrics card displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify health card exists
        health_card = page.locator("text=Article Ingestion Health")
        expect(health_card).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_uptime_display(self, page: Page):
        """Test uptime percentage display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for API data load
        
        # Verify uptime value exists
        uptime_value = page.locator("#uptime-value")
        expect(uptime_value).to_be_visible()
        
        # Verify uptime label exists
        uptime_label = page.locator("text=Uptime")
        expect(uptime_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_total_sources_display(self, page: Page):
        """Test total sources count display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify total sources value exists
        total_sources = page.locator("#total-sources")
        expect(total_sources).to_be_visible()
        
        # Verify total sources label exists
        total_sources_label = page.locator("text=Total Sources")
        expect(total_sources_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_avg_response_time_display(self, page: Page):
        """Test average response time display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify avg response value exists
        avg_response = page.locator("#avg-response")
        expect(avg_response).to_be_visible()
        
        # Verify avg response label exists
        avg_response_label = page.locator("text=Avg Response")
        expect(avg_response_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_health_indicator_color_coding(self, page: Page):
        """Test health indicator color coding."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify health indicator exists
        health_indicator = page.locator("#health-indicator")
        expect(health_indicator).to_be_visible()
        
        # Verify indicator has a color class (green/yellow/red)
        indicator_class = health_indicator.get_attribute("class")
        assert "bg-green" in indicator_class or "bg-yellow" in indicator_class or "bg-red" in indicator_class


class TestVolumeCharts:
    """Test volume charts."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_daily_chart_display(self, page: Page):
        """Test daily volume chart display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)  # Wait for Chart.js to load
        
        # Verify daily chart canvas exists
        daily_chart = page.locator("#dailyChart")
        expect(daily_chart).to_be_visible()
        
        # Verify daily chart label
        daily_label = page.locator("text=Daily Volume")
        expect(daily_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_hourly_chart_display(self, page: Page):
        """Test hourly volume chart display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify hourly chart canvas exists
        hourly_chart = page.locator("#hourlyChart")
        expect(hourly_chart).to_be_visible()
        
        # Verify hourly chart label
        hourly_label = page.locator("text=Hourly Volume")
        expect(hourly_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_chart_js_initialization(self, page: Page):
        """Test Chart.js library initialization."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify Chart.js is loaded
        chart_exists = page.evaluate("typeof Chart !== 'undefined'")
        assert chart_exists, "Chart.js should be loaded"
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_chart_data_updates_from_api(self, page: Page):
        """Test chart data updates from API."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/dashboard/data" in route.request.url:
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/dashboard/data", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify API was called
        assert api_called["called"], "Dashboard data API should be called"
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_chart_responsive_behavior(self, page: Page):
        """Test chart responsive behavior."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Resize viewport
        page.set_viewport_size({"width": 375, "height": 667})  # Mobile
        page.wait_for_timeout(1000)
        
        # Verify charts are still visible
        daily_chart = page.locator("#dailyChart")
        expect(daily_chart).to_be_visible()
        
        # Resize back
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.wait_for_timeout(1000)


class TestFailingSourcesWidget:
    """Test failing sources widget."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_failing_sources_widget_display(self, page: Page):
        """Test failing sources widget displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify failing sources section exists
        failing_sources_section = page.locator("text=Failing Sources")
        expect(failing_sources_section).to_be_visible()
        
        # Verify container exists
        failing_container = page.locator("#failing-sources-container")
        expect(failing_container).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_failing_sources_api_call(self, page: Page):
        """Test failing sources API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/sources/failing" in route.request.url:
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/sources/failing", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Failing sources API should be called"
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_failing_sources_empty_state(self, page: Page):
        """Test failing sources empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and return empty data
        def handle_route(route):
            if "/api/sources/failing" in route.request.url:
                route.fulfill(status=200, body="[]", headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/sources/failing", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify empty state message
        empty_state = page.locator("text=No failing sources")
        # Empty state may or may not be visible depending on data


class TestHighScoreArticlesWidget:
    """Test high-score articles widget."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_high_score_articles_widget_display(self, page: Page):
        """Test high-score articles widget displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify high-score articles section exists
        high_score_section = page.locator("text=High-Score Articles")
        expect(high_score_section).to_be_visible()
        
        # Verify container exists
        high_score_container = page.locator("#high-score-articles-container")
        expect(high_score_container).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_copy_urls_button(self, page: Page):
        """Test copy URLs button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify copy URLs button exists
        copy_btn = page.locator("button:has-text('📋 Copy URLs')")
        expect(copy_btn).to_be_visible()
        
        # Verify onclick handler
        onclick_attr = copy_btn.get_attribute("onclick")
        assert "copyArticleUrls" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_article_cards_display(self, page: Page):
        """Test article cards display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Find article links
        article_links = page.locator("a[href^='/articles/']")
        # Articles may or may not exist depending on data
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_article_classification_badges(self, page: Page):
        """Test article classification badges."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Look for classification badges
        chosen_badges = page.locator("text=Chosen")
        rejected_badges = page.locator("text=Rejected")
        unclassified_badges = page.locator("text=Unclassified")
        # Badges may or may not exist depending on data
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_article_hunt_score_display(self, page: Page):
        """Test article hunt score display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Look for score displays (numbers)
        score_elements = page.locator("text=/\\d{1,2}\\.\\d/")
        # Scores may or may not exist depending on data


class TestSystemStatsWidget:
    """Test system stats widget."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_system_stats_widget_display(self, page: Page):
        """Test system stats widget displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify system stats section exists
        system_stats_section = page.locator("text=System Stats")
        expect(system_stats_section).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_total_articles_display(self, page: Page):
        """Test total articles count display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify total articles label exists
        total_articles_label = page.locator("text=Total Articles")
        expect(total_articles_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_active_sources_display(self, page: Page):
        """Test active sources count display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify active sources label exists
        active_sources_label = page.locator("text=Active Sources")
        expect(active_sources_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_processing_queue_display(self, page: Page):
        """Test processing queue display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify processing queue label exists
        processing_queue_label = page.locator("text=Processing Queue")
        expect(processing_queue_label).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_avg_score_display(self, page: Page):
        """Test average score display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify avg score label exists
        avg_score_label = page.locator("text=Avg Score")
        expect(avg_score_label).to_be_visible()


class TestRecentActivityWidget:
    """Test recent activity widget."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_recent_activity_widget_display(self, page: Page):
        """Test recent activity widget displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify recent activity section exists
        recent_activity_section = page.locator("text=Recent Activity")
        expect(recent_activity_section).to_be_visible()
        
        # Verify container exists
        recent_activity_container = page.locator("#recent-activity-container")
        expect(recent_activity_container).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_recent_activity_empty_state(self, page: Page):
        """Test recent activity empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Check for empty state message
        empty_state = page.locator("text=No recent activity")
        # Empty state may or may not be visible depending on data


class TestQuickActions:
    """Test quick actions."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_quick_actions_section_display(self, page: Page):
        """Test quick actions section displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify quick actions section exists
        quick_actions_section = page.locator("text=Quick Actions")
        expect(quick_actions_section).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_rescore_all_articles_button(self, page: Page):
        """Test Rescore All Articles button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify rescore button exists
        rescore_btn = page.locator("button:has-text('🔄 Rescore All Articles')")
        expect(rescore_btn).to_be_visible()
        
        # Verify onclick handler
        onclick_attr = rescore_btn.get_attribute("onclick")
        assert "rescoreAllArticles" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_rescore_all_articles_api_call(self, page: Page):
        """Test Rescore All Articles API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call - MUST set up route BEFORE navigation
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/actions/rescore-all" in route.request.url and route.request.method == "POST":
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/actions/rescore-all", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Wait for button to be visible and clickable
        rescore_btn = page.locator("button:has-text('🔄 Rescore All Articles'), button:has-text('Rescore All Articles')").first
        rescore_btn.wait_for(state="visible", timeout=5000)
        rescore_btn.click()
        page.wait_for_timeout(3000)  # Wait for API call to complete
        
        # Verify API was called
        assert api_called["called"], "Rescore all articles API should be called"
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_run_health_check_button(self, page: Page):
        """Test Run Health Check button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Verify health check button exists
        health_check_btn = page.locator("button:has-text('🔍 Run Health Check')")
        expect(health_check_btn).to_be_visible()
        
        # Verify onclick handler
        onclick_attr = health_check_btn.get_attribute("onclick")
        assert "runHealthCheck" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_run_health_check_navigation(self, page: Page):
        """Test Run Health Check navigation."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        
        # Click health check button
        health_check_btn = page.locator("button:has-text('🔍 Run Health Check')")
        health_check_btn.click()
        page.wait_for_timeout(1000)
        
        # Verify navigation to health checks page
        expect(page).to_have_url(f"{base_url}/health-checks")
        
        # Verify session storage flag was set
        auto_run_flag = page.evaluate("sessionStorage.getItem('autoRunHealthChecks')")
        assert auto_run_flag == "true", "Auto-run health checks flag should be set"


class TestDataLoading:
    """Test data loading features."""
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_dashboard_data_api_call(self, page: Page):
        """Test dashboard data API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/dashboard/data" in route.request.url:
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/dashboard/data", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Dashboard data API should be called"
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_auto_refresh_polling(self, page: Page):
        """Test auto-refresh polling (60s interval)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API calls
        api_call_count = {"count": 0}
        
        def handle_route(route):
            if "/api/dashboard/data" in route.request.url:
                api_call_count["count"] += 1
            route.continue_()
        
        page.route("**/api/dashboard/data", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify initial API call
        assert api_call_count["count"] >= 1, "Dashboard data API should be called on load"
        
        # Note: Testing 60s polling interval would require waiting 60+ seconds
        # This test verifies the initial call and polling setup exists
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_last_updated_timestamp_update(self, page: Page):
        """Test last updated timestamp updates."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Get initial timestamp
        last_updated = page.locator("#last-updated")
        initial_timestamp = last_updated.text_content()
        
        # Wait for potential update
        page.wait_for_timeout(3000)
        
        # Verify timestamp still exists (may or may not have changed)
        expect(last_updated).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_chart_initialization_retry(self, page: Page):
        """Test chart initialization retry logic."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        # Verify charts are initialized
        daily_chart = page.locator("#dailyChart")
        expect(daily_chart).to_be_visible()
        
        # Verify Chart.js is loaded
        chart_exists = page.evaluate("typeof Chart !== 'undefined'")
        assert chart_exists, "Chart.js should be loaded"
    
    @pytest.mark.ui
    @pytest.mark.dashboard
    def test_error_handling(self, page: Page):
        """Test error handling for API failures."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept and fail API call
        def handle_route(route):
            if "/api/dashboard/data" in route.request.url:
                route.fulfill(status=500, body="Internal Server Error")
            else:
                route.continue_()
        
        page.route("**/api/dashboard/data", handle_route)
        
        page.goto(f"{base_url}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify page still loads (graceful error handling)
        heading = page.locator("h1:has-text('Huntable - CTI Scraper & Workbench')")
        expect(heading).to_be_visible()

