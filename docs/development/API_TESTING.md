# 🔌 API Testing

Comprehensive guide for testing CTI Scraper REST API endpoints.

## 🎯 Overview

This guide covers testing the CTI Scraper REST API endpoints, including request/response validation, error handling, and data consistency verification.

## 🛠️ Setup and Dependencies

### Required Dependencies
```bash
# Install API testing dependencies
pip install httpx pytest-asyncio pytest-httpx
```

### Configuration
```python
# conftest.py
import pytest
import httpx
from typing import AsyncGenerator

@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API testing."""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        yield client

@pytest.fixture
def api_headers():
    """Default API headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
```

## 🧪 Basic API Tests

### Health Check
```python
@pytest.mark.api
async def test_health_endpoint(async_client: httpx.AsyncClient):
    """Test health check endpoint."""
    response = await async_client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
```

### Articles API
```python
@pytest.mark.api
async def test_articles_endpoint(async_client: httpx.AsyncClient):
    """Test articles API endpoint."""
    response = await async_client.get("/api/articles")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "articles" in data
    assert isinstance(data["articles"], list)
    
    # Verify article structure
    if data["articles"]:
        article = data["articles"][0]
        required_fields = ["id", "title", "url", "content", "threat_score"]
        for field in required_fields:
            assert field in article
```

### Sources API
```python
@pytest.mark.api
async def test_sources_endpoint(async_client: httpx.AsyncClient):
    """Test sources API endpoint."""
    response = await async_client.get("/api/sources")
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "sources" in data
    assert isinstance(data["sources"], list)
    
    # Verify source structure
    if data["sources"]:
        source = data["sources"][0]
        required_fields = ["id", "name", "url", "type", "active"]
        for field in required_fields:
            assert field in source
```

## 📊 Data Validation Tests

### Article Data Validation
```python
@pytest.mark.api
async def test_article_data_validation(async_client: httpx.AsyncClient):
    """Test article data validation."""
    response = await async_client.get("/api/articles")
    assert response.status_code == 200
    
    data = response.json()
    articles = data["articles"]
    
    for article in articles:
        # Validate required fields
        assert article["id"] is not None
        assert isinstance(article["id"], int)
        assert article["title"] is not None
        assert isinstance(article["title"], str)
        assert len(article["title"]) > 0
        
        # Validate URL format
        assert article["url"].startswith("http")
        
        # Validate threat score
        assert article["threat_score"] is not None
        assert isinstance(article["threat_score"], (int, float))
        assert 0 <= article["threat_score"] <= 100
        
        # Validate timestamps
        assert "created_at" in article
        assert "updated_at" in article
```

### Source Data Validation
```python
@pytest.mark.api
async def test_source_data_validation(async_client: httpx.AsyncClient):
    """Test source data validation."""
    response = await async_client.get("/api/sources")
    assert response.status_code == 200
    
    data = response.json()
    sources = data["sources"]
    
    for source in sources:
        # Validate required fields
        assert source["id"] is not None
        assert isinstance(source["id"], int)
        assert source["name"] is not None
        assert isinstance(source["name"], str)
        assert len(source["name"]) > 0
        
        # Validate URL format
        assert source["url"].startswith("http")
        
        # Validate source type
        valid_types = ["rss", "atom", "json", "scraping"]
        assert source["type"] in valid_types
        
        # Validate active status
        assert isinstance(source["active"], bool)
```

## 🔍 Query Parameter Testing

### Pagination
```python
@pytest.mark.api
async def test_articles_pagination(async_client: httpx.AsyncClient):
    """Test articles pagination."""
    # Test first page
    response = await async_client.get("/api/articles?page=1&limit=10")
    assert response.status_code == 200
    
    data = response.json()
    assert "articles" in data
    assert "pagination" in data
    
    pagination = data["pagination"]
    assert "page" in pagination
    assert "limit" in pagination
    assert "total" in pagination
    assert "pages" in pagination
    
    # Test second page
    response = await async_client.get("/api/articles?page=2&limit=10")
    assert response.status_code == 200
    
    # Test invalid page
    response = await async_client.get("/api/articles?page=0")
    assert response.status_code == 400
```

