# Testing Guide

This document provides comprehensive guidance for testing the CTI Scraper application.

## Overview

The CTI Scraper uses a multi-layered testing approach with Docker-based testing, unit tests, integration tests, and end-to-end testing capabilities.

## Test Infrastructure

### Test Scripts

- **`run_tests.py`**: Unified Python test runner with multiple execution modes
- **`run_tests.sh`**: Shell wrapper for common test scenarios
- **`pytest.ini`**: Pytest configuration file

### Test Categories

1. **Smoke Tests**: Basic functionality verification
2. **Unit Tests**: Individual component testing
3. **Integration Tests**: Component interaction testing
4. **API Tests**: REST API endpoint testing
5. **UI Tests**: Web interface testing
6. **Docker Tests**: Containerized testing
7. **Backup Tests**: Backup system functionality and restore verification

## Quick Start

### Health Check (Recommended First Step)

```bash
# Quick smoke test
python run_tests.py --smoke
./run_tests.sh smoke
```

### Backup System Testing

```bash
# Test backup creation and restore
./run_tests.sh backup

# Test backup API endpoints
curl -X POST http://localhost:8001/api/backup/create
curl -X GET http://localhost:8001/api/backup/list
curl -X GET http://localhost:8001/api/backup/status
```

### Full Test Suite

```bash
# Run all tests with coverage
python run_tests.py --all --coverage
./run_tests.sh all --coverage
```

## Test Execution Modes

### Local Testing

```bash
# Unit tests only
python run_tests.py --unit
./run_tests.sh unit

# Integration tests
python run_tests.py --integration
./run_tests.sh integration

# API tests
python run_tests.py --api
./run_tests.sh api

# UI tests
python run_tests.py --ui
./run_tests.sh ui
```

### Docker Testing

```bash
# Run tests in Docker containers
python run_tests.py --docker --all
./run_tests.sh all --docker

# Specific test categories in Docker
python run_tests.py --docker --integration
./run_tests.sh integration --docker
```

## Test Dependencies

### Installation

```bash
# Install test dependencies
python run_tests.py --install
```

### Virtual Environments

The project uses multiple virtual environments for different purposes:

- **`venv-test/`**: Testing dependencies and tools
- **`venv-lg/`**: Local development environment
- **`venv-ml/`**: Machine learning and AI dependencies

## Test Structure

### Directory Layout

```
tests/
├── test_*.py              # Individual test modules
├── conftest.py           # Pytest configuration and fixtures
├── fixtures/             # Test data and fixtures
├── mocks/                # Mock objects and stubs
└── integration/          # Integration test suites
```

### Test Modules

1. **`test_content_filter.py`**: ML-based content filtering (25 tests)
2. **`test_sigma_validator.py`**: SIGMA rule validation (50 tests)
3. **`test_source_manager.py`**: Source configuration management (35 tests)
4. **`test_content_cleaner.py`**: HTML cleaning and text processing (30 tests)
5. **`test_http_client.py`**: HTTP client and rate limiting (38/39 tests)

## Writing Tests

### Test Structure

```python
import pytest
from src.core.models import Article

class TestArticleModel:
    """Test cases for Article model."""
    
    def test_article_creation(self):
        """Test article creation with valid data."""
        article = Article(
            title="Test Article",
            url="https://example.com/test",
            content="Test content"
        )
        assert article.title == "Test Article"
        assert article.url == "https://example.com/test"
    
    def test_article_validation(self):
        """Test article validation with invalid data."""
        with pytest.raises(ValueError):
            Article(title="", url="invalid-url")
```

### Fixtures

```python
@pytest.fixture
async def db_session():
    """Database session fixture."""
    async with async_db_manager.get_session() as session:
        yield session

@pytest.fixture
def sample_article():
    """Sample article fixture."""
    return Article(
        title="Sample Article",
        url="https://example.com/sample",
        content="Sample content for testing"
    )
```

## Docker Testing

### Prerequisites

- Docker and Docker Compose installed
- `.env` file configured
- Services running: `./start.sh`

### Docker Test Commands

```bash
# Run all tests in Docker
docker-compose run --rm web python run_tests.py --all

# Run specific test categories
docker-compose run --rm web python run_tests.py --unit
docker-compose run --rm web python run_tests.py --integration

# Run tests with coverage
docker-compose run --rm web python run_tests.py --all --coverage
```

