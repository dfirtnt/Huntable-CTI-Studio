# 🐍 Pytest Fundamentals

Core pytest concepts and usage for CTI Scraper testing.

## 🎯 Overview

Pytest is the primary testing framework for CTI Scraper. This guide covers essential concepts and patterns.

## 📦 Dependencies

```bash
# Install test dependencies using unified interface
python run_tests.py --install

# Or manually install from requirements
pip install -r requirements-test.txt

# Core testing dependencies
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-playwright>=0.4.0
httpx>=0.24.0
faker>=18.0.0
coverage>=7.0.0
```

## 🏗️ Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_basic.py            # Basic functionality tests
├── test_core.py             # Core system tests
├── test_database.py         # Database tests
├── test_utils.py            # Utility function tests
├── api/                     # API endpoint tests
│   └── test_endpoints.py
├── e2e/                     # End-to-end tests
│   ├── test_web_interface.py
│   └── mcp_orchestrator.py
├── integration/             # Integration tests
│   └── test_system_integration.py
└── utils/                   # Test utilities
    └── test_data_generator.py
```

## 🔧 Configuration

### pytest.ini
```ini
[tool:pytest]
testpaths = tests
markers =
    slow: marks tests as slow
    ui: marks tests as UI tests
    api: marks tests as API tests
    integration: marks tests as integration tests
    smoke: marks tests as smoke tests
asyncio_mode = auto
```

### Environment Variables
```bash
# .env
TESTING=true
DATABASE_URL=postgresql://user:pass@postgres/test_db
REDIS_URL=redis://localhost:6379
CTI_SCRAPER_URL=http://localhost:8001  # Default port, change if needed
```

## 🎭 Fixtures

### Basic Fixtures
```python
# conftest.py
import pytest
import httpx
from playwright.async_api import async_playwright

@pytest.fixture
def sample_article():
    """Sample article data for testing."""
    return {
        "title": "Test Article",
        "content": "Test content",
        "url": "https://example.com/test"
    }

@pytest.fixture
async def async_client():
    """Async HTTP client for API testing."""
    async with httpx.AsyncClient() as client:
        yield client

@pytest.fixture
async def browser_page():
    """Playwright browser page for UI testing."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()
```

### Database Fixtures
```python
@pytest.fixture
def test_db():
    """Test database connection."""
    # Setup test database
    yield db_connection
    # Cleanup after test
```

## 🧪 Test Examples

### Basic Test
```python
def test_article_creation(sample_article):
    """Test article creation functionality."""
    article = create_article(sample_article)
    assert article.title == "Test Article"
    assert article.url == "https://example.com/test"
```

### Async Test
```python
@pytest.mark.asyncio
async def test_api_endpoint(async_client):
    """Test API endpoint response."""
    response = await async_client.get("/api/articles")
    assert response.status_code == 200
    data = response.json()
    assert "articles" in data
```

### UI Test
```python
@pytest.mark.ui
async def test_homepage_loads(browser_page):
    """Test homepage loads correctly."""
    await browser_page.goto("http://localhost:8001/")
    title = await browser_page.title()
    assert "CTI Scraper" in title
```

## 🏷️ Test Markers

### Using Markers
```python
@pytest.mark.slow
def test_performance():
    """Marked as slow for separate execution."""
    pass

@pytest.mark.api
def test_api_response():
    """Marked for API testing."""
    pass

@pytest.mark.ui
def test_user_interface():
    """Marked for UI testing."""
    pass
```

### Running Marked Tests
```bash
# Run only API tests
pytest -m api

# Run all except slow tests
pytest -m "not slow"

# Run UI and API tests
pytest -m "ui or api"
```

## 🔍 Assertions

### Basic Assertions
```python
def test_basic_assertions():
    """Basic assertion examples."""
    assert True
    assert 1 + 1 == 2
    assert "hello" in "hello world"
    assert len([1, 2, 3]) == 3
```

### Exception Testing
```python
def test_exception_handling():
    """Test exception handling."""
    with pytest.raises(ValueError):
        raise ValueError("Invalid input")
    
    with pytest.raises(ValueError, match="Invalid input"):
        raise ValueError("Invalid input")
```

### Async Assertions
```python
@pytest.mark.asyncio
async def test_async_assertions():
    """Async assertion examples."""
    result = await async_function()
    assert result is not None
    assert result.status == "success"
```

## 📊 Test Data

### Using Faker
```python
from faker import Faker

fake = Faker()

def test_with_fake_data():
    """Test with generated fake data."""
    article_data = {
        "title": fake.sentence(),
        "content": fake.text(),
        "author": fake.name(),
        "url": fake.url()
    }
    # Test with generated data
```

### Test Data Files
```python
# tests/data/sample_articles.json
{
    "articles": [
        {
            "title": "Sample Article 1",
            "content": "Sample content 1"
        }
    ]
}

# In test
def test_with_data_file():
    """Test using data from file."""
    with open("tests/data/sample_articles.json") as f:
        data = json.load(f)
    # Use data in test
```

## 🚀 Running Tests

### Using Unified Interface
```bash
# Quick health check
python run_tests.py --smoke
./run_tests.sh smoke

# Run all tests
python run_tests.py --all
./run_tests.sh all

# Run with coverage
python run_tests.py --all --coverage
./run_tests.sh all --coverage

# Docker-based testing
python run_tests.py --docker --integration
./run_tests.sh integration --docker
```

### Basic Commands
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_basic.py

# Run specific test function
pytest tests/test_basic.py::test_article_creation

# Run with coverage
pytest --cov=src --cov-report=html
```

### Advanced Commands
```bash
# Run in parallel
pytest -n auto

# Stop on first failure
pytest --maxfail=1

# Run only failed tests from last run
pytest --lf

# Run tests matching pattern
pytest -k "test_article"

# Run with debug output
pytest -s --log-cli-level=DEBUG
```

## 🔧 Debugging

### Debug Mode
```bash
# Run with debug output
pytest -s -v --log-cli-level=DEBUG

# Run single test with debug
pytest tests/test_basic.py::test_article_creation -s -v
```

### Using pdb
```python
def test_with_debugger():
    """Test with debugger breakpoint."""
    result = some_function()
    import pdb; pdb.set_trace()  # Breakpoint
    assert result is not None
```

### Playwright Debug
```bash
# Run with visible browser
pytest tests/e2e/ -v --headed=true

# Run with Playwright debug
PWDEBUG=1 pytest tests/e2e/ -s
```

## 📈 Best Practices

### Test Design
- **Single Responsibility**: One assertion per test
- **Descriptive Names**: Clear test purpose
- **Setup/Teardown**: Proper test isolation
- **Mock External**: External service simulation

### Test Organization
- **Group Related Tests**: Use classes or modules
- **Use Fixtures**: Reusable test setup
- **Mark Tests**: Use markers for categorization
- **Keep Tests Fast**: Avoid slow operations

### Maintenance
- **Regular Updates**: Keep dependencies current
- **Test Data**: Refresh test data regularly
- **Coverage Goals**: Maintain coverage targets
- **Performance Baselines**: Track performance trends

## 🎯 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)
- **Test API endpoints** → [API Testing](API_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)

## 📚 Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Playwright Python](https://playwright.dev/python/)
- [Faker Documentation](https://faker.readthedocs.io/)