### Filtering
```python
@pytest.mark.api
async def test_articles_filtering(async_client: httpx.AsyncClient):
    """Test articles filtering."""
    # Test threat score filter
    response = await async_client.get("/api/articles?min_threat_score=50")
    assert response.status_code == 200
    
    data = response.json()
    for article in data["articles"]:
        assert article["threat_score"] >= 50
    
    # Test date range filter
    response = await async_client.get("/api/articles?start_date=2024-01-01&end_date=2024-12-31")
    assert response.status_code == 200
    
    # Test source filter
    response = await async_client.get("/api/articles?source_id=1")
    assert response.status_code == 200
```

### Search
```python
@pytest.mark.api
async def test_articles_search(async_client: httpx.AsyncClient):
    """Test articles search functionality."""
    # Test text search
    response = await async_client.get("/api/articles?search=malware")
    assert response.status_code == 200
    
    data = response.json()
    # Verify search results contain search term
    for article in data["articles"]:
        content = (article["title"] + " " + article["content"]).lower()
        assert "malware" in content
    
    # Test empty search
    response = await async_client.get("/api/articles?search=")
    assert response.status_code == 200
    
    # Test special characters
    response = await async_client.get("/api/articles?search=test%20query")
    assert response.status_code == 200
```

## 📝 CRUD Operations Testing

### Create Source
```python
@pytest.mark.api
async def test_create_source(async_client: httpx.AsyncClient, api_headers):
    """Test creating a new source."""
    source_data = {
        "name": "Test Source",
        "url": "https://example.com/feed.xml",
        "type": "rss",
        "active": True
    }
    
    response = await async_client.post(
        "/api/sources",
        json=source_data,
        headers=api_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify created source
    assert data["name"] == "Test Source"
    assert data["url"] == "https://example.com/feed.xml"
    assert data["type"] == "rss"
    assert data["active"] is True
    assert "id" in data
```

### Update Source
```python
@pytest.mark.api
async def test_update_source(async_client: httpx.AsyncClient, api_headers):
    """Test updating an existing source."""
    # First create a source
    source_data = {
        "name": "Original Source",
        "url": "https://example.com/feed.xml",
        "type": "rss",
        "active": True
    }
    
    create_response = await async_client.post(
        "/api/sources",
        json=source_data,
        headers=api_headers
    )
    source_id = create_response.json()["id"]
    
    # Update the source
    update_data = {
        "name": "Updated Source",
        "active": False
    }
    
    response = await async_client.put(
        f"/api/sources/{source_id}",
        json=update_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify updated source
    assert data["name"] == "Updated Source"
    assert data["active"] is False
    assert data["url"] == "https://example.com/feed.xml"  # Unchanged
```

### Delete Source
```python
@pytest.mark.api
async def test_delete_source(async_client: httpx.AsyncClient):
    """Test deleting a source."""
    # First create a source
    source_data = {
        "name": "Source to Delete",
        "url": "https://example.com/feed.xml",
        "type": "rss",
        "active": True
    }
    
    create_response = await async_client.post(
        "/api/sources",
        json=source_data
    )
    source_id = create_response.json()["id"]
    
    # Delete the source
    response = await async_client.delete(f"/api/sources/{source_id}")
    assert response.status_code == 204
    
    # Verify source is deleted
    response = await async_client.get(f"/api/sources/{source_id}")
    assert response.status_code == 404
```

## 🚨 Error Handling Tests

### Invalid Endpoints
```python
@pytest.mark.api
async def test_invalid_endpoints(async_client: httpx.AsyncClient):
    """Test invalid endpoint handling."""
    # Test non-existent endpoint
    response = await async_client.get("/api/nonexistent")
    assert response.status_code == 404
    
    # Test invalid method
    response = await async_client.post("/api/articles")
    assert response.status_code == 405  # Method not allowed
```

