import pytest
from playwright.sync_api import Page, expect
import time

class TestCTIScraperWebInterface:
    """End-to-end tests for CTIScraper web interface"""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Setup for each test"""
        page.goto("http://localhost:8000")
        page.wait_for_load_state("networkidle")
    
    def test_homepage_loads(self, page: Page):
        """Test that the homepage loads successfully"""
        expect(page).to_have_title("CTI Scraper")
        expect(page.locator("h1")).to_be_visible()
    
    def test_navigation_menu(self, page: Page):
        """Test navigation menu functionality"""
        # Check main navigation links
        expect(page.locator("nav")).to_be_visible()
        
        # Test sources page navigation
        page.click("text=Sources")
        expect(page).to_have_url("http://localhost:8000/sources")
        expect(page.locator("h1")).to_contain_text("Sources")
    
    def test_sources_page(self, page: Page):
        """Test sources page functionality"""
        page.goto("http://localhost:8000/sources")
        page.wait_for_load_state("networkidle")
        
        # Check sources table is visible
        expect(page.locator("table")).to_be_visible()
        
        # Check for Group-IB source (recently added)
        expect(page.locator("text=Group-IB")).to_be_visible()
        
        # Check source status indicators
        expect(page.locator(".status-indicator")).to_be_visible()
    
    def test_articles_page(self, page: Page):
        """Test articles page functionality"""
        page.goto("http://localhost:8000/articles")
        page.wait_for_load_state("networkidle")
        
        # Check articles table
        expect(page.locator("table")).to_be_visible()
        
        # Check for article content
        expect(page.locator(".article-title")).to_be_visible()
    
    def test_api_endpoints(self, page: Page):
        """Test API endpoints via browser"""
        # Test health endpoint
        response = page.request.get("http://localhost:8000/health")
        expect(response).to_be_ok()
        
        # Test sources API
        response = page.request.get("http://localhost:8000/api/sources")
        expect(response).to_be_ok()
        data = response.json()
        expect(data).to_have_property("sources")
    
    def test_search_functionality(self, page: Page):
        """Test search functionality"""
        page.goto("http://localhost:8000/articles")
        
        # Look for search input
        search_input = page.locator("input[type='search'], input[placeholder*='search']")
        if search_input.count() > 0:
            search_input.fill("threat")
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle")
            
            # Check results
            expect(page.locator(".search-results")).to_be_visible()
    
    def test_responsive_design(self, page: Page):
        """Test responsive design on mobile viewport"""
        page.set_viewport_size({"width": 375, "height": 667})  # iPhone SE
        
        page.goto("http://localhost:8000")
        
        # Check mobile navigation
        expect(page.locator("nav")).to_be_visible()
        
        # Check table responsiveness
        page.goto("http://localhost:8000/sources")
        expect(page.locator("table")).to_be_visible()
    
    def test_error_handling(self, page: Page):
        """Test error handling for invalid routes"""
        # Test 404 page
        page.goto("http://localhost:8000/nonexistent-page")
        
        # Should show error page or redirect
        expect(page.locator("body")).to_be_visible()
    
    def test_performance(self, page: Page):
        """Test page load performance"""
        start_time = time.time()
        page.goto("http://localhost:8000")
        page.wait_for_load_state("networkidle")
        load_time = time.time() - start_time
        
        # Page should load within 5 seconds
        assert load_time < 5.0, f"Page load time {load_time:.2f}s exceeds 5s limit"
    
    def test_accessibility(self, page: Page):
        """Test basic accessibility features"""
        page.goto("http://localhost:8000")
        
        # Check for alt text on images
        images = page.locator("img")
        for i in range(images.count()):
            img = images.nth(i)
            alt_text = img.get_attribute("alt")
            assert alt_text is not None, "Image missing alt text"
        
        # Check for proper heading hierarchy
        h1_count = page.locator("h1").count()
        assert h1_count == 1, f"Expected 1 h1, found {h1_count}"
    
    def test_threat_hunting_scoring(self, page: Page):
        """Test threat hunting scoring interface"""
        page.goto("http://localhost:8000/articles")
        
        # Look for scoring elements
        score_elements = page.locator(".threat-score, .score, [data-score]")
        if score_elements.count() > 0:
            expect(score_elements.first()).to_be_visible()
            
            # Check score values are numeric
            score_text = score_elements.first().text_content()
            assert score_text.replace(".", "").replace("-", "").isdigit(), "Score should be numeric"
    
    def test_source_management(self, page: Page):
        """Test source management functionality"""
        page.goto("http://localhost:8000/sources")
        
        # Check for source controls
        expect(page.locator("table")).to_be_visible()
        
        # Check for active/inactive indicators
        status_indicators = page.locator(".status-indicator, .active, .inactive")
        if status_indicators.count() > 0:
            expect(status_indicators.first()).to_be_visible()
    
    def test_data_export(self, page: Page):
        """Test data export functionality"""
        page.goto("http://localhost:8000/articles")
        
        # Look for export buttons
        export_buttons = page.locator("button:has-text('Export'), a:has-text('Export'), .export-btn")
        if export_buttons.count() > 0:
            # Test export functionality
            with page.expect_download() as download_info:
                export_buttons.first().click()
            download = download_info.value
            assert download.suggested_filename.endswith(('.csv', '.json', '.xlsx')), "Export should be a data file"
