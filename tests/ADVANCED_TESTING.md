# Advanced Testing Guide

Comprehensive guide for advanced testing strategies including API testing, end-to-end testing, and performance testing for the CTIScraper system.

## Table of Contents

1. [API Testing](#api-testing)
2. [End-to-End Testing](#end-to-end-testing)
3. [Performance Testing](#performance-testing)
4. [Test Execution](#test-execution)
5. [Debugging](#debugging)
6. [Best Practices](#best-practices)
7. [Resources](#resources)

## API Testing

### Overview

API testing validates REST API endpoints, including request/response validation, error handling, and data consistency verification.

### Setup and Dependencies

```bash
# Install API testing dependencies
pip install httpx pytest-asyncio pytest-httpx
```

### Configuration

```python
# conftest.py
import pytest
import httpx
import os
from typing import AsyncGenerator

@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API testing."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    async with httpx.AsyncClient(base_url=base_url) as client:
        yield client

@pytest.fixture
def api_headers():
    """Default API headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
```

### Basic API Tests

#### Health Check
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

#### Articles API
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

#### Sources API
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

### Data Validation Tests

#### Article Data Validation
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

### Query Parameter Testing

#### Pagination
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

#### Filtering
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

### CRUD Operations Testing

#### Create Source
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

### Error Handling Tests

#### Invalid Endpoints
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

#### Invalid Data
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
```

### Performance Tests

#### Response Time Testing
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

#### Concurrent Request Testing
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

### Security Tests

#### Input Validation
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

## End-to-End Testing

### Overview

End-to-end (E2E) testing validates complete user workflows and system integration, ensuring all components work together correctly from the user's perspective.

### Test Structure

```
tests/e2e/
├── conftest.py              # Shared fixtures and configuration
├── test_web_interface.py    # Main E2E test suite
├── test_user_workflows.py   # Complete user workflows
├── test_system_integration.py # System integration tests
├── mcp_orchestrator.py      # MCP-based test orchestration
├── playwright_config.py     # Playwright configuration
└── README.md               # E2E testing documentation
```

### User Workflow Tests

#### Complete Source Management Workflow
```python
@pytest.mark.e2e
def test_complete_source_management_workflow(page: Page):
    """Test complete source management workflow from start to finish."""
    # 1. Navigate to sources page
    page.goto("http://localhost:8001/sources")
    expect(page).to_have_title("CTI Scraper - Sources")
    
    # 2. Add new source
    page.click("button:has-text('Add Source')")
    page.fill("input[name='name']", "E2E Test Source")
    page.fill("input[name='url']", "https://example.com/threat-feed.xml")
    page.select_option("select[name='type']", "rss")
    page.click("button:has-text('Save')")
    
    # 3. Verify source was added
    expect(page.locator("text=E2E Test Source")).to_be_visible()
    expect(page.locator(".success-message")).to_be_visible()
    
    # 4. Trigger content collection
    page.click("button:has-text('Collect Content')")
    expect(page.locator(".loading-indicator")).to_be_visible()
    expect(page.locator(".loading-indicator")).to_be_hidden(timeout=30000)
    
    # 5. Verify articles were collected
    page.goto("http://localhost:8001/articles")
    expect(page.locator(".article-list")).to_be_visible()
    
    # 6. Verify articles have threat scores
    articles = page.locator(".article-item")
    count = articles.count()
    assert count > 0, "Should have collected articles"
    
    # 7. Check threat scoring
    threat_scores = page.locator(".threat-score")
    expect(threat_scores.first).to_be_visible()
    
    # 8. Test article filtering
    page.click("button:has-text('High Threat')")
    expect(page.locator(".article-item")).to_be_visible()
    
    # 9. Test article search
    page.fill("input[placeholder='Search articles...']", "threat")
    page.press("input[placeholder='Search articles...']", "Enter")
    expect(page.locator(".search-results")).to_be_visible()
    
    # 10. Clean up - delete source
    page.goto("http://localhost:8001/sources")
    page.click("button:has-text('Delete')")
    page.click("button:has-text('Confirm')")
    expect(page.locator("text=E2E Test Source")).to_be_hidden()
```

#### Content Processing Workflow
```python
@pytest.mark.e2e
def test_content_processing_workflow(page: Page):
    """Test complete content processing workflow."""
    # 1. Add source with known content
    page.goto("http://localhost:8001/sources")
    page.click("button:has-text('Add Source')")
    page.fill("input[name='name']", "Content Test Source")
    page.fill("input[name='url']", "https://example.com/test-feed.xml")
    page.select_option("select[name='type']", "rss")
    page.click("button:has-text('Save')")
    
    # 2. Trigger collection
    page.click("button:has-text('Collect Content')")
    expect(page.locator(".loading-indicator")).to_be_visible()
    
    # 3. Wait for processing to complete
    expect(page.locator(".loading-indicator")).to_be_hidden(timeout=60000)
    
    # 4. Verify articles were processed
    page.goto("http://localhost:8001/articles")
    expect(page.locator(".article-list")).to_be_visible()
    
    # 5. Check article details
    first_article = page.locator(".article-item").first
    first_article.click()
    
    # 6. Verify article content
    expect(page.locator(".article-content")).to_be_visible()
    expect(page.locator(".article-metadata")).to_be_visible()
    
    # 7. Check threat analysis
    expect(page.locator(".threat-analysis")).to_be_visible()
    expect(page.locator(".threat-score")).to_be_visible()
    
    # 8. Verify source attribution
    expect(page.locator(".source-info")).to_be_visible()
    expect(page.locator("text=Content Test Source")).to_be_visible()
    
    # 9. Test article annotation
    page.click("button:has-text('Add Annotation')")
    page.fill("textarea[name='annotation']", "E2E test annotation")
    page.select_option("select[name='label']", "huntable")
    page.click("button:has-text('Save')")
    
    # 10. Verify annotation was added
    expect(page.locator("text=E2E test annotation")).to_be_visible()
    expect(page.locator(".annotation-label")).to_be_visible()
```

### System Integration Tests

#### Database Integration
```python
@pytest.mark.e2e
def test_database_integration(page: Page):
    """Test database integration across the system."""
    # 1. Create source via UI
    page.goto("http://localhost:8001/sources")
    page.click("button:has-text('Add Source')")
    page.fill("input[name='name']", "DB Integration Test")
    page.fill("input[name='url']", "https://example.com/db-test.xml")
    page.select_option("select[name='type']", "rss")
    page.click("button:has-text('Save')")
    
    # 2. Verify source in database via API
    response = page.request.get("/api/sources")
    assert response.status == 200
    
    data = response.json()
    sources = data["sources"]
    created_source = next((s for s in sources if s["name"] == "DB Integration Test"), None)
    assert created_source is not None
    
    # 3. Trigger collection
    page.click("button:has-text('Collect Content')")
    expect(page.locator(".loading-indicator")).to_be_hidden(timeout=30000)
    
    # 4. Verify articles in database
    response = page.request.get("/api/articles")
    assert response.status == 200
    
    data = response.json()
    articles = data["articles"]
    assert len(articles) > 0
    
    # 5. Verify article-source relationship
    for article in articles:
        if article["source_id"] == created_source["id"]:
            assert article["title"] is not None
            assert article["content"] is not None
            assert article["threat_score"] is not None
            break
    else:
        assert False, "No articles found for created source"
```

### Data Flow Tests

#### End-to-End Data Processing
```python
@pytest.mark.e2e
def test_end_to_end_data_processing(page: Page):
    """Test complete data processing pipeline."""
    # 1. Add source
    page.goto("http://localhost:8001/sources")
    page.click("button:has-text('Add Source')")
    page.fill("input[name='name']", "Data Flow Test")
    page.fill("input[name='url']", "https://example.com/data-flow.xml")
    page.select_option("select[name='type']", "rss")
    page.click("button:has-text('Save')")
    
    # 2. Trigger collection
    page.click("button:has-text('Collect Content')")
    expect(page.locator(".loading-indicator")).to_be_visible()
    
    # 3. Wait for processing
    expect(page.locator(".loading-indicator")).to_be_hidden(timeout=60000)
    
    # 4. Verify data flow through system
    # Check raw data collection
    page.goto("http://localhost:8001/articles")
    expect(page.locator(".article-list")).to_be_visible()
    
    # Check content processing
    first_article = page.locator(".article-item").first
    first_article.click()
    expect(page.locator(".article-content")).to_be_visible()
    
    # Check threat analysis
    expect(page.locator(".threat-analysis")).to_be_visible()
    threat_score = page.locator(".threat-score").text_content()
    assert threat_score.isdigit()
    
    # Check metadata extraction
    expect(page.locator(".article-metadata")).to_be_visible()
    expect(page.locator(".source-info")).to_be_visible()
    
    # Check searchability
    page.goto("http://localhost:8001/articles")
    page.fill("input[placeholder='Search articles...']", "threat")
    page.press("input[placeholder='Search articles...']", "Enter")
    expect(page.locator(".search-results")).to_be_visible()
    
    # Check filtering
    page.click("button:has-text('High Threat')")
    expect(page.locator(".article-item")).to_be_visible()
```

### Performance E2E Tests

#### System Performance
```python
@pytest.mark.e2e
def test_system_performance(page: Page):
    """Test system performance under E2E conditions."""
    import time
    
    # 1. Test page load performance
    start_time = time.time()
    page.goto("http://localhost:8001/")
    expect(page.locator("main")).to_be_visible()
    load_time = time.time() - start_time
    
    assert load_time < 5.0, f"Page load time {load_time}s exceeds 5s limit"
    
    # 2. Test navigation performance
    start_time = time.time()
    page.click("text=Articles")
    expect(page.locator(".article-list")).to_be_visible()
    nav_time = time.time() - start_time
    
    assert nav_time < 3.0, f"Navigation time {nav_time}s exceeds 3s limit"
    
    # 3. Test search performance
    start_time = time.time()
    page.fill("input[placeholder='Search articles...']", "test")
    page.press("input[placeholder='Search articles...']", "Enter")
    expect(page.locator(".search-results")).to_be_visible()
    search_time = time.time() - start_time
    
    assert search_time < 2.0, f"Search time {search_time}s exceeds 2s limit"
    
    # 4. Test form submission performance
    page.goto("http://localhost:8001/sources")
    page.click("button:has-text('Add Source')")
    
    start_time = time.time()
    page.fill("input[name='name']", "Performance Test")
    page.fill("input[name='url']", "https://example.com/perf.xml")
    page.select_option("select[name='type']", "rss")
    page.click("button:has-text('Save')")
    expect(page.locator("text=Performance Test")).to_be_visible()
    form_time = time.time() - start_time
    
    assert form_time < 2.0, f"Form submission time {form_time}s exceeds 2s limit"
```

## Performance Testing

### Overview

Performance testing ensures CTIScraper meets performance requirements under various load conditions.

### Test Categories

- **Load Testing**: Normal expected load
- **Stress Testing**: Beyond normal capacity
- **Volume Testing**: Large amounts of data
- **Spike Testing**: Sudden load increases
- **Endurance Testing**: Extended periods
- **Scalability Testing**: Resource scaling

### Performance Metrics

- **Response Time**: API and page load times
- **Throughput**: Requests per second
- **Resource Utilization**: CPU, memory, disk
- **Error Rate**: Failed requests percentage
- **Concurrent Users**: Simultaneous users supported

### Tools and Setup

```bash
# Install performance testing dependencies
pip install locust pytest-benchmark memory-profiler psutil
```

### Load Testing

#### Basic Load Test
```python
import asyncio
import time
import httpx
import os
from typing import List, Dict

class LoadTester:
    """Basic load testing implementation."""
    
    def __init__(self, base_url: str = None):
        if base_url is None:
            base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        self.base_url = base_url
        self.results = []
    
    async def single_request(self, endpoint: str) -> Dict:
        """Make a single request and measure performance."""
        start_time = time.time()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}{endpoint}")
                end_time = time.time()
                
                return {
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "response_time": end_time - start_time,
                    "success": response.status_code == 200,
                    "error": None
                }
        except Exception as e:
            end_time = time.time()
            return {
                "endpoint": endpoint,
                "status_code": None,
                "response_time": end_time - start_time,
                "success": False,
                "error": str(e)
            }
    
    async def concurrent_requests(self, endpoint: str, concurrency: int = 10) -> List[Dict]:
        """Make concurrent requests to test load handling."""
        tasks = [self.single_request(endpoint) for _ in range(concurrency)]
        results = await asyncio.gather(*tasks)
        return results
    
    def analyze_results(self, results: List[Dict]) -> Dict:
        """Analyze load test results."""
        if not results:
            return {}
        
        response_times = [r["response_time"] for r in results if r["success"]]
        success_count = sum(1 for r in results if r["success"])
        error_count = len(results) - success_count
        
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0
        
        return {
            "total_requests": len(results),
            "successful_requests": success_count,
            "failed_requests": error_count,
            "success_rate": (success_count / len(results)) * 100,
            "avg_response_time": avg_response_time,
            "min_response_time": min_response_time,
            "max_response_time": max_response_time,
            "requests_per_second": len(results) / sum(r["response_time"] for r in results)
        }

# Test implementation
@pytest.mark.performance
async def test_api_load_performance():
    """Test API performance under load."""
    load_tester = LoadTester()
    
    # Test articles endpoint
    results = await load_tester.concurrent_requests("/api/articles", concurrency=20)
    analysis = load_tester.analyze_results(results)
    
    # Assertions
    assert analysis["success_rate"] >= 95, f"Success rate {analysis['success_rate']}% below 95%"
    assert analysis["avg_response_time"] < 2.0, f"Avg response time {analysis['avg_response_time']}s exceeds 2s"
    assert analysis["max_response_time"] < 5.0, f"Max response time {analysis['max_response_time']}s exceeds 5s"
```

#### Locust Load Testing
```python
# locustfile.py
from locust import HttpUser, task, between
import random

class CTIScraperUser(HttpUser):
    """Locust user for CTI Scraper load testing."""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts."""
        self.client.verify = False
    
    @task(3)
    def view_homepage(self):
        """View homepage - most common task."""
        self.client.get("/")
    
    @task(2)
    def view_articles(self):
        """View articles page."""
        self.client.get("/articles")
    
    @task(2)
    def view_sources(self):
        """View sources page."""
        self.client.get("/sources")
    
    @task(1)
    def view_analysis(self):
        """View analysis page."""
        self.client.get("/analysis")
    
    @task(1)
    def api_articles(self):
        """Call articles API."""
        self.client.get("/api/articles")
    
    @task(1)
    def api_sources(self):
        """Call sources API."""
        self.client.get("/api/sources")
    
    @task(1)
    def search_articles(self):
        """Search articles."""
        search_terms = ["malware", "threat", "attack", "security", "vulnerability"]
        term = random.choice(search_terms)
        self.client.get(f"/api/articles?search={term}")
    
    @task(1)
    def filter_articles(self):
        """Filter articles by threat score."""
        min_score = random.randint(0, 100)
        self.client.get(f"/api/articles?min_threat_score={min_score}")

# Run with: locust -f locustfile.py --host=http://localhost:8001
```

### Stress Testing

#### Stress Test Implementation
```python
@pytest.mark.performance
async def test_stress_performance():
    """Test system behavior under stress conditions."""
    load_tester = LoadTester()
    
    # Gradually increase load
    concurrency_levels = [10, 25, 50, 100, 200]
    results = {}
    
    for concurrency in concurrency_levels:
        print(f"Testing with {concurrency} concurrent requests...")
        
        # Test multiple endpoints
        endpoints = ["/", "/articles", "/sources", "/api/articles", "/api/sources"]
        all_results = []
        
        for endpoint in endpoints:
            endpoint_results = await load_tester.concurrent_requests(endpoint, concurrency)
            all_results.extend(endpoint_results)
        
        analysis = load_tester.analyze_results(all_results)
        results[concurrency] = analysis
        
        # Check if system is still responsive
        if analysis["success_rate"] < 90:
            print(f"System degraded at {concurrency} concurrent requests")
            break
    
    # Find breaking point
    breaking_point = None
    for concurrency, analysis in results.items():
        if analysis["success_rate"] < 90:
            breaking_point = concurrency
            break
    
    # Assertions
    assert breaking_point is None or breaking_point >= 100, f"System breaks at {breaking_point} concurrent requests"
    
    # Verify performance under normal load
    normal_load = results.get(25, {})
    assert normal_load["success_rate"] >= 95, "Normal load performance degraded"
    assert normal_load["avg_response_time"] < 3.0, "Normal load response time too high"
```

### System Resource Monitoring

#### Resource Usage Testing
```python
import psutil
import time
from typing import Dict, List

class SystemMonitor:
    """Monitor system resources during testing."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.metrics = []
    
    def start_monitoring(self):
        """Start resource monitoring."""
        self.metrics = []
        self.start_time = time.time()
    
    def collect_metrics(self) -> Dict:
        """Collect current system metrics."""
        cpu_percent = self.process.cpu_percent()
        memory_info = self.process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # System-wide metrics
        system_cpu = psutil.cpu_percent()
        system_memory = psutil.virtual_memory()
        
        metrics = {
            "timestamp": time.time(),
            "process_cpu": cpu_percent,
            "process_memory_mb": memory_mb,
            "system_cpu": system_cpu,
            "system_memory_percent": system_memory.percent,
            "system_memory_available_gb": system_memory.available / 1024 / 1024 / 1024
        }
        
        self.metrics.append(metrics)
        return metrics
    
    def get_summary(self) -> Dict:
        """Get monitoring summary."""
        if not self.metrics:
            return {}
        
        process_cpu_values = [m["process_cpu"] for m in self.metrics]
        process_memory_values = [m["process_memory_mb"] for m in self.metrics]
        system_cpu_values = [m["system_cpu"] for m in self.metrics]
        
        return {
            "duration": time.time() - self.start_time,
            "avg_process_cpu": sum(process_cpu_values) / len(process_cpu_values),
            "max_process_cpu": max(process_cpu_values),
            "avg_process_memory_mb": sum(process_memory_values) / len(process_memory_values),
            "max_process_memory_mb": max(process_memory_values),
            "avg_system_cpu": sum(system_cpu_values) / len(system_cpu_values),
            "max_system_cpu": max(system_cpu_values)
        }

# Test implementation
@pytest.mark.performance
async def test_resource_usage():
    """Test system resource usage under load."""
    monitor = SystemMonitor()
    load_tester = LoadTester()
    
    # Start monitoring
    monitor.start_monitoring()
    
    # Run load test while monitoring
    async def monitor_and_test():
        tasks = []
        
        # Monitoring task
        async def monitor_task():
            while True:
                monitor.collect_metrics()
                await asyncio.sleep(1)
        
        # Load test task
        async def load_task():
            return await load_tester.concurrent_requests("/api/articles", concurrency=50)
        
        tasks.append(asyncio.create_task(monitor_task()))
        tasks.append(asyncio.create_task(load_task()))
        
        # Wait for load test to complete
        results = await tasks[1]
        
        # Stop monitoring
        tasks[0].cancel()
        
        return results
    
    # Run test
    results = await monitor_and_test()
    analysis = load_tester.analyze_results(results)
    summary = monitor.get_summary()
    
    # Assertions
    assert analysis["success_rate"] >= 95, "Load test success rate too low"
    assert summary["max_process_cpu"] < 80, f"Max CPU usage {summary['max_process_cpu']}% too high"
    assert summary["max_process_memory_mb"] < 500, f"Max memory usage {summary['max_process_memory_mb']}MB too high"
```

### Performance Benchmarks

#### Benchmark Testing
```python
import pytest
import time
from typing import Dict

class PerformanceBenchmarks:
    """Performance benchmark definitions."""
    
    BENCHMARKS = {
        "homepage_load": {"max_time": 2.0, "description": "Homepage load time"},
        "articles_page": {"max_time": 3.0, "description": "Articles page load time"},
        "api_articles": {"max_time": 1.0, "description": "Articles API response time"},
        "api_sources": {"max_time": 1.0, "description": "Sources API response time"},
        "search_articles": {"max_time": 2.0, "description": "Article search response time"},
        "concurrent_users": {"min_users": 50, "description": "Concurrent users supported"},
        "throughput": {"min_rps": 100, "description": "Requests per second"}
    }
    
    @classmethod
    def validate_benchmark(cls, test_name: str, value: float) -> bool:
        """Validate if value meets benchmark requirements."""
        benchmark = cls.BENCHMARKS.get(test_name)
        if not benchmark:
            return True
        
        if "max_time" in benchmark:
            return value <= benchmark["max_time"]
        elif "min_users" in benchmark:
            return value >= benchmark["min_users"]
        elif "min_rps" in benchmark:
            return value >= benchmark["min_rps"]
        
        return True

# Test implementations
@pytest.mark.performance
async def test_homepage_benchmark():
    """Test homepage load time benchmark."""
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8001/")
        assert response.status_code == 200
    
    load_time = time.time() - start_time
    
    assert PerformanceBenchmarks.validate_benchmark("homepage_load", load_time), \
        f"Homepage load time {load_time}s exceeds benchmark"

@pytest.mark.performance
async def test_api_benchmark():
    """Test API response time benchmark."""
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8001/api/articles")
        assert response.status_code == 200
    
    response_time = time.time() - start_time
    
    assert PerformanceBenchmarks.validate_benchmark("api_articles", response_time), \
        f"API response time {response_time}s exceeds benchmark"
```

## Test Execution

### Basic Commands

#### API Tests
```bash
# Run API tests using unified interface
python run_tests.py --api

# Docker-based API testing
python run_tests.py --docker --api

# Run specific test file
pytest tests/api/test_endpoints.py

# Run with verbose output
pytest -m api -v

# Run with coverage
pytest -m api --cov=src --cov-report=html
```

#### E2E Tests
```bash
# Run E2E tests using unified interface
python run_tests.py --ui

# Docker-based E2E testing
python run_tests.py --docker --ui

# Run specific test file
pytest tests/e2e/test_web_interface.py

# Run with visible browser
pytest -m e2e --headed=true

# Run with debug output
pytest -m e2e -v -s
```

#### Performance Tests
```bash
# Run performance tests using unified interface
python run_tests.py --performance

# Docker-based performance testing
python run_tests.py --docker --performance

# Run specific performance test
pytest tests/performance/test_load.py -v

# Run with benchmark mode
pytest --benchmark-only -m performance

# Run Locust load tests
locust -f locustfile.py --host=http://localhost:8001
```

### Advanced Commands

#### API Testing
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

#### E2E Testing
```bash
# Run with specific browser
pytest -m e2e --browser=firefox

# Run with slow motion
pytest -m e2e --slow-mo=1000

# Run with video recording
pytest -m e2e --video=on

# Run with trace
pytest -m e2e --trace=on

# Run in parallel
pytest -m e2e -n auto
```

#### Performance Testing
```bash
# Run with performance profiling
pytest -m performance --profile

# Run with memory profiling
pytest -m performance --memray

# Run with custom timeout
pytest -m performance --timeout=300

# Run in parallel
pytest -m performance -n auto
```

## Debugging

### Common Issues

#### API Tests
1. **Connection errors** → Check if application is running
2. **Timeout errors** → Increase timeout or check performance
3. **Data validation failures** → Check API response format
4. **Authentication errors** → Verify auth configuration

#### E2E Tests
1. **Application not running** → Check Docker containers
2. **Database connectivity** → Verify database service
3. **Timeout errors** → Increase timeout or check performance
4. **Flaky tests** → Use more specific selectors

#### Performance Tests
1. **Resource constraints** → Check system resources
2. **Network issues** → Verify network connectivity
3. **Test environment** → Ensure isolated test environment
4. **Baseline establishment** → Set proper performance baselines

### Debug Commands

#### API Testing
```bash
# Run with debug output
pytest -m api -v -s --log-cli-level=DEBUG

# Run single test with debug
pytest tests/api/test_endpoints.py::test_articles_endpoint -v -s

# Check API response
curl -v http://localhost:8001/api/articles
```

#### E2E Testing
```bash
# Run with visible browser
pytest -m e2e --headed=true

# Run with debug output
pytest -m e2e -v -s --log-cli-level=DEBUG

# Run single test with debug
pytest tests/e2e/test_web_interface.py::test_homepage_loads -v -s

# Check application health
curl http://localhost:8001/health
```

#### Performance Testing
```bash
# Run with debug output
pytest -m performance -v -s

# Run single test with debug
pytest tests/performance/test_load.py::test_api_load_performance -v -s

# Check system resources
htop
```

### Debug Mode

#### API Testing
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

#### E2E Testing
```python
# Enable Playwright debug mode
PWDEBUG=1 pytest -m e2e -s

# Use browser developer tools
page.pause()  # Pause execution for manual inspection
```

#### Performance Testing
```python
# Add performance debugging
@pytest.mark.performance
async def test_debug_performance():
    """Debug performance issues."""
    import time
    import psutil
    
    # Monitor resources
    process = psutil.Process()
    start_cpu = process.cpu_percent()
    start_memory = process.memory_info().rss / 1024 / 1024
    
    # Run test
    start_time = time.time()
    # ... test code ...
    end_time = time.time()
    
    # Check resources
    end_cpu = process.cpu_percent()
    end_memory = process.memory_info().rss / 1024 / 1024
    
    print(f"Test duration: {end_time - start_time}s")
    print(f"CPU usage: {start_cpu}% -> {end_cpu}%")
    print(f"Memory usage: {start_memory}MB -> {end_memory}MB")
```

## Best Practices

### Test Design

#### API Testing
- **Test realistic scenarios** with real data
- **Validate response structure** and data types
- **Test error conditions** and edge cases
- **Verify data consistency** across endpoints

#### E2E Testing
- **Test complete workflows** not just individual features
- **Use realistic data** and scenarios
- **Verify data consistency** across components
- **Test error conditions** and edge cases

#### Performance Testing
- **Realistic scenarios** with real data
- **Gradual load increase** to find breaking points
- **Multiple test types** for comprehensive coverage
- **Baseline establishment** for comparison

### Performance

#### API Testing
- **Monitor response times** and set limits
- **Test concurrent requests** for scalability
- **Use appropriate timeouts** for different operations
- **Profile slow endpoints** and optimize

#### E2E Testing
- **Monitor execution time** and set limits
- **Test under load** conditions
- **Optimize test execution** for speed
- **Profile slow tests** and improve

#### Performance Testing
- **Continuous monitoring** during tests
- **Resource usage tracking** for optimization
- **Error rate monitoring** for reliability
- **Response time distribution** analysis

### Security

#### API Testing
- **Test input validation** and sanitization
- **Verify authentication** and authorization
- **Test rate limiting** and abuse prevention
- **Check for common vulnerabilities**

#### E2E Testing
- **Test security workflows** and access controls
- **Verify data protection** and privacy
- **Test session management** and timeouts
- **Check for security headers** and policies

### Maintenance

#### API Testing
- **Update tests** when API changes
- **Refactor common patterns** into reusable functions
- **Document test purposes** clearly
- **Keep test data current**

#### E2E Testing
- **Keep tests independent** and isolated
- **Update tests** when UI changes
- **Refactor common patterns** into reusable functions
- **Document test purposes** clearly

#### Performance Testing
- **Isolated environment** for consistent results
- **Repeatable tests** for reliable comparisons
- **Automated execution** in CI/CD
- **Regular performance reviews** and updates

## Resources

### Documentation

- [httpx Documentation](https://www.python-httpx.org/)
- [pytest-httpx](https://pytest-httpx.readthedocs.io/)
- [Playwright E2E Testing](https://playwright.dev/docs/test-types)
- [Locust Documentation](https://docs.locust.io/)
- [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)

### Best Practices

- [REST API Testing Best Practices](https://restfulapi.net/testing/)
- [API Security Testing](https://owasp.org/www-project-api-security/)
- [E2E Testing Best Practices](https://playwright.dev/docs/best-practices)
- [Performance Testing Best Practices](https://martinfowler.com/articles/practical-test-pyramid.html)
- [Load Testing Strategies](https://k6.io/docs/testing-guides/)

### Tools

- **httpx**: HTTP client for API testing
- **pytest-httpx**: Pytest plugin for httpx
- **Playwright**: Browser automation for E2E testing
- **Locust**: Load testing framework
- **pytest-benchmark**: Performance benchmarking
- **psutil**: System resource monitoring

---

*Last updated: January 2025*
