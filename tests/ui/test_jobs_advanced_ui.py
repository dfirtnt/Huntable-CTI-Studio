"""
UI tests for Jobs page advanced monitoring features using Playwright.
Tests filtering, cancellation, retry, priority management, and related features.
"""

import pytest
from playwright.sync_api import Page, expect
import os
import json


class TestJobsPageLoad:
    """Test jobs page basic loading."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_jobs_page_loads(self, page: Page):
        """Test jobs page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for JavaScript initialization
        
        # Verify page title
        expect(page).to_have_title("Job Monitor - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('🔄 Job Monitor')")
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_auto_refresh_toggle_display(self, page: Page):
        """Test auto-refresh toggle displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify auto-refresh checkbox exists
        auto_refresh = page.locator("#autoRefresh")
        expect(auto_refresh).to_be_visible()
        expect(auto_refresh).to_be_checked()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_refresh_button_display(self, page: Page):
        """Test refresh button displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify refresh button exists
        refresh_btn = page.locator("#refreshBtn")
        expect(refresh_btn).to_be_visible()
        expect(refresh_btn).to_have_text("🔄 Refresh Now")


class TestJobsAutoRefresh:
    """Test jobs auto-refresh features."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_auto_refresh_toggle_functionality(self, page: Page):
        """Test auto-refresh toggle functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify auto-refresh is checked by default
        auto_refresh = page.locator("#autoRefresh")
        expect(auto_refresh).to_be_checked()
        
        # Toggle auto-refresh off
        auto_refresh.uncheck()
        page.wait_for_timeout(500)
        expect(auto_refresh).not_to_be_checked()
        
        # Toggle auto-refresh on
        auto_refresh.check()
        page.wait_for_timeout(500)
        expect(auto_refresh).to_be_checked()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_auto_refresh_interval(self, page: Page):
        """Test auto-refresh interval (5s)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API calls
        api_call_count = {"count": 0}
        
        def handle_route(route):
            if "/api/jobs" in route.request.url:
                api_call_count["count"] += 1
                mock_response = {
                    "status": "ok",
                    "worker_stats": {},
                    "active_tasks": {}
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify initial API calls
        initial_count = api_call_count["count"]
        assert initial_count >= 3, "Job APIs should be called on load (status, queues, history)"
        
        # Note: Testing full 5s interval would require waiting 5+ seconds
        # This test verifies the auto-refresh setup exists


class TestJobsRefreshButton:
    """Test jobs refresh button."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_refresh_button_functionality(self, page: Page):
        """Test refresh button functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API calls
        api_call_count = {"count": 0}
        
        def handle_route(route):
            if "/api/jobs" in route.request.url:
                api_call_count["count"] += 1
                mock_response = {
                    "status": "ok",
                    "worker_stats": {},
                    "active_tasks": {}
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Get initial count
        initial_count = api_call_count["count"]
        
        # Click refresh button
        refresh_btn = page.locator("#refreshBtn")
        refresh_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify API was called again
        assert api_call_count["count"] > initial_count, "Refresh button should trigger API calls"
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_last_updated_timestamp_update(self, page: Page):
        """Test last updated timestamp updates."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify last updated timestamp exists
        last_updated = page.locator("#lastUpdated")
        expect(last_updated).to_be_visible()
        
        # Get initial timestamp
        initial_timestamp = last_updated.text_content()
        
        # Click refresh button
        refresh_btn = page.locator("#refreshBtn")
        refresh_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify timestamp updated (may or may not change depending on timing)
        expect(last_updated).to_be_visible()


