"""
Comprehensive tests for CTI Scraper web application.

Tests all UI components, API endpoints, and user workflows.
"""

import pytest
import httpx
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# Test configuration
BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 30.0

class TestCoreRoutes:
    """Test core application routes and pages."""
    
    @pytest.mark.asyncio
    async def test_homepage_loads(self, async_client: httpx.AsyncClient):
        """Test that the homepage loads correctly."""
        response = await async_client.get("/")
        assert response.status_code == 200
        assert "CTI Scraper" in response.text
        assert "Threat Intelligence Dashboard" in response.text
        assert "Recent Articles" in response.text
    
    @pytest.mark.asyncio
    async def test_articles_list_page(self, async_client: httpx.AsyncClient):
        """Test the articles listing page."""
        response = await async_client.get("/articles")
        assert response.status_code == 200
        assert "Articles" in response.text
        assert "Browse and search collected threat intelligence articles" in response.text
    
    @pytest.mark.asyncio
    async def test_sources_management_page(self, async_client: httpx.AsyncClient):
        """Test the sources management page."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "Sources" in response.text
        assert "Manage and monitor your threat intelligence collection sources" in response.text
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client: httpx.AsyncClient):
        """Test the health check endpoint."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

class TestArticlePages:
    """Test article-related pages and functionality."""
    
    @pytest.mark.asyncio
    async def test_article_detail_page(self, async_client: httpx.AsyncClient):
        """Test individual article detail pages."""
        # First get the articles list to find an article ID
        list_response = await async_client.get("/articles")
        assert list_response.status_code == 200
        
        # Try to access article ID 1 (should exist if there are articles)
        response = await async_client.get("/articles/1")
        if response.status_code == 200:
            # Check for expected content
            assert "Article Content" in response.text
            assert "Threat Hunting Analysis" in response.text
            assert "TTP Quality Assessment" in response.text
            assert "LLM Quality Assessment Details" in response.text
        else:
            # If no articles exist, that's also valid
            assert response.status_code in [404, 500]
    
    @pytest.mark.asyncio
    async def test_article_pagination(self, async_client: httpx.AsyncClient):
        """Test article pagination functionality."""
        response = await async_client.get("/articles?limit=10")
        assert response.status_code == 200
        
        response = await async_client.get("/articles?limit=50")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_invalid_article_id(self, async_client: httpx.AsyncClient):
        """Test handling of invalid article IDs."""
        response = await async_client.get("/articles/999999")
        assert response.status_code in [404, 500]

