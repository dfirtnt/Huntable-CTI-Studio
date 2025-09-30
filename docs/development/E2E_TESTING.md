# 🔗 End-to-End Testing

Comprehensive guide for end-to-end testing of the CTI Scraper system.

## 🎯 Overview

End-to-end (E2E) testing validates complete user workflows and system integration, ensuring all components work together correctly from the user's perspective.

## 🏗️ E2E Test Architecture

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

### Test Categories
- **User Workflows**: Complete user journeys
- **System Integration**: Component interaction
- **Data Flow**: End-to-end data processing
- **Performance**: System-wide performance validation

## 🎭 User Workflow Tests

### Complete Source Management Workflow
```python
@pytest.mark.e2e
async def test_complete_source_management_workflow(page: Page):
    """Test complete source management workflow from start to finish."""
    # 1. Navigate to sources page
    await page.goto("http://localhost:8000/sources")
    await expect(page).to_have_title("CTI Scraper - Sources")
    
    # 2. Add new source
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "E2E Test Source")
    await page.fill("input[name='url']", "https://example.com/threat-feed.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # 3. Verify source was added
    await expect(page.locator("text=E2E Test Source")).to_be_visible()
    await expect(page.locator(".success-message")).to_be_visible()
    
    # 4. Trigger content collection
    await page.click("button:has-text('Collect Content')")
    await expect(page.locator(".loading-indicator")).to_be_visible()
    await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=30000)
    
    # 5. Verify articles were collected
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
    
    # 6. Verify articles have threat scores
    articles = page.locator(".article-item")
    count = await articles.count()
    assert count > 0, "Should have collected articles"
    
    # 7. Check threat scoring
    threat_scores = page.locator(".threat-score")
    await expect(threat_scores.first).to_be_visible()
    
    # 8. Test article filtering
    await page.click("button:has-text('High Threat')")
    await expect(page.locator(".article-item")).to_be_visible()
    
    # 9. Test article search
    await page.fill("input[placeholder='Search articles...']", "threat")
    await page.press("input[placeholder='Search articles...']", "Enter")
    await expect(page.locator(".search-results")).to_be_visible()
    
    # 10. Clean up - delete source
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Delete')")
    await page.click("button:has-text('Confirm')")
    await expect(page.locator("text=E2E Test Source")).to_be_hidden()
```

### Content Processing Workflow
```python
@pytest.mark.e2e
async def test_content_processing_workflow(page: Page):
    """Test complete content processing workflow."""
    # 1. Add source with known content
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "Content Test Source")
    await page.fill("input[name='url']", "https://example.com/test-feed.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # 2. Trigger collection
    await page.click("button:has-text('Collect Content')")
    await expect(page.locator(".loading-indicator")).to_be_visible()
    
    # 3. Wait for processing to complete
    await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=60000)
    
    # 4. Verify articles were processed
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
    
    # 5. Check article details
    first_article = page.locator(".article-item").first
    await first_article.click()
    
    # 6. Verify article content
    await expect(page.locator(".article-content")).to_be_visible()
    await expect(page.locator(".article-metadata")).to_be_visible()
    
    # 7. Check threat analysis
    await expect(page.locator(".threat-analysis")).to_be_visible()
    await expect(page.locator(".threat-score")).to_be_visible()
    
    # 8. Verify source attribution
    await expect(page.locator(".source-info")).to_be_visible()
    await expect(page.locator("text=Content Test Source")).to_be_visible()
    
    # 9. Test article annotation
    await page.click("button:has-text('Add Annotation')")
    await page.fill("textarea[name='annotation']", "E2E test annotation")
    await page.select_option("select[name='label']", "huntable")
    await page.click("button:has-text('Save')")
    
    # 10. Verify annotation was added
    await expect(page.locator("text=E2E test annotation")).to_be_visible()
    await expect(page.locator(".annotation-label")).to_be_visible()
```

## 🔗 System Integration Tests