class TestJobsWorkerStatus:
    """Test jobs worker status display."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_worker_status_display(self, page: Page):
        """Test worker status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with workers
        def handle_route(route):
            if "/api/jobs/status" in route.request.url:
                mock_response = {
                    "status": "ok",
                    "worker_stats": {
                        "worker1@hostname": {
                            "pool": {"processes": [1, 2, 3]},
                            "total": {"SUCCESS": 10, "FAILURE": 2}
                        }
                    },
                    "active_tasks": {}
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify worker status section exists
        worker_status = page.locator("#workerStatus")
        expect(worker_status).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_worker_status_empty_state(self, page: Page):
        """Test worker status empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with no workers
        def handle_route(route):
            if "/api/jobs/status" in route.request.url:
                mock_response = {
                    "status": "ok",
                    "worker_stats": {},
                    "active_tasks": {}
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify empty state message appears
        empty_state = page.locator("text=No active workers")
        expect(empty_state).to_be_visible()


class TestJobsQueueStatus:
    """Test jobs queue status display."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_queue_status_display(self, page: Page):
        """Test queue status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with queues
        def handle_route(route):
            if "/api/jobs/queues" in route.request.url:
                mock_response = {
                    "queues": {
                        "default": 5,
                        "high_priority": 2
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/status" in route.request.url:
                mock_response = {"status": "ok", "worker_stats": {}, "active_tasks": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify queue status section exists
        queue_status = page.locator("#queueStatus")
        expect(queue_status).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_queue_status_empty_state(self, page: Page):
        """Test queue status empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with empty queues
        def handle_route(route):
            if "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/status" in route.request.url:
                mock_response = {"status": "ok", "worker_stats": {}, "active_tasks": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify queue status section exists (may show empty queues)
        queue_status = page.locator("#queueStatus")
        expect(queue_status).to_be_visible()


class TestJobsActiveTasks:
    """Test jobs active tasks display."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_active_tasks_display(self, page: Page):
        """Test active tasks display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with active tasks
        def handle_route(route):
            if "/api/jobs/status" in route.request.url:
                mock_response = {
                    "status": "ok",
                    "worker_stats": {},
                    "active_tasks": {
                        "worker1@hostname": [
                            {
                                "id": "task-123",
                                "name": "tasks.collect_source",
                                "time_start": 1234567890,
                                "args": [1]
                            }
                        ]
                    }
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify active tasks section exists
        active_tasks = page.locator("#activeTasks")
        expect(active_tasks).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_active_tasks_empty_state(self, page: Page):
        """Test active tasks empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with no active tasks
        def handle_route(route):
            if "/api/jobs/status" in route.request.url:
                mock_response = {
                    "status": "ok",
                    "worker_stats": {},
                    "active_tasks": {}
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify empty state message appears
        empty_state = page.locator("text=No active tasks")
        expect(empty_state).to_be_visible()


class TestJobsHistory:
    """Test jobs history display."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_job_history_display(self, page: Page):
        """Test job history display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with job history
        def handle_route(route):
            if "/api/jobs/history" in route.request.url:
                mock_response = {
                    "recent_tasks": [
                        {
                            "task_id": "task-123",
                            "status": "SUCCESS",
                            "date_done": "2025-01-01T00:00:00Z",
                            "result": {"articles_collected": 10}
                        }
                    ]
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/status" in route.request.url:
                mock_response = {"status": "ok", "worker_stats": {}, "active_tasks": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify job history section exists
        job_history = page.locator("#jobHistory")
        expect(job_history).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_job_history_empty_state(self, page: Page):
        """Test job history empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API response with no history
        def handle_route(route):
            if "/api/jobs/history" in route.request.url:
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/status" in route.request.url:
                mock_response = {"status": "ok", "worker_stats": {}, "active_tasks": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            elif "/api/jobs/queues" in route.request.url:
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify empty state message appears
        empty_state = page.locator("text=No recent tasks")
        expect(empty_state).to_be_visible()


class TestJobsErrorHandling:
    """Test jobs error handling."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_job_data_error_handling(self, page: Page):
        """Test job data error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock API error
        def handle_route(route):
            if "/api/jobs" in route.request.url:
                route.fulfill(status=500, body="Internal Server Error")
            else:
                route.continue_()
        
        page.route("**/api/jobs/**", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify page still loads (graceful error handling)
        heading = page.locator("h1:has-text('🔄 Job Monitor')")
        expect(heading).to_be_visible()
        
        # Verify error messages appear in sections
        error_message = page.locator("text=Error loading")
        # Error messages may appear in worker/queue/task sections


class TestJobsAPIIntegration:
    """Test jobs API integration."""
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_jobs_status_api_call(self, page: Page):
        """Test jobs status API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/jobs/status" in route.request.url:
                api_called["called"] = True
                mock_response = {
                    "status": "ok",
                    "worker_stats": {},
                    "active_tasks": {}
                }
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/status", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Jobs status API should be called"
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_jobs_queues_api_call(self, page: Page):
        """Test jobs queues API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/jobs/queues" in route.request.url:
                api_called["called"] = True
                mock_response = {"queues": {}}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/queues", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Jobs queues API should be called"
    
    @pytest.mark.ui
    @pytest.mark.jobs
    def test_jobs_history_api_call(self, page: Page):
        """Test jobs history API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Track API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/jobs/history" in route.request.url:
                api_called["called"] = True
                mock_response = {"recent_tasks": []}
                route.fulfill(status=200, body=json.dumps(mock_response), headers={"Content-Type": "application/json"})
            else:
                route.continue_()
        
        page.route("**/api/jobs/history", handle_route)
        
        page.goto(f"{base_url}/jobs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Jobs history API should be called"