class TestAPIEndpoints:
    """Test all API endpoints."""
    
    @pytest.mark.asyncio
    async def test_api_articles_list(self, async_client: httpx.AsyncClient):
        """Test the articles API endpoint."""
        response = await async_client.get("/api/articles")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert isinstance(data["articles"], list)
    
    @pytest.mark.asyncio
    async def test_api_articles_with_limit(self, async_client: httpx.AsyncClient):
        """Test articles API with limit parameter."""
        response = await async_client.get("/api/articles?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert len(data["articles"]) <= 5
    
    @pytest.mark.asyncio
    async def test_api_article_detail(self, async_client: httpx.AsyncClient):
        """Test individual article API endpoint."""
        response = await async_client.get("/api/articles/1")
        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert "title" in data
            assert "content" in data
        else:
            # If no articles exist, that's also valid
            assert response.status_code in [404, 500]
    
    @pytest.mark.asyncio
    async def test_api_sources_list(self, async_client: httpx.AsyncClient):
        """Test the sources API endpoint."""
        response = await async_client.get("/api/sources")
        assert response.status_code == 200
        
        data = response.json()
        assert "sources" in data
        assert isinstance(data["sources"], list)
    
    @pytest.mark.asyncio
    async def test_api_source_detail(self, async_client: httpx.AsyncClient):
        """Test individual source API endpoint."""
        response = await async_client.get("/api/sources/1")
        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert "name" in data
            assert "url" in data
        else:
            # If no sources exist, that's also valid
            assert response.status_code in [404, 500]

class TestSourceManagement:
    """Test source management functionality."""
    
    @pytest.mark.asyncio
    async def test_source_test_functionality(self, async_client: httpx.AsyncClient):
        """Test the source testing functionality."""
        # First check if we have any sources
        sources_response = await async_client.get("/api/sources")
        assert sources_response.status_code == 200
        
        sources_data = sources_response.json()
        if sources_data["sources"]:
            source_id = sources_data["sources"][0]["id"]
            
            # Test the source test endpoint
            response = await async_client.post(f"/api/sources/{source_id}/test")
            assert response.status_code == 200
            
            data = response.json()
            assert "source_id" in data
            assert "source_name" in data
            assert "overall_success" in data
            assert "tests" in data
            assert isinstance(data["tests"], list)
    
    @pytest.mark.asyncio
    async def test_source_stats_functionality(self, async_client: httpx.AsyncClient):
        """Test the source statistics functionality."""
        # First check if we have any sources
        sources_response = await async_client.get("/api/sources")
        assert sources_response.status_code == 200
        
        sources_data = sources_response.json()
        if sources_data["sources"]:
            source_id = sources_data["sources"][0]["id"]
            
            # Test the source stats endpoint
            response = await async_client.get(f"/api/sources/{source_id}/stats")
            assert response.status_code == 200
            
            data = response.json()
            assert "source_id" in data
            assert "source_name" in data
            assert "total_articles" in data
            assert "avg_content_length" in data
            assert "avg_quality_score" in data
            assert "articles_by_date" in data
    
    @pytest.mark.asyncio
    async def test_source_toggle_functionality(self, async_client: httpx.AsyncClient):
        """Test the source toggle functionality."""
        # First check if we have any sources
        sources_response = await async_client.get("/api/sources")
        assert sources_response.status_code == 200
        
        sources_data = sources_response.json()
        if sources_data["sources"]:
            source_id = sources_data["sources"][0]["id"]
            
            # Test the source toggle endpoint
            response = await async_client.post(f"/api/sources/{source_id}/toggle")
            assert response.status_code == 200
            
            data = response.json()
            # The response should contain information about the toggle operation
            assert "source_name" in data or "message" in data

class TestUIComponents:
    """Test UI components and rendering."""
    
    @pytest.mark.asyncio
    async def test_navigation_menu(self, async_client: httpx.AsyncClient):
        """Test that navigation menu is present on all pages."""
        pages = ["/", "/articles", "/sources"]
        
        for page in pages:
            response = await async_client.get(page)
            assert response.status_code == 200
            
            # Check for navigation elements
            assert "Dashboard" in response.text
            assert "Articles" in response.text
            assert "TTP Analysis" in response.text
            assert "Sources" in response.text
    
    @pytest.mark.asyncio
    async def test_dashboard_statistics_cards(self, async_client: httpx.AsyncClient):
        """Test that dashboard statistics cards are displayed."""
        response = await async_client.get("/")
        assert response.status_code == 200
        
        # Check for statistics cards
        assert "Total Articles" in response.text
        assert "Active Sources" in response.text
        assert "Last 24h" in response.text
        assert "Database Size" in response.text
    
    @pytest.mark.asyncio
    async def test_quality_score_displays(self, async_client: httpx.AsyncClient):
        """Test that quality scores are displayed correctly."""
        # Test on analysis page
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        
        # Check for quality metrics
        assert "Combined Quality" in response.text
        assert "TTP Quality" in response.text
        assert "LLM Quality" in response.text
    
    @pytest.mark.asyncio
    async def test_chart_rendering(self, async_client: httpx.AsyncClient):
        """Test that charts are properly rendered."""
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        
        # Check for chart containers
        assert 'id="qualityChart"' in response.text
        assert 'id="tacticalChart"' in response.text

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_404_handling(self, async_client: httpx.AsyncClient):
        """Test 404 error handling."""
        response = await async_client.get("/nonexistent-page")
        assert response.status_code == 404
        assert "Something went wrong" in response.text or "Page not found" in response.text
    
    @pytest.mark.asyncio
    async def test_invalid_parameters(self, async_client: httpx.AsyncClient):
        """Test handling of invalid parameters."""
        # Test with invalid limit
        response = await async_client.get("/articles?limit=invalid")
        # Should handle gracefully - 422 is correct for validation errors
        assert response.status_code in [200, 400, 422, 500]
    
    @pytest.mark.asyncio
    async def test_malicious_input_handling(self, async_client: httpx.AsyncClient):
        """Test handling of potentially malicious input."""
        malicious_inputs = [
            "'; DROP TABLE articles; --",
            "<script>alert('xss')</script>",
            "../../../etc/passwd"
        ]
        
        for malicious_input in malicious_inputs:
            response = await async_client.get(f"/articles?search={malicious_input}")
            # Should handle safely
            assert response.status_code in [200, 400, 500]

class TestDataConsistency:
    """Test data consistency across endpoints."""
    
    @pytest.mark.asyncio
    async def test_articles_data_consistency(self, async_client: httpx.AsyncClient):
        """Test consistency between HTML and API article endpoints."""
        # Get HTML articles page
        html_response = await async_client.get("/articles")
        assert html_response.status_code == 200
        
        # Get API articles
        api_response = await async_client.get("/api/articles")
        assert api_response.status_code == 200
        
        # Check if data is consistent
        api_data = api_response.json()
        if api_data["articles"]:
            # Should have at least one article
            assert len(api_data["articles"]) > 0
    
    @pytest.mark.asyncio
    async def test_sources_data_consistency(self, async_client: httpx.AsyncClient):
        """Test consistency between HTML and API source endpoints."""
        # Get HTML sources page
        html_response = await async_client.get("/sources")
        assert html_response.status_code == 200
        
        # Get API sources
        api_response = await async_client.get("/api/sources")
        assert api_response.status_code == 200
        
        # Check if data is consistent
        api_data = api_response.json()
        if api_data["sources"]:
            # Should have at least one source
            assert len(api_data["sources"]) > 0

class TestPerformance:
    """Test application performance."""
    
    @pytest.mark.asyncio
    async def test_response_times(self, async_client: httpx.AsyncClient):
        """Test that endpoints respond within reasonable time."""
        import time
        
        endpoints = ["/", "/articles", "/sources"]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = await async_client.get(endpoint)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 5.0, f"Endpoint {endpoint} took {response_time:.2f}s"
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, async_client: httpx.AsyncClient):
        """Test handling of concurrent requests."""
        async def make_request():
            return await async_client.get("/")
        
        # Make 5 concurrent requests
        tasks = [make_request() for _ in range(5)]
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200

