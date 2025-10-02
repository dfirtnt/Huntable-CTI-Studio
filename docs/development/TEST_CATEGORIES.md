# 📋 Test Categories

Understanding different test types and their purposes in CTI Scraper.

## 🎯 Overview

CTI Scraper uses a comprehensive testing strategy with multiple test categories, each serving a specific purpose in the quality assurance process.

## 🔥 Smoke Tests

### Purpose
Quick health check of critical functionality to verify the system is working.

### Scope
- Core endpoints and basic navigation
- Essential features and system health
- Database connectivity
- Service availability

### Duration
~30 seconds

### Use Cases
- Pre-deployment verification
- Daily health checks
- CI/CD pipeline validation
- Quick system status verification

### Examples
```python
@pytest.mark.smoke
def test_homepage_loads():
    """Verify homepage loads successfully."""
    response = requests.get("http://localhost:8001/")
    assert response.status_code == 200

@pytest.mark.smoke
def test_database_connection():
    """Verify database connectivity."""
    result = db.execute("SELECT 1")
    assert result is not None
```

### Running Smoke Tests
```bash
# Run smoke tests only
python run_tests.py --smoke
./run_tests.sh smoke

# Run with pytest
pytest -m smoke
```

## 🌐 API Tests

### Purpose
Test all API endpoints and ensure data consistency across the system.

### Scope
- JSON API responses and structure
- HTTP status codes and error handling
- Data validation and serialization
- Authentication and authorization
- Rate limiting and performance

### Duration
~1-2 minutes

### Use Cases
- API development and integration
- Backend service validation
- Data consistency verification
- Third-party integration testing

### Examples
```python
@pytest.mark.api
async def test_articles_api(async_client):
    """Test articles API endpoint."""
    response = await async_client.get("/api/articles")
    assert response.status_code == 200
    
    data = response.json()
    assert "articles" in data
    assert isinstance(data["articles"], list)

@pytest.mark.api
async def test_api_error_handling(async_client):
    """Test API error handling."""
    response = await async_client.get("/api/nonexistent")
    assert response.status_code == 404
```

### Running API Tests
```bash
# Run API tests only
python run_tests.py --api
./run_tests.sh api

# Run with pytest
pytest -m api
```

## 🖥️ UI Tests

### Purpose
End-to-end user interface testing with Playwright to verify user workflows.

### Scope
- User flows and navigation
- Form submissions and interactions
- Responsive design and accessibility
- Error handling and user feedback
- Visual elements and layout

### Duration
~3-5 minutes

### Use Cases
- UI development and validation
- User experience testing
- Cross-browser compatibility
- Accessibility compliance

### Examples
```python
@pytest.mark.ui
async def test_dashboard_navigation(page):
    """Test navigation between dashboard sections."""
    await page.goto("http://localhost:8001/")
    
    # Verify dashboard loads
    await expect(page).to_have_title("CTI Scraper")
    
    # Test navigation to articles
    await page.click("text=Articles")
    await expect(page).to_have_url("http://localhost:8001/articles")

@pytest.mark.ui
async def test_source_management(page):
    """Test source management functionality."""
    await page.goto("/sources")
    await page.click("button:has-text('Add Source')")
    
    # Fill form
    await page.fill("input[name='name']", "Test Source")
    await page.fill("input[name='url']", "https://example.com")
    await page.click("button:has-text('Save')")
    
    # Verify source was added
    await expect(page.locator("text=Test Source")).to_be_visible()
```

### Running UI Tests
```bash
# Run UI tests only
python run_tests.py --ui
./run_tests.sh ui

# Run with pytest
pytest -m ui

# Run with visible browser
pytest -m ui --headed=true
```

## 🔗 Integration Tests

### Purpose
Test system-wide data flow and component interaction to ensure everything works together.

### Scope
- Database connectivity and transactions
- Service integration and communication
- Data consistency across components
- End-to-end workflows
- External service integration

### Duration
~2-3 minutes

### Use Cases
- System integration validation
- End-to-end workflow testing
- Data flow verification
- Service communication testing

### Examples
```python
@pytest.mark.integration
def test_article_processing_workflow():
    """Test complete article processing workflow."""
    # 1. Add source
    source = add_source("https://example.com/feed")
    
    # 2. Trigger collection
    trigger_collection(source.id)
    
    # 3. Verify article was processed
    articles = get_articles()
    assert len(articles) > 0
    
    # 4. Verify scoring was applied
    article = articles[0]
    assert article.threat_score is not None

@pytest.mark.integration
def test_database_transactions():
    """Test database transaction handling."""
    with db.transaction():
        article = create_article(test_data)
        annotation = create_annotation(article.id)
        
        # Verify both were created
        assert article.id is not None
        assert annotation.article_id == article.id
```