### Invalid Data
```python
@pytest.mark.api
async def test_invalid_data_handling(async_client: httpx.AsyncClient, api_headers):
    """Test invalid data handling."""
    # Test missing required fields
    invalid_data = {"name": "Test Source"}  # Missing URL
    
    response = await async_client.post(
        "/api/sources",
        json=invalid_data,
        headers=api_headers
    )
    assert response.status_code == 400
    
    # Test invalid URL format
    invalid_data = {
        "name": "Test Source",
        "url": "not-a-valid-url",
        "type": "rss"
    }
    
    response = await async_client.post(
        "/api/sources",
        json=invalid_data,
        headers=api_headers
    )
    assert response.status_code == 400
    
    # Test invalid source type
    invalid_data = {
        "name": "Test Source",
        "url": "https://example.com/feed.xml",
        "type": "invalid-type"
    }
    
    response = await async_client.post(
        "/api/sources",
        json=invalid_data,
        headers=api_headers
    )
    assert response.status_code == 400
```

### Authentication Errors
```python
@pytest.mark.api
async def test_authentication_errors(async_client: httpx.AsyncClient):
    """Test authentication error handling."""
    # Test without authentication
    response = await async_client.get("/api/admin/sources")
    assert response.status_code == 401
    
    # Test with invalid token
    headers = {"Authorization": "Bearer invalid-token"}
    response = await async_client.get("/api/admin/sources", headers=headers)
    assert response.status_code == 401
```

## ⚡ Performance Tests

### Response Time Testing
```python
@pytest.mark.api
async def test_api_response_times(async_client: httpx.AsyncClient):
    """Test API response times."""
    import time
    
    # Test articles endpoint response time
    start_time = time.time()
    response = await async_client.get("/api/articles")
    response_time = time.time() - start_time
    
    assert response.status_code == 200
    assert response_time < 2.0, f"Response time {response_time}s exceeds 2s limit"
    
    # Test sources endpoint response time
    start_time = time.time()
    response = await async_client.get("/api/sources")
    response_time = time.time() - start_time
    
    assert response.status_code == 200
    assert response_time < 1.0, f"Response time {response_time}s exceeds 1s limit"
```

### Concurrent Request Testing
```python
@pytest.mark.api
async def test_concurrent_requests(async_client: httpx.AsyncClient):
    """Test concurrent request handling."""
    import asyncio
    
    # Make multiple concurrent requests
    tasks = [
        async_client.get("/api/articles") for _ in range(10)
    ]
    
    responses = await asyncio.gather(*tasks)
    
    # Verify all requests succeeded
    for response in responses:
        assert response.status_code == 200
    
    # Verify response consistency
    first_data = responses[0].json()
    for response in responses[1:]:
        data = response.json()
        assert data["articles"] == first_data["articles"]
```

## 🔒 Security Tests

### Input Validation
```python
@pytest.mark.api
async def test_input_validation(async_client: httpx.AsyncClient, api_headers):
    """Test input validation and security."""
    # Test SQL injection attempt
    malicious_data = {
        "name": "'; DROP TABLE sources; --",
        "url": "https://example.com/feed.xml",
        "type": "rss"
    }
    
    response = await async_client.post(
        "/api/sources",
        json=malicious_data,
        headers=api_headers
    )
    
    # Should handle gracefully (either reject or sanitize)
    assert response.status_code in [400, 201]
    
    # Test XSS attempt
    xss_data = {
        "name": "<script>alert('xss')</script>",
        "url": "https://example.com/feed.xml",
        "type": "rss"
    }
    
    response = await async_client.post(
        "/api/sources",
        json=xss_data,
        headers=api_headers
    )
    
    # Should sanitize or reject
    assert response.status_code in [400, 201]
```

### Rate Limiting
```python
@pytest.mark.api
async def test_rate_limiting(async_client: httpx.AsyncClient):
    """Test rate limiting functionality."""
    # Make rapid requests
    for i in range(100):
        response = await async_client.get("/api/articles")
        
        # Should eventually hit rate limit
        if response.status_code == 429:
            assert "rate limit" in response.text.lower()
            break
    else:
        # If no rate limit hit, that's also acceptable
        assert True
```

## 📊 Data Consistency Tests

