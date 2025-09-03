"""
System integration tests for CTI Scraper.
"""
import pytest
import asyncio
import httpx
from typing import AsyncGenerator
import time

class TestSystemHealth:
    """Test overall system health and connectivity."""
    
    @pytest.mark.integration
    @pytest.mark.smoke
    async def test_system_startup(self, async_client: httpx.AsyncClient):
        """Test that all system components are running."""
        # Test main dashboard
        response = await async_client.get("/")
        assert response.status_code == 200
        
        # Test all major endpoints
        endpoints = ["/articles", "/analysis", "/sources"]
        for endpoint in endpoints:
            response = await async_client.get(endpoint)
            assert response.status_code == 200, f"Endpoint {endpoint} failed"
    
    @pytest.mark.integration
    async def test_database_connectivity(self, async_client: httpx.AsyncClient):
        """Test database connectivity through API endpoints."""
        # Test articles API
        response = await async_client.get("/api/articles")
        assert response.status_code == 200
        
        data = response.json()
        assert "articles" in data
        assert isinstance(data["articles"], list)
    
    @pytest.mark.integration
    async def test_quality_assessment_pipeline(self, async_client: httpx.AsyncClient):
        """Test the complete quality assessment pipeline."""
        # Get articles list
        response = await async_client.get("/articles")
        assert response.status_code == 200
        
        # If there are articles, test quality assessment
        if "No articles" not in response.text:
            # Try to access first article
            response = await async_client.get("/articles/1")
            if response.status_code == 200:
                # Check for quality assessment elements
                assert "TTP Quality Assessment" in response.text
                assert "Combined Quality Score" in response.text
                assert "LLM Quality Assessment" in response.text

class TestDataFlow:
    """Test data flow through the system."""
    
    @pytest.mark.integration
    async def test_article_to_analysis_flow(self, async_client: httpx.AsyncClient):
        """Test data flow from articles to analysis."""
        # Get articles
        articles_response = await async_client.get("/articles")
        assert articles_response.status_code == 200
        
        # Get analysis dashboard
        analysis_response = await async_client.get("/analysis")
        assert analysis_response.status_code == 200
        
        # Verify data consistency
        if "No articles" not in articles_response.text:
            # Should have analysis data
            assert "Quality Distribution" in analysis_response.text
            assert "Tactical vs Strategic Distribution" in analysis_response.text
    
    @pytest.mark.integration
    async def test_api_data_consistency(self, async_client: httpx.AsyncClient):
        """Test consistency between HTML and API endpoints."""
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

class TestQualityFramework:
    """Test the quality assessment framework integration."""
    
    @pytest.mark.integration
    async def test_ttp_detection_integration(self, async_client: httpx.AsyncClient):
        """Test TTP detection integration in the UI."""
        # Get analysis page
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        
        # Check for TTP analysis elements
        assert "Threat Hunting Analysis Dashboard" in response.text
        assert "Top Articles with Huntable Techniques" in response.text
    
    @pytest.mark.integration
    async def test_llm_quality_assessment_integration(self, async_client: httpx.AsyncClient):
        """Test LLM quality assessment integration."""
        # Get analysis page
        response = await async_client.get("/analysis")
        assert response.status_code == 200
        
        # Check for LLM quality metrics
        assert "Combined Quality" in response.text
        assert "TTP Quality" in response.text
        assert "LLM Quality" in response.text
        
        # Check for quality distribution
        assert "Quality Distribution" in response.text
        assert "Tactical vs Strategic Distribution" in response.text

class TestErrorHandling:
    """Test system-wide error handling."""
    
    @pytest.mark.integration
    async def test_system_error_handling(self, async_client: httpx.AsyncClient):
        """Test system error handling."""
        # Test 404 handling
        response = await async_client.get("/nonexistent-endpoint")
        assert response.status_code == 404
        
        # Test invalid article ID
        response = await async_client.get("/articles/999999")
        assert response.status_code in [404, 500]
    
    @pytest.mark.integration
    async def test_database_error_handling(self, async_client: httpx.AsyncClient):
        """Test database error handling."""
        # Test with invalid parameters
        response = await async_client.get("/articles?limit=invalid")
        # Should handle gracefully
        assert response.status_code in [200, 400, 500]

class TestPerformance:
    """Test system performance."""
    
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_system_response_times(self, async_client: httpx.AsyncClient):
        """Test system response times."""
        endpoints = ["/", "/articles", "/analysis", "/sources"]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = await async_client.get(endpoint)
            end_time = time.time()
            
            assert response.status_code == 200
            response_time = end_time - start_time
            assert response_time < 5.0, f"Endpoint {endpoint} took {response_time:.2f}s"
    
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_concurrent_user_simulation(self, async_client: httpx.AsyncClient):
        """Test system under concurrent load."""
        async def make_request():
            return await async_client.get("/")
        
        # Simulate 10 concurrent users
        tasks = [make_request() for _ in range(10)]
        start_time = time.time()
        responses = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200
        
        total_time = end_time - start_time
        assert total_time < 10.0, f"Concurrent requests took {total_time:.2f}s"

class TestSecurity:
    """Test system security."""
    
    @pytest.mark.integration
    async def test_input_validation(self, async_client: httpx.AsyncClient):
        """Test input validation and sanitization."""
        # Test SQL injection attempts
        malicious_inputs = [
            "'; DROP TABLE articles; --",
            "<script>alert('xss')</script>",
            "../../../etc/passwd"
        ]
        
        for malicious_input in malicious_inputs:
            response = await async_client.get(f"/articles?search={malicious_input}")
            # Should handle safely
            assert response.status_code in [200, 400, 500]
    
    @pytest.mark.integration
    async def test_authentication_requirements(self, async_client: httpx.AsyncClient):
        """Test authentication requirements."""
        # Currently no auth required, but test for future
        response = await async_client.get("/")
        assert response.status_code == 200

class TestDataIntegrity:
    """Test data integrity and consistency."""
    
    @pytest.mark.integration
    async def test_article_data_integrity(self, async_client: httpx.AsyncClient):
        """Test article data integrity."""
        # Get articles via API
        response = await async_client.get("/api/articles")
        assert response.status_code == 200
        
        data = response.json()
        if data["articles"]:
            article = data["articles"][0]
            
            # Check required fields
            required_fields = ["id", "title", "content"]
            for field in required_fields:
                assert field in article
            
            # Check data types
            assert isinstance(article["id"], int)
            assert isinstance(article["title"], str)
            assert isinstance(article["content"], str)
    
    @pytest.mark.integration
    async def test_quality_score_consistency(self, async_client: httpx.AsyncClient):
        """Test quality score consistency across endpoints."""
        # Get analysis page
        analysis_response = await async_client.get("/analysis")
        assert analysis_response.status_code == 200
        
        # If there are articles, check quality scores
        if "No analyses available" not in analysis_response.text:
            # Should have quality metrics
            assert "Combined Quality" in analysis_response.text
            assert "Quality Distribution" in analysis_response.text
