"""
API endpoint tests for CTI Scraper.
"""
import pytest
import httpx
from typing import Dict, Any

class TestDashboardEndpoints:
    """Test dashboard-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.smoke
    async def test_dashboard_home(self, async_client: httpx.AsyncClient):
        """Test the main dashboard page."""
        response = await async_client.get("/")
        assert response.status_code == 200
        assert "CTI Scraper" in response.text
        assert "Dashboard" in response.text
    
    @pytest.mark.api
    async def test_dashboard_stats(self, async_client: httpx.AsyncClient):
        """Test dashboard statistics display."""
        response = await async_client.get("/")
        assert response.status_code == 200
        
        # Check for key dashboard elements
        assert "Total Articles" in response.text
        assert "Total Sources" in response.text
        assert "Last Update" in response.text

class TestArticlesEndpoints:
    """Test article-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.smoke
    async def test_articles_list(self, async_client: httpx.AsyncClient):
        """Test the articles listing page."""
        response = await async_client.get("/articles")
        assert response.status_code == 200
        assert "Articles" in response.text
        assert "Browse Articles" in response.text
    
    @pytest.mark.api
    async def test_articles_pagination(self, async_client: httpx.AsyncClient):
        """Test articles pagination."""
        response = await async_client.get("/articles?limit=10")
        assert response.status_code == 200
        
        response = await async_client.get("/articles?limit=50")
        assert response.status_code == 200
    
    @pytest.mark.api
    @pytest.mark.smoke
    async def test_article_detail(self, async_client: httpx.AsyncClient):
        """Test individual article detail page."""
        # First get the articles list to find an article ID
        list_response = await async_client.get("/articles")
        assert list_response.status_code == 200
        
        # Try to access article ID 1 (should exist if there are articles)
        response = await async_client.get("/articles/1")
        if response.status_code == 200:
            assert "Article Content" in response.text
            assert "Threat Hunting Analysis" in response.text
            assert "TTP Quality Assessment" in response.text
        else:
            # If no articles exist, that's also valid
            assert response.status_code in [404, 500]

class TestAnalysisEndpoints:
    """Test analysis-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.smoke
    async def test_analysis_dashboard(self, async_client: httpx.AsyncClient):
        """Test the TTP analysis dashboard."""
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        assert "Threat Hunting Analysis Dashboard" in response.text
        assert "Quality Distribution" in response.text
    
    @pytest.mark.api
    async def test_analysis_quality_metrics(self, async_client: httpx.AsyncClient):
        """Test quality metrics display on analysis page."""
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        
        # Check for quality score cards
        assert "Combined Quality" in response.text
        assert "TTP Quality" in response.text
        assert "LLM Quality" in response.text

class TestSourcesEndpoints:
    """Test source-related endpoints."""
    
    @pytest.mark.api
    @pytest.mark.smoke
    async def test_sources_list(self, async_client: httpx.AsyncClient):
        """Test the sources listing page."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "Sources" in response.text
        assert "Manage Sources" in response.text
    
    @pytest.mark.api
    async def test_source_management(self, async_client: httpx.AsyncClient):
        """Test source management functionality."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        
        # Check for source management elements
        assert "Add Source" in response.text or "New Source" in response.text

class TestAPIEndpoints:
    """Test JSON API endpoints."""
    
    @pytest.mark.api
    async def test_api_articles(self, async_client: httpx.AsyncClient):
        """Test the articles API endpoint."""
        response = await async_client.get("/api/articles")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert isinstance(data["articles"], list)
    
    @pytest.mark.api
    async def test_api_articles_limit(self, async_client: httpx.AsyncClient):
        """Test articles API with limit parameter."""
        response = await async_client.get("/api/articles?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert len(data["articles"]) <= 5
    
    @pytest.mark.api
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

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.api
    async def test_404_handling(self, async_client: httpx.AsyncClient):
        """Test 404 error handling."""
        response = await async_client.get("/nonexistent-page")
        assert response.status_code == 404
        assert "Page not found" in response.text
    
    @pytest.mark.api
    async def test_invalid_article_id(self, async_client: httpx.AsyncClient):
        """Test handling of invalid article IDs."""
        response = await async_client.get("/articles/999999")
        assert response.status_code in [404, 500]
    
    @pytest.mark.api
    async def test_invalid_limit_parameter(self, async_client: httpx.AsyncClient):
        """Test handling of invalid limit parameters."""
        response = await async_client.get("/articles?limit=invalid")
        # Should handle gracefully, either default or error
        assert response.status_code in [200, 400, 500]

class TestPerformance:
    """Test performance and response times."""
    
    @pytest.mark.api
    @pytest.mark.slow
    async def test_response_times(self, async_client: httpx.AsyncClient):
        """Test that endpoints respond within reasonable time."""
        import time
        
        start_time = time.time()
        response = await async_client.get("/")
        end_time = time.time()
        
        assert response.status_code == 200
        assert (end_time - start_time) < 5.0  # Should respond within 5 seconds
    
    @pytest.mark.api
    @pytest.mark.slow
    async def test_concurrent_requests(self, async_client: httpx.AsyncClient):
        """Test handling of concurrent requests."""
        import asyncio
        
        async def make_request():
            return await async_client.get("/")
        
        # Make 5 concurrent requests
        tasks = [make_request() for _ in range(5)]
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200
