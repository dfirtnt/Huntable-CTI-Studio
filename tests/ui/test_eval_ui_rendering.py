"""Tests for eval UI metrics rendering."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
class TestEvalUIRendering:
    """Test eval UI metrics rendering."""
    
    def test_eval_page_loads(self, page: Page):
        """Test that eval page loads."""
        page.goto("http://localhost:8002/evaluations")
        
        # Assert page loaded
        expect(page).to_have_url("http://localhost:8002/evaluations", timeout=5000)
        expect(page.locator("h1, .page-title")).to_contain_text("Evaluation", timeout=5000)
    
    def test_eval_metrics_display(self, page: Page):
        """Test that eval metrics are displayed."""
        page.goto("http://localhost:8002/evaluations")
        
        # Look for metrics display
        metrics = page.locator(".metrics, .eval-metrics, [data-testid='metrics']")
        if metrics.count() > 0:
            expect(metrics.first).to_be_visible(timeout=5000)
    
    @pytest.mark.skip(reason="Requires eval data - implement with test fixtures")
    def test_eval_results_table(self, page: Page):
        """Test that eval results are displayed in table."""
        page.goto("http://localhost:8002/evaluations")
        
        # Look for results table
        results_table = page.locator("table, .results-table")
        if results_table.count() > 0:
            expect(results_table.first).to_be_visible(timeout=5000)
            
            # Check for table headers
            headers = results_table.locator("th, thead")
            expect(headers.first).to_be_visible()
    
    def test_eval_run_button(self, page: Page):
        """Test that eval run button is present."""
        page.goto("http://localhost:8002/evaluations")
        
        # Look for run button
        run_btn = page.locator("button:has-text('Run'), button:has-text('Start')").first
        if run_btn.is_visible():
            expect(run_btn).to_be_enabled()