### Database Integration
```python
@pytest.mark.e2e
async def test_database_integration(page: Page):
    """Test database integration across the system."""
    # 1. Create source via UI
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "DB Integration Test")
    await page.fill("input[name='url']", "https://example.com/db-test.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # 2. Verify source in database via API
    response = await page.request.get("/api/sources")
    assert response.status == 200
    
    data = await response.json()
    sources = data["sources"]
    created_source = next((s for s in sources if s["name"] == "DB Integration Test"), None)
    assert created_source is not None
    
    # 3. Trigger collection
    await page.click("button:has-text('Collect Content')")
    await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=30000)
    
    # 4. Verify articles in database
    response = await page.request.get("/api/articles")
    assert response.status == 200
    
    data = await response.json()
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

### Service Integration
```python
@pytest.mark.e2e
async def test_service_integration(page: Page):
    """Test integration between different services."""
    # 1. Verify all services are running
    health_response = await page.request.get("/health")
    assert health_response.status == 200
    
    health_data = await health_response.json()
    assert health_data["status"] == "healthy"
    
    # 2. Test web service
    await page.goto("http://localhost:8000/")
    await expect(page).to_have_title("CTI Scraper")
    
    # 3. Test API service
    api_response = await page.request.get("/api/articles")
    assert api_response.status == 200
    
    # 4. Test database service
    db_response = await page.request.get("/api/sources")
    assert db_response.status == 200
    
    # 5. Test worker service (if applicable)
    # This would test background job processing
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "Service Integration Test")
    await page.fill("input[name='url']", "https://example.com/service-test.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # 6. Trigger background processing
    await page.click("button:has-text('Collect Content')")
    await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=60000)
    
    # 7. Verify background processing completed
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
```

## 📊 Data Flow Tests

### End-to-End Data Processing
```python
@pytest.mark.e2e
async def test_end_to_end_data_processing(page: Page):
    """Test complete data processing pipeline."""
    # 1. Add source
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "Data Flow Test")
    await page.fill("input[name='url']", "https://example.com/data-flow.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # 2. Trigger collection
    await page.click("button:has-text('Collect Content')")
    await expect(page.locator(".loading-indicator")).to_be_visible()
    
    # 3. Wait for processing
    await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=60000)
    
    # 4. Verify data flow through system
    # Check raw data collection
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
    
    # Check content processing
    first_article = page.locator(".article-item").first
    await first_article.click()
    await expect(page.locator(".article-content")).to_be_visible()
    
    # Check threat analysis
    await expect(page.locator(".threat-analysis")).to_be_visible()
    threat_score = await page.locator(".threat-score").text_content()
    assert threat_score.isdigit()
    
    # Check metadata extraction
    await expect(page.locator(".article-metadata")).to_be_visible()
    await expect(page.locator(".source-info")).to_be_visible()
    
    # Check searchability
    await page.goto("http://localhost:8000/articles")
    await page.fill("input[placeholder='Search articles...']", "threat")
    await page.press("input[placeholder='Search articles...']", "Enter")
    await expect(page.locator(".search-results")).to_be_visible()
    
    # Check filtering
    await page.click("button:has-text('High Threat')")
    await expect(page.locator(".article-item")).to_be_visible()
```

### Cross-Component Data Consistency
```python
@pytest.mark.e2e
async def test_cross_component_data_consistency(page: Page):
    """Test data consistency across different components."""
    # 1. Create source
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "Consistency Test")
    await page.fill("input[name='url']", "https://example.com/consistency.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # 2. Get source ID from UI
    source_element = page.locator("text=Consistency Test")
    await expect(source_element).to_be_visible()
    
    # 3. Verify source in API
    api_response = await page.request.get("/api/sources")
    assert api_response.status == 200
    
    api_data = await api_response.json()
    api_source = next((s for s in api_data["sources"] if s["name"] == "Consistency Test"), None)
    assert api_source is not None
    
    # 4. Trigger collection
    await page.click("button:has-text('Collect Content')")
    await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=30000)
    
    # 5. Verify articles in UI
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
    
    # 6. Verify articles in API
    api_response = await page.request.get("/api/articles")
    assert api_response.status == 200
    
    api_data = await api_response.json()
    articles = api_data["articles"]
    
    # 7. Verify article-source relationship
    for article in articles:
        if article["source_id"] == api_source["id"]:
            # Check UI consistency
            await page.goto(f"http://localhost:8000/articles/{article['id']}")
            await expect(page.locator(".article-content")).to_be_visible()
            await expect(page.locator("text=Consistency Test")).to_be_visible()
            break
    else:
        assert False, "No articles found for created source"