### Cross-Endpoint Consistency
```python
@pytest.mark.api
async def test_cross_endpoint_consistency(async_client: httpx.AsyncClient):
    """Test data consistency across endpoints."""
    # Get articles from main endpoint
    articles_response = await async_client.get("/api/articles")
    assert articles_response.status_code == 200
    articles_data = articles_response.json()
    
    # Get sources from main endpoint
    sources_response = await async_client.get("/api/sources")
    assert sources_response.status_code == 200
    sources_data = sources_response.json()
    
    # Verify article-source relationships
    for article in articles_data["articles"]:
        if "source_id" in article:
            source_id = article["source_id"]
            # Find corresponding source
            source = next(
                (s for s in sources_data["sources"] if s["id"] == source_id),
                None
            )
            assert source is not None, f"Article {article['id']} references non-existent source {source_id}"
```

### Database Consistency
```python
@pytest.mark.api
async def test_database_consistency(async_client: httpx.AsyncClient):
    """Test database consistency through API."""
    # Create a source
    source_data = {
        "name": "Consistency Test Source",
        "url": "https://example.com/feed.xml",
        "type": "rss",
        "active": True
    }
    
    create_response = await async_client.post("/api/sources", json=source_data)
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]
    
    # Verify source appears in list
    list_response = await async_client.get("/api/sources")
    assert list_response.status_code == 200
    
    sources = list_response.json()["sources"]
    created_source = next((s for s in sources if s["id"] == source_id), None)
    assert created_source is not None
    assert created_source["name"] == "Consistency Test Source"
    
    # Verify individual source endpoint
    individual_response = await async_client.get(f"/api/sources/{source_id}")
    assert individual_response.status_code == 200
    
    individual_source = individual_response.json()
    assert individual_source["name"] == "Consistency Test Source"
```

## 🚀 Running API Tests

### Basic Commands
```bash
# Run all API tests
pytest -m api

# Run specific test file
pytest tests/api/test_endpoints.py

# Run with verbose output
pytest -m api -v

# Run with coverage
pytest -m api --cov=src --cov-report=html
```

### Advanced Commands
```bash
# Run specific test function
pytest tests/api/test_endpoints.py::test_articles_endpoint -v

# Run with debug output
pytest -m api -v -s

# Run in parallel
pytest -m api -n auto

# Run only failed tests
pytest -m api --lf
```

## 🔧 Debugging API Tests

### Common Issues
1. **Connection errors** → Check if application is running
2. **Timeout errors** → Increase timeout or check performance
3. **Data validation failures** → Check API response format
4. **Authentication errors** → Verify auth configuration

### Debug Commands
```bash
# Run with debug output
pytest -m api -v -s --log-cli-level=DEBUG

# Run single test with debug
pytest tests/api/test_endpoints.py::test_articles_endpoint -v -s

# Check API response
curl -v http://localhost:8000/api/articles
```

### Debug Mode
```python
# Add debug prints in tests
@pytest.mark.api
async def test_debug_api(async_client: httpx.AsyncClient):
    """Debug API response."""
    response = await async_client.get("/api/articles")
    print(f"Status: {response.status_code}")
    print(f"Headers: {response.headers}")
    print(f"Content: {response.text}")
    
    assert response.status_code == 200
```

## 📊 Test Reports

### API Test Results
- **Location**: `test-results/api-report.html`
- **Content**: API test results, response times, error rates
- **Features**: Request/response details, performance metrics

### Coverage Reports
- **Location**: `htmlcov/index.html`
- **Content**: Code coverage for API endpoints
- **Target**: 90%+ coverage for API code

## 🎯 Best Practices

### Test Design
- **Test realistic scenarios** with real data
- **Validate response structure** and data types
- **Test error conditions** and edge cases
- **Verify data consistency** across endpoints

### Performance
- **Monitor response times** and set limits
- **Test concurrent requests** for scalability
- **Use appropriate timeouts** for different operations
- **Profile slow endpoints** and optimize

### Security
- **Test input validation** and sanitization
- **Verify authentication** and authorization
- **Test rate limiting** and abuse prevention
- **Check for common vulnerabilities**

## 📚 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)
- **Debug and maintain** → [Test Maintenance](TEST_MAINTENANCE.md)

## 🔍 Additional Resources

- [httpx Documentation](https://www.python-httpx.org/)
- [pytest-httpx](https://pytest-httpx.readthedocs.io/)
- [REST API Testing Best Practices](https://restfulapi.net/testing/)
- [API Security Testing](https://owasp.org/www-project-api-security/)