### Docker Test Environment

- **Database**: PostgreSQL container with test data
- **Cache**: Redis container for testing
- **Services**: All services available for integration testing
- **Isolation**: Clean environment for each test run

## Coverage Reports

### Generating Coverage

```bash
# Generate HTML coverage report
python run_tests.py --all --coverage
open htmlcov/index.html

# Generate coverage for specific modules
python run_tests.py --unit --coverage
```

### Coverage Targets

- **Unit Tests**: 90%+ coverage
- **Integration Tests**: 80%+ coverage
- **API Tests**: 85%+ coverage
- **Overall**: 85%+ coverage

## Continuous Integration

### GitHub Actions

The project includes GitHub Actions workflows for:

- **CI Pipeline**: Automated testing on pull requests
- **Security Scanning**: Dependency vulnerability checks
- **Code Quality**: Linting and type checking
- **Docker Testing**: Containerized test execution

### Local CI Simulation

```bash
# Simulate CI pipeline locally
python run_tests.py --ci
./run_tests.sh ci
```

## Performance Testing

### Load Testing

```bash
# API endpoint load testing
python run_tests.py --load-test

# Database performance testing
python run_tests.py --db-performance
```

### Benchmarking

```bash
# Performance benchmarks
python run_tests.py --benchmark

# Memory usage testing
python run_tests.py --memory-test
```

## Debugging Tests

### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG python run_tests.py --unit

# Verbose test output
python run_tests.py --unit --verbose
```

### Test Isolation

```bash
# Run single test file
python run_tests.py --file tests/test_models.py

# Run specific test method
python run_tests.py --method test_article_creation
```

## Test Data Management

### Fixtures

- **`conftest.py`**: Global fixtures and configuration
- **`fixtures/`**: Test data files and samples
- **Database fixtures**: Automated test data setup

### Mocking

- **External APIs**: Mock HTTP requests
- **Database**: Use test database
- **File System**: Mock file operations
- **Time**: Mock datetime for consistent testing

## Best Practices

### Test Writing

1. **Descriptive Names**: Use clear, descriptive test names
2. **Single Responsibility**: Each test should verify one thing
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Mock External Dependencies**: Isolate units under test
5. **Clean Setup/Teardown**: Ensure test isolation

### Test Organization

1. **Group Related Tests**: Use test classes for related functionality
2. **Use Fixtures**: Share common setup code
3. **Parameterized Tests**: Test multiple scenarios efficiently
4. **Test Categories**: Organize tests by type and purpose

## Troubleshooting

### Common Issues

1. **Database Connection**: Ensure PostgreSQL container is running
2. **Port Conflicts**: Check for port conflicts on 8001, 5432, 6379
3. **Environment Variables**: Verify `.env` file configuration
4. **Dependencies**: Ensure all test dependencies are installed

### Debug Commands

```bash
# Check service status
docker-compose ps

# View test logs
docker-compose logs -f web

# Debug specific test
pytest tests/test_models.py::TestArticleModel::test_article_creation -v -s
```

## Test Maintenance

### Regular Tasks

1. **Update Test Data**: Keep fixtures current
2. **Review Coverage**: Maintain coverage targets
3. **Update Dependencies**: Keep test dependencies current
4. **Performance Monitoring**: Track test execution time

### Test Refactoring

1. **Remove Duplication**: Extract common test code
2. **Improve Readability**: Use descriptive names and comments
3. **Optimize Performance**: Reduce test execution time
4. **Update Assertions**: Use appropriate assertion methods

## Resources

### Documentation

- [Pytest Documentation](https://docs.pytest.org/)
- [Docker Testing Guide](docs/deployment/DOCKER_ARCHITECTURE.md)
- [API Testing Guide](docs/API_ENDPOINTS.md)

### Tools

- **Pytest**: Test framework and runner
- **Coverage.py**: Code coverage measurement
- **Docker**: Containerized testing
- **GitHub Actions**: Continuous integration

---

**Note**: This testing guide is maintained alongside the codebase. For the most up-to-date information, refer to the test files and configuration in the repository.
