# Development Setup Guide

Comprehensive guide for setting up the CTIScraper development environment, including pytest configuration, virtual environments, and testing frameworks.

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [Virtual Environments](#virtual-environments)
3. [Pytest Configuration](#pytest-configuration)
4. [Test Framework](#test-framework)
5. [Dependencies](#dependencies)
6. [Configuration Files](#configuration-files)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

## Environment Setup

### Prerequisites

- **Docker uses Python 3.11** (standardized in Dockerfile)
- **Local development**: Python 3.11+ recommended for most environments
- **ML environment**: Python 3.9.6 for specific ML library compatibility (local venv only)
- Docker and Docker Compose
- Git

### Quick Setup

```bash
# Clone repository
git clone <repository-url>
cd CTIScraper

# Start application
./start.sh

# Install test dependencies
python run_tests.py --install
```

## Virtual Environments

CTIScraper uses multiple virtual environments for different development workflows:

### 1. `venv-test` (Python 3.13.7 - local only)
**Purpose**: Testing and development
- **Primary use**: Running tests locally against Dockerized application
- **Note**: Docker containers use Python 3.11; this local venv can use 3.13.7 for latest tooling
- **Dependencies**: All testing frameworks and tools
- **Activation**: `source venv-test/bin/activate`
- **Usage**: `python run_tests.py --smoke`

### 2. `venv-lg` (Python 3.13.7 - local only)
**Purpose**: LG workflow (commit + push + GitHub hygiene)
- **Primary use**: Code quality, security auditing, documentation generation
- **Note**: Docker containers use Python 3.11; this local venv can use 3.13.7 for latest tooling
- **Dependencies**: Development tools, security scanners, documentation generators
- **Activation**: `source venv-lg/bin/activate`
- **Usage**: Triggered by `lg` command for GitHub hygiene

### 3. `venv-ml` (Python 3.9.6 - local only)
**Purpose**: ML/AI tasks and fine-tuning
- **Primary use**: Machine learning experiments, model training, AI analysis
- **Note**: Docker containers use Python 3.11; this local venv uses 3.9.6 for specific ML library compatibility
- **Dependencies**: ML libraries, data science tools, specific Python 3.9 compatibility
- **Activation**: `source venv-ml/bin/activate`
- **Usage**: ML experiments and model development

### Creating Virtual Environments

```bash
# Testing environment
python3 -m venv venv-test
source venv-test/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt

# LG workflow environment
python3 -m venv venv-lg
source venv-lg/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt

# ML environment (Python 3.9)
python3.9 -m venv venv-ml
source venv-ml/bin/activate
pip install -r requirements.txt
# Install ML-specific dependencies as needed
```

### Environment Activation

```bash
# For testing
source venv-test/bin/activate

# For LG workflow
source venv-lg/bin/activate

# For ML tasks
source venv-ml/bin/activate
```

## Pytest Configuration

### Core Concepts

Pytest is the primary testing framework for CTIScraper. It provides:

- **Test Discovery**: Automatic test discovery and execution
- **Fixtures**: Reusable test setup and teardown
- **Markers**: Test categorization and filtering
- **Assertions**: Rich assertion capabilities
- **Plugins**: Extensive plugin ecosystem

### Dependencies

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

### Test Structure

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

### Configuration Files

#### pytest.ini
```ini
[tool:pytest]
testpaths = tests
markers =
    slow: marks tests as slow
    ui: marks tests as UI tests
    api: marks tests as API tests
    integration: marks tests as integration tests
    smoke: marks tests as smoke tests
    unit: marks tests as unit tests
asyncio_mode = auto
```

#### Environment Variables
```bash
# .env
TESTING=true
DATABASE_URL=postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper
REDIS_URL=redis://redis:6379/0
CTI_SCRAPER_URL=http://localhost:8001  # Default port, change if needed
```

## Test Framework

### Fixtures

#### Basic Fixtures
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

#### Database Fixtures
```python
@pytest.fixture
def test_db():
    """Test database connection."""
    # Setup test database
    yield db_connection
    # Cleanup after test
```

### Test Examples

#### Basic Test
```python
def test_article_creation(sample_article):
    """Test article creation functionality."""
    article = create_article(sample_article)
    assert article.title == "Test Article"
    assert article.url == "https://example.com/test"
```

#### Async Test
```python
@pytest.mark.asyncio
async def test_api_endpoint(async_client):
    """Test API endpoint response."""
    response = await async_client.get("/api/articles")
    assert response.status_code == 200
    data = response.json()
    assert "articles" in data
```

#### UI Test
```python
@pytest.mark.ui
async def test_homepage_loads(browser_page):
    """Test homepage loads correctly."""
    await browser_page.goto("http://localhost:8001/")
    title = await browser_page.title()
    assert "CTI Scraper" in title
```

### Test Markers

#### Available Markers
```python
@pytest.mark.smoke        # Quick health checks
@pytest.mark.api          # API endpoint tests
@pytest.mark.ui           # User interface tests
@pytest.mark.integration  # System integration tests
@pytest.mark.coverage     # Coverage analysis tests
@pytest.mark.slow         # Slow-running tests
@pytest.mark.regression   # Regression tests
```

#### Using Markers
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

#### Running Marked Tests
```bash
# Run only API tests
pytest -m api

# Run all except slow tests
pytest -m "not slow"

# Run UI and API tests
pytest -m "ui or api"
```

### Assertions

#### Basic Assertions
```python
def test_basic_assertions():
    """Basic assertion examples."""
    assert True
    assert 1 + 1 == 2
    assert "hello" in "hello world"
    assert len([1, 2, 3]) == 3
```

#### Exception Testing
```python
def test_exception_handling():
    """Test exception handling."""
    with pytest.raises(ValueError):
        raise ValueError("Invalid input")
    
    with pytest.raises(ValueError, match="Invalid input"):
        raise ValueError("Invalid input")
```

#### Async Assertions
```python
@pytest.mark.asyncio
async def test_async_assertions():
    """Async assertion examples."""
    result = await async_function()
    assert result is not None
    assert result.status == "success"
```

### Test Data

#### Using Faker
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

#### Test Data Files
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

## Dependencies

### Core Dependencies

```bash
# Core application dependencies
pip install -r requirements.txt

# Testing dependencies
pip install -r requirements-test.txt

# Development dependencies (for LG workflow)
pip install -r requirements-dev.txt
```

### Testing Dependencies

- **pytest**: Test framework and runner
- **pytest-asyncio**: Async test support
- **pytest-playwright**: Browser automation
- **httpx**: HTTP client for API testing
- **faker**: Test data generation
- **coverage**: Code coverage measurement

### Development Dependencies

- **black**: Code formatting
- **flake8**: Linting
- **mypy**: Type checking
- **bandit**: Security scanning
- **safety**: Dependency vulnerability checking

## Configuration Files

### Environment Configuration

#### .env File
```bash
# Application settings
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper
REDIS_URL=redis://redis:6379/0

# Testing settings
TESTING=true
CTI_SCRAPER_URL=http://localhost:8001

# API Keys (for real API tests)
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
```

#### Docker Configuration
```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres/cti_scraper
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
```

### Test Configuration

#### pytest.ini
```ini
[tool:pytest]
testpaths = tests
markers =
    slow: marks tests as slow
    ui: marks tests as UI tests
    api: marks tests as API tests
    integration: marks tests as integration tests
    smoke: marks tests as smoke tests
    unit: marks tests as unit tests
asyncio_mode = auto
```

#### conftest.py
```python
import pytest
import asyncio
from httpx import AsyncClient
from playwright.async_api import async_playwright

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def async_client():
    """Async HTTP client for API testing."""
    async with AsyncClient() as client:
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

## Best Practices

### Environment Management

1. **Environment Isolation**
   - Each virtual environment serves a specific purpose
   - Don't mix dependencies across environments
   - Use the appropriate environment for each task

2. **Dependency Management**
   - Keep `requirements.txt` updated for core dependencies
   - Use `requirements-test.txt` for testing-specific dependencies
   - Document ML-specific dependencies separately

3. **Environment Switching**
   - Always deactivate current environment before switching
   - Use `which python` to verify active environment
   - Check `pip list` to verify installed packages

4. **Docker Integration**
   - Application runs in Docker containers
   - Virtual environments are for local development tasks
   - Tests can run locally or in Docker containers

### Test Design

1. **Single Responsibility**: One assertion per test
2. **Descriptive Names**: Clear test purpose
3. **Setup/Teardown**: Proper test isolation
4. **Mock External**: External service simulation

### Test Organization

1. **Group Related Tests**: Use classes or modules
2. **Use Fixtures**: Reusable test setup
3. **Mark Tests**: Use markers for categorization
4. **Keep Tests Fast**: Avoid slow operations

### Maintenance

1. **Regular Updates**: Keep dependencies current
2. **Test Data**: Refresh test data regularly
3. **Coverage Goals**: Maintain coverage targets
4. **Performance Baselines**: Track performance trends

## Usage Patterns

### Testing Workflow
```bash
# Activate test environment
source venv-test/bin/activate

# Run tests
python run_tests.py --smoke
python run_tests.py --all --coverage

```

### LG Workflow
```bash
# Activate LG environment
source venv-lg/bin/activate

# Run LG workflow (commit + push + GitHub hygiene)
# This is typically triggered by the 'lg' command
```

### ML Workflow
```bash
# Activate ML environment
source venv-ml/bin/activate

# Run ML experiments
python scripts/ml_experiment.py
```

### Running Tests

#### Using Unified Interface
```bash
# Quick health check
python run_tests.py --smoke

# Run all tests
python run_tests.py --all

# Run with coverage
python run_tests.py --all --coverage

# Docker-based testing
python run_tests.py --docker --integration
```

#### Basic Commands
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

#### Advanced Commands
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

## Troubleshooting

### Common Issues

#### Environment not found
```bash
# Check if environment exists
ls -la venv-*/

# Recreate if missing
python3 -m venv venv-test
```

#### Wrong Python version
```bash
# Check Python version
python --version

# Use specific version for ML environment
python3.9 -m venv venv-ml
```

#### Dependencies not installed
```bash
# Install requirements
pip install -r requirements.txt
pip install -r requirements-test.txt
```

#### Environment conflicts
```bash
# Deactivate current environment
deactivate

# Activate correct environment
source venv-test/bin/activate
```

#### Tests failing
```bash
# Check test category and scope
pytest -m smoke -v

# Check test isolation and dependencies
pytest --tb=long
```

#### Slow execution
```bash
# Use appropriate test categories
pytest -m "not slow"

# Run tests in parallel
pytest -n auto
```

#### Missing coverage
```bash
# Run coverage tests
pytest --cov=src --cov-report=html

# Check coverage configuration
cat pytest.ini | grep cov
```

#### Flaky tests
```bash
# Check test isolation and dependencies
pytest --tb=long

# Run tests multiple times
pytest --count=3
```

### Debug Commands

```bash
# Debug specific category
pytest -m smoke -v -s
pytest -m api --tb=long
pytest -m ui --headed=true

# Check test markers
pytest --markers

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

## Integration with Docker

### Application Architecture
- **Application**: Runs in Docker containers
- **Development**: Uses virtual environments for local tasks
- **Testing**: Can run locally or in Docker containers

### Test Execution
```bash
# Local testing (using venv-test)
source venv-test/bin/activate
python run_tests.py --smoke

# Docker testing
python run_tests.py --docker --smoke

# Unified script
python run_tests.py --docker --smoke
```

## Maintenance

### Regular Updates
- Update dependencies monthly
- Check for security vulnerabilities
- Keep Python versions current

### Environment Cleanup
- Remove unused environments
- Clean up old dependencies
- Archive experimental environments

### Documentation
- Keep this guide updated
- Document new environments
- Update usage patterns

## Next Steps

- **Learn test categories** → See the testing guide in the tests directory
- **Test web interface** → [Web App Testing](WEB_APP_TESTING.md)

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Playwright Python](https://playwright.dev/python/)
- [Faker Documentation](https://faker.readthedocs.io/)
- [Docker Architecture Guide](../deployment/DOCKER_ARCHITECTURE.md)

---

*Last updated: January 2025*