### Running Integration Tests
```bash
# Run integration tests only
python run_tests.py --integration
./run_tests.sh integration

# Docker-based integration tests (recommended)
python run_tests.py --docker --integration
./run_tests.sh integration --docker

# Run with pytest
pytest -m integration
```

## 📊 Coverage Tests

### Purpose
Comprehensive testing with code coverage analysis to ensure complete system validation.

### Scope
- All test categories combined
- Code coverage analysis
- Performance metrics
- Quality gates validation

### Duration
~5-8 minutes

### Use Cases
- Quality assurance and validation
- Development completion verification
- Release preparation
- Coverage target maintenance

### Examples
```python
@pytest.mark.coverage
def test_comprehensive_coverage():
    """Test with coverage analysis."""
    # Run all test categories
    # Generate coverage report
    # Validate coverage targets
    pass
```

### Running Coverage Tests
```bash
# Run coverage tests
python run_tests.py --coverage
./run_tests.sh all --coverage

# Run with pytest
pytest --cov=src --cov-report=html --cov-fail-under=80
```

## 🎭 Test Markers

### Available Markers
```python
@pytest.mark.smoke        # Quick health checks
@pytest.mark.api          # API endpoint tests
@pytest.mark.ui           # User interface tests
@pytest.mark.integration  # System integration tests
@pytest.mark.coverage     # Coverage analysis tests
@pytest.mark.slow         # Slow-running tests
@pytest.mark.regression   # Regression tests
```

### Custom Markers
```python
# pytest.ini
[tool:pytest]
markers =
    smoke: marks tests as smoke tests
    api: marks tests as API tests
    ui: marks tests as UI tests
    integration: marks tests as integration tests
    coverage: marks tests as coverage tests
    slow: marks tests as slow
    regression: marks tests as regression tests
```

## 🚀 Running Test Categories

### Using run_tests.py
```bash
# Run specific categories
python run_tests.py --smoke
python run_tests.py --api
python run_tests.py --ui
python run_tests.py --integration
python run_tests.py --coverage

# Run all tests
python run_tests.py --all

# Docker-based testing
python run_tests.py --docker --integration
python run_tests.py --docker --all --coverage
```

### Using run_tests.sh (Unified Script)
```bash
# Run specific categories
./run_tests.sh smoke
./run_tests.sh api
./run_tests.sh ui
./run_tests.sh integration

# Run with coverage
./run_tests.sh all --coverage

# Docker-based testing
./run_tests.sh integration --docker
./run_tests.sh all --coverage --docker
```

### Using pytest directly
```bash
# Run by marker
pytest -m smoke
pytest -m api
pytest -m ui
pytest -m integration

# Run multiple categories
pytest -m "smoke or api"
pytest -m "ui and not slow"

# Run with specific options
pytest -m ui --headed=true
pytest -m api -v
pytest -m integration --maxfail=1
```

## 📈 Test Execution Strategy

### Development Workflow
1. **Write code** → Run smoke tests
2. **Add features** → Run API/UI tests
3. **Integration** → Run integration tests
4. **Release prep** → Run coverage tests

### CI/CD Pipeline
1. **Pull Request** → Smoke + API tests
2. **Merge to main** → All test categories
3. **Release** → Coverage tests + performance

### Local Development
1. **Quick feedback** → Smoke tests
2. **Feature validation** → Specific category
3. **Full validation** → All tests

## 🎯 Best Practices

### Test Category Selection
- **Use smoke tests** for quick validation
- **Use API tests** for backend development
- **Use UI tests** for frontend development
- **Use integration tests** for system validation
- **Use coverage tests** for quality assurance

### Test Organization
- **Group related tests** by category
- **Use appropriate markers** for categorization
- **Maintain test isolation** between categories
- **Keep tests focused** on their purpose

### Performance Considerations
- **Run smoke tests frequently** (fast feedback)
- **Run API tests regularly** (moderate speed)
- **Run UI tests less frequently** (slower execution)
- **Run integration tests before releases** (comprehensive validation)

## 📚 Next Steps

- **Learn pytest basics** → [Pytest Fundamentals](PYTEST_FUNDAMENTALS.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Test API endpoints** → [API Testing](API_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)

## 🔍 Troubleshooting

### Common Issues
- **Tests failing** → Check test category and scope
- **Slow execution** → Use appropriate test categories
- **Missing coverage** → Run coverage tests
- **Flaky tests** → Check test isolation and dependencies

### Debug Commands
```bash
# Debug specific category
pytest -m smoke -v -s
pytest -m api --tb=long
pytest -m ui --headed=true

# Check test markers
pytest --markers
```
