# Lightweight Integration Testing

## Overview

This document describes the lightweight integration testing approach for CTI Scraper, which focuses on critical paths while reducing environment dependencies through mocking and in-memory databases.

## Philosophy

### Critical Paths Focus
- **Data ingestion**: RSS → Processing → Storage
- **Content analysis**: Articles → Quality Assessment → Analysis Dashboard  
- **Source management**: Source config → Collection → Health monitoring
- **API consistency**: HTML pages ↔ API endpoints

### Reduced Environment Dependency
- **Mock external services** (RSS feeds, external APIs)
- **Use test databases** instead of production data
- **Isolate components** so one failure doesn't cascade
- **Minimize setup complexity** (fewer moving parts)

## Test Categories

### 1. Lightweight Integration Tests (`integration_light`)
- **Purpose**: Test critical paths with mocked dependencies
- **Speed**: Fast (< 30 seconds)
- **Dependencies**: Minimal (no Docker, no external services)
- **Use cases**: Development, CI/CD, rapid feedback

### 2. Full Integration Tests (`integration_full`)
- **Purpose**: Test complete system with real environment
- **Speed**: Slow (2-5 minutes)
- **Dependencies**: Full Docker stack, PostgreSQL, Redis
- **Use cases**: Pre-deployment validation, system verification

### 3. Unit Tests (`unit`)
- **Purpose**: Test individual components in isolation
- **Speed**: Very fast (< 10 seconds)
- **Dependencies**: None
- **Use cases**: Development, refactoring, component testing

## Test Structure

```
tests/
├── integration/
│   ├── test_lightweight_integration.py    # Lightweight integration tests
│   └── test_system_integration.py         # Full integration tests
├── conftest.py                            # Full integration fixtures
├── conftest_lightweight.py                # Lightweight integration fixtures
├── run_lightweight_tests.py               # Legacy test runner script
└── run_tests.py                           # Unified test runner (recommended)
```

## Running Tests

### Using the Unified Test Runner (Recommended)
```bash
# Run lightweight integration tests
python3 run_tests.py --integration

# Run full integration tests (Docker-based)
python3 run_tests.py --docker --integration

# Run unit tests
python3 run_tests.py --unit

# Run smoke tests (quick health check)
python3 run_tests.py --smoke
```

### Using the Legacy Test Runner
```bash
# Run lightweight integration tests
python3 tests/run_lightweight_tests.py light

# Run full integration tests (requires Docker)
python3 tests/run_lightweight_tests.py full

# Run unit tests only
python3 tests/run_lightweight_tests.py unit

# Run critical path tests
python3 tests/run_lightweight_tests.py critical

# Run all tests
python3 tests/run_lightweight_tests.py all
```

### Using pytest directly

```bash
# Lightweight integration tests
pytest -m integration_light tests/integration/test_lightweight_integration.py

# Full integration tests
pytest -m integration_full tests/integration/

# Unit tests
pytest -m unit tests/

# All tests
pytest tests/
```

## Test Fixtures

### Lightweight Fixtures (`conftest_lightweight.py`)

- `mock_database_manager`: Mock database with sample data
- `mock_http_client`: Mock HTTP client with RSS responses
- `mock_content_processor`: Mock content processing
- `sample_articles`: Pre-defined test articles
- `sample_sources`: Pre-defined test sources
- `mock_quality_assessor`: Mock quality assessment service
- `mock_source_manager`: Mock source management
- `mock_environment`: Complete mocked environment

### Full Integration Fixtures (`conftest.py`)

- `async_client`: Real HTTP client for API testing
- `browser`: Playwright browser for UI testing
- `page`: Playwright page for UI interactions

## Critical Path Tests

### 1. Data Ingestion Pipeline
```python
@pytest.mark.integration_light
async def test_rss_to_database_flow(mock_http_client, mock_database_manager, sample_source):
    """Test complete RSS parsing to database storage flow."""
    # Parse RSS feed
    articles = await rss_parser.parse_feed(sample_source)
    
    # Store in database
    stored_article = await mock_database_manager.create_article(article)
    
    # Verify flow
    assert len(articles) == 1
    assert stored_article.id == 1
```

### 2. Content Analysis Pipeline
```python
@pytest.mark.integration_light
async def test_article_quality_assessment(mock_quality_assessor, sample_articles):
    """Test article quality assessment pipeline."""
    assessment = await mock_quality_assessor.assess_article(sample_articles[0])
    
    assert assessment["ttp_score"] == 75
    assert assessment["quality_level"] == "Good"
```

### 3. Source Management Pipeline
```python
@pytest.mark.integration_light
async def test_source_config_loading(mock_source_manager, mock_source_config):
    """Test source configuration loading and validation."""
    sources = await mock_source_manager.load_sources_from_config("config/sources.yaml")
    
    assert len(sources) == 1
    assert sources[0].identifier == "test-source-1"
```