```

## ⚡ Performance E2E Tests

### System Performance
```python
@pytest.mark.e2e
async def test_system_performance(page: Page):
    """Test system performance under E2E conditions."""
    import time
    
    # 1. Test page load performance
    start_time = time.time()
    await page.goto("http://localhost:8000/")
    await expect(page.locator("main")).to_be_visible()
    load_time = time.time() - start_time
    
    assert load_time < 5.0, f"Page load time {load_time}s exceeds 5s limit"
    
    # 2. Test navigation performance
    start_time = time.time()
    await page.click("text=Articles")
    await expect(page.locator(".article-list")).to_be_visible()
    nav_time = time.time() - start_time
    
    assert nav_time < 3.0, f"Navigation time {nav_time}s exceeds 3s limit"
    
    # 3. Test search performance
    start_time = time.time()
    await page.fill("input[placeholder='Search articles...']", "test")
    await page.press("input[placeholder='Search articles...']", "Enter")
    await expect(page.locator(".search-results")).to_be_visible()
    search_time = time.time() - start_time
    
    assert search_time < 2.0, f"Search time {search_time}s exceeds 2s limit"
    
    # 4. Test form submission performance
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    
    start_time = time.time()
    await page.fill("input[name='name']", "Performance Test")
    await page.fill("input[name='url']", "https://example.com/perf.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    await expect(page.locator("text=Performance Test")).to_be_visible()
    form_time = time.time() - start_time
    
    assert form_time < 2.0, f"Form submission time {form_time}s exceeds 2s limit"
```

### Load Testing
```python
@pytest.mark.e2e
async def test_system_load(page: Page):
    """Test system behavior under load."""
    # 1. Create multiple sources
    await page.goto("http://localhost:8000/sources")
    
    for i in range(5):
        await page.click("button:has-text('Add Source')")
        await page.fill("input[name='name']", f"Load Test Source {i}")
        await page.fill("input[name='url']", f"https://example.com/load-{i}.xml")
        await page.select_option("select[name='type']", "rss")
        await page.click("button:has-text('Save')")
        await expect(page.locator(f"text=Load Test Source {i}")).to_be_visible()
    
    # 2. Trigger multiple collections
    for i in range(3):
        await page.click("button:has-text('Collect Content')")
        await expect(page.locator(".loading-indicator")).to_be_visible()
        await expect(page.locator(".loading-indicator")).to_be_hidden(timeout=60000)
    
    # 3. Verify system stability
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
    
    # 4. Test search under load
    await page.fill("input[placeholder='Search articles...']", "load")
    await page.press("input[placeholder='Search articles...']", "Enter")
    await expect(page.locator(".search-results")).to_be_visible()
    
    # 5. Verify system responsiveness
    start_time = time.time()
    await page.click("text=Sources")
    await expect(page.locator("text=Load Test Source 0")).to_be_visible()
    response_time = time.time() - start_time
    
    assert response_time < 3.0, f"System response time {response_time}s exceeds 3s limit"
```

## 🚀 Running E2E Tests

### Basic Commands
```bash
# Run all E2E tests
pytest -m e2e

# Run specific test file
pytest tests/e2e/test_web_interface.py

# Run with visible browser
pytest -m e2e --headed=true

# Run with debug output
pytest -m e2e -v -s
```

### Advanced Commands
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

### MCP Orchestration
```bash
# Run with MCP orchestration
python tests/e2e/mcp_orchestrator.py

# Health check only
python -c "
import asyncio
from tests.e2e.mcp_orchestrator import PlaywrightMCPOrchestrator
orchestrator = PlaywrightMCPOrchestrator()
print(asyncio.run(orchestrator.health_check()))
"
```

## 🔧 Debugging E2E Tests

### Common Issues
1. **Application not running** → Check Docker containers
2. **Database connectivity** → Verify database service
3. **Timeout errors** → Increase timeout or check performance
4. **Flaky tests** → Use more specific selectors

### Debug Commands
```bash
# Run with visible browser
pytest -m e2e --headed=true

# Run with debug output
pytest -m e2e -v -s --log-cli-level=DEBUG

# Run single test with debug
pytest tests/e2e/test_web_interface.py::test_homepage_loads -v -s

# Check application health
curl http://localhost:8000/health
```

### Debug Mode
```python
# Enable Playwright debug mode
PWDEBUG=1 pytest -m e2e -s

# Use browser developer tools
await page.pause()  # Pause execution for manual inspection
```

## 📊 Test Reports

### E2E Test Results
- **Location**: `test-results/e2e-report.html`
- **Content**: E2E test results, workflow validation, performance metrics
- **Features**: Interactive debugging, failure analysis

### Artifacts
- **Videos**: Test execution recordings (`test-results/videos/`)
- **Traces**: Detailed execution traces (`test-results/traces/`)
- **Screenshots**: Page screenshots (`test-results/screenshots/`)
- **Reports**: HTML and JSON test reports (`playwright-report/`)

## 🎯 Best Practices

### Test Design
- **Test complete workflows** not just individual features
- **Use realistic data** and scenarios
- **Verify data consistency** across components
- **Test error conditions** and edge cases

### Performance
- **Monitor execution time** and set limits
- **Test under load** conditions
- **Optimize test execution** for speed
- **Profile slow tests** and improve

### Maintenance
- **Keep tests independent** and isolated
- **Update tests** when UI changes
- **Refactor common patterns** into reusable functions
- **Document test purposes** clearly

## 📚 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Test API endpoints** → [API Testing](API_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)

## 🔍 Additional Resources

- [Playwright E2E Testing](https://playwright.dev/docs/test-types)
- [E2E Testing Best Practices](https://playwright.dev/docs/best-practices)
- [Test Orchestration](https://playwright.dev/docs/test-parallel)
- [Performance Testing](https://playwright.dev/docs/test-performance)