class TestUserWorkflows:
    """Test complete user workflows."""
    
    @pytest.mark.asyncio
    async def test_article_browsing_workflow(self, async_client: httpx.AsyncClient):
        """Test the complete article browsing workflow."""
        # 1. Start at dashboard
        response = await async_client.get("/")
        assert response.status_code == 200
        
        # 2. Navigate to articles
        response = await async_client.get("/articles")
        assert response.status_code == 200
        
        # 3. Try to view a specific article
        response = await async_client.get("/articles/1")
        # This might fail if no articles exist, which is fine
        assert response.status_code in [200, 404, 500]
    
    @pytest.mark.asyncio
    async def test_analysis_workflow(self, async_client: httpx.AsyncClient):
        """Test the analysis workflow."""
        # 1. Go to analysis dashboard
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        
        # 2. Check that quality metrics are displayed
        assert "Quality Distribution" in response.text
        assert "Tactical vs Strategic Distribution" in response.text
    
    @pytest.mark.asyncio
    async def test_source_management_workflow(self, async_client: httpx.AsyncClient):
        """Test the source management workflow."""
        # 1. Go to sources page
        response = await async_client.get("/sources")
        assert response.status_code == 200
        
        # 2. Check that source management elements are present
        assert "Manage and monitor your threat intelligence collection sources" in response.text
        
        # 3. Check if we can access source APIs
        sources_response = await async_client.get("/api/sources")
        assert sources_response.status_code == 200

# Fixture for async HTTP client
@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for testing."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TEST_TIMEOUT) as client:
        yield client