### 4. API Consistency Pipeline
```python
@pytest.mark.integration_light
def test_api_endpoint_consistency(mock_fastapi_app):
    """Test consistency between API endpoints."""
    response = mock_fastapi_app.get("/api/articles")
    
    assert response.status_code == 200
    assert "articles" in response.json()
```

## Benefits

### Development Benefits
- **Faster feedback**: Tests run in seconds, not minutes
- **Easier debugging**: Isolated components, clear error messages
- **Reduced setup**: No Docker required for most tests
- **Better coverage**: Focus on critical paths

### CI/CD Benefits
- **More reliable**: Fewer flaky tests due to external dependencies
- **Faster pipelines**: Quick feedback on critical functionality
- **Better resource usage**: No need for full environment in every run
- **Parallel execution**: Multiple test suites can run simultaneously

### Maintenance Benefits
- **Easier maintenance**: Mocked dependencies are stable
- **Better documentation**: Tests serve as living documentation
- **Clearer intent**: Focus on what matters most
- **Reduced complexity**: Simpler test setup and teardown

## Best Practices

### 1. Mock Strategy
- **Mock external dependencies**: RSS feeds, APIs, databases
- **Keep business logic real**: Test actual processing logic
- **Use realistic data**: Mock responses should match real data structure
- **Test error conditions**: Mock failures and error responses

### 2. Test Organization
- **Group by critical path**: Organize tests by user journey
- **Use descriptive names**: Test names should explain the scenario
- **Keep tests focused**: One critical path per test
- **Use appropriate markers**: Mark tests for different environments

### 3. Data Management
- **Use fixtures**: Reusable test data and mocks
- **Keep data minimal**: Only include what's needed for the test
- **Use realistic data**: Test data should match production patterns
- **Clean up properly**: Ensure tests don't leave side effects

### 4. Performance Considerations
- **Mock expensive operations**: Database queries, HTTP requests
- **Use in-memory alternatives**: SQLite, mock databases
- **Parallel execution**: Run independent tests in parallel
- **Timeout management**: Set appropriate timeouts for async operations

## Migration Strategy

### Phase 1: Add Lightweight Tests
1. Create `test_lightweight_integration.py`
2. Add `conftest_lightweight.py` with mocked fixtures
3. Implement critical path tests with mocks
4. Add test markers and runner script

### Phase 2: Update Existing Tests
1. Add `integration_full` markers to existing integration tests
2. Keep full integration tests for system validation
3. Update CI/CD to run appropriate test suites
4. Document test categories and usage

### Phase 3: Optimize and Maintain
1. Monitor test performance and reliability
2. Add new critical paths as system evolves
3. Refine mocking strategies based on experience
4. Update documentation and best practices

## Troubleshooting

### Common Issues

#### 1. Mock Not Working
```python
# Ensure mock is properly configured
mock_client.get.return_value = mock_response
mock_client.get.assert_called_once()
```

#### 2. Async Test Failures
```python
# Use proper async fixtures
@pytest.mark.asyncio
async def test_async_function(mock_async_client):
    result = await mock_async_client.get("/api/test")
    assert result.status_code == 200
```

#### 3. Fixture Scope Issues
```python
# Use appropriate fixture scope
@pytest.fixture(scope="function")  # or "session", "module"
def mock_database():
    return AsyncMock()
```

### Debugging Tips

1. **Use verbose output**: `pytest -v` for detailed test information
2. **Check mock calls**: `mock.assert_called_with()` to verify interactions
3. **Isolate failures**: Run individual tests to identify issues
4. **Check fixture scope**: Ensure fixtures are available when needed
5. **Verify async setup**: Ensure async fixtures are properly configured

## Future Enhancements

### Planned Improvements
1. **Test data generation**: Automated test data creation
2. **Performance benchmarking**: Track test execution times
3. **Coverage analysis**: Ensure critical paths are fully covered
4. **Test visualization**: Dashboard for test results and trends
5. **Automated test discovery**: Auto-detect new critical paths

### Integration Opportunities
1. **CI/CD integration**: Automated test suite selection
2. **Monitoring integration**: Test results in system monitoring
3. **Documentation generation**: Auto-generate test documentation
4. **Performance regression detection**: Track test performance over time

## Conclusion

Lightweight integration testing provides a balanced approach to testing critical paths while maintaining development velocity. By focusing on what matters most and reducing environment dependencies, we can achieve:

- **Faster feedback** during development
- **More reliable CI/CD** pipelines
- **Better developer experience** with easier test setup
- **Maintained confidence** in critical system functionality

This approach complements full integration testing by providing rapid validation of critical paths while preserving comprehensive system testing for deployment validation.

