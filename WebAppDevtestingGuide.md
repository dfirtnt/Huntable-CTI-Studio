# Web App Development Testing Guide

This guide provides comprehensive instructions for testing the CTI Scraper web application using various testing tools and methodologies.

## Overview

The CTI Scraper web application testing strategy includes:
- **Docker Playwright E2E Testing**: Primary testing method for full application testing
- **IDE Debugging**: Development debugging and testing
- **GitHub Actions CI/CD**: Automated testing pipeline
- **Manual Testing**: Interactive testing for specific scenarios
- **ML Feedback Regression Tests**: Essential tests for ML feedback features

## Testing Tools

### Primary Tools

1. **Docker Playwright**: End-to-end testing in containerized environment
2. **Browser Extensions**: DebugBrowser-Agent for error viewing
3. **FastAPI Test Client**: API endpoint testing
4. **PostgreSQL Testing**: Database integration testing

### Development Tools

1. **Cursor IDE**: Primary development environment
2. **IDE Debugging**: Development environment debugging tools
3. **Docker Compose**: Container orchestration for testing
4. **GitHub Actions**: Continuous integration testing

## Docker Playwright E2E Testing

### Setup

```bash
# Start the application
./start.sh

# Verify services are running
docker-compose ps

# Check web interface
curl http://localhost:8001/health
```

### Test Execution

```bash
# Run E2E tests
docker-compose run --rm web python -m pytest tests/e2e/ -v

# Run specific test scenarios
docker-compose run --rm web python -m pytest tests/e2e/test_dashboard.py -v

# Run with browser automation
docker-compose run --rm web python -m pytest tests/e2e/test_article_flow.py --browser=chromium -v
```

### Test Scenarios

#### 1. Dashboard Testing
- **Page Load**: Verify dashboard loads correctly
- **Statistics Display**: Check real-time statistics
- **Source Health**: Monitor source status indicators
- **Recent Articles**: Verify article list display

#### 2. Article Management
- **Article Listing**: Test pagination and filtering
- **Article Detail**: Verify content display and metadata
- **Classification**: Test chosen/rejected functionality
- **Search**: Test search functionality

#### 3. Source Management
- **Source Configuration**: Test source CRUD operations
- **Health Monitoring**: Verify source status updates
- **Collection Testing**: Test manual collection triggers
- **Configuration Updates**: Test source setting changes

#### 4. AI Features
- **SIGMA Rule Generation**: Test AI-powered rule creation
- **IOC Extraction**: Test indicator extraction
- **RAG Chat**: Test semantic search interface
- **Content Analysis**: Test AI-powered content analysis

## IDE Debugging

### Browser Developer Tools

Use browser developer tools for debugging web application issues:

1. **Open DevTools**: F12 or right-click → Inspect
2. **Console Tab**: View JavaScript errors and logs
3. **Network Tab**: Monitor API requests and responses
4. **Elements Tab**: Inspect DOM structure and CSS
5. **Sources Tab**: Set breakpoints and debug JavaScript

### Debug Commands

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# View application logs
docker-compose logs -f web

# Debug specific service
docker-compose exec web bash
```

## API Testing

### FastAPI Test Client

```python
from fastapi.testclient import TestClient
from src.web.modern_main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_articles_endpoint():
    response = client.get("/api/articles")
    assert response.status_code == 200
    assert "articles" in response.json()
```

### API Test Categories

1. **Health Endpoints**: `/health`, `/api/health`
2. **Article Endpoints**: `/api/articles/*`
3. **Source Endpoints**: `/api/sources/*`
4. **AI Endpoints**: `/api/chat/*`, `/api/articles/*/generate-sigma`
5. **Annotation Endpoints**: `/api/annotations/*`
6. **ML Feedback Endpoints**: `/api/model/*`, `/api/feedback/*`

## ML Feedback Testing

### Essential Regression Tests

The ML feedback features have dedicated regression prevention tests:

```bash
# Run the 3 critical ML feedback tests
./scripts/run_ml_feedback_tests.sh

# Run individual test categories
docker exec cti_web python -m pytest tests/integration/test_huntable_probability.py -v
docker exec cti_web python -m pytest tests/api/test_ml_feedback.py -v
docker exec cti_web python -m pytest tests/integration/test_retraining_integration.py -v
```

### ML Feedback Test Categories

1. **Huntable Probability Tests**: Ensure consistent probability calculations
2. **API Contract Tests**: Prevent frontend breakage from API changes
3. **Retraining Integration Tests**: Ensure core workflow functionality

### Test Philosophy

- **Balanced approach**: Maximum protection with minimum maintenance overhead
- **Focus on critical paths**: Test the most likely breakage scenarios
- **Integration tests**: Catch real-world issues, not just unit-level problems
- **Simple and maintainable**: Easy to understand and debug

See `tests/ML_FEEDBACK_TESTS_README.md` for detailed guidelines.

## Database Testing

### PostgreSQL Testing

```bash
# Connect to test database
docker exec cti_postgres psql -U cti_user -d cti_scraper

# Run database tests
docker-compose run --rm web python -m pytest tests/database/ -v
```

### Database Test Scenarios

1. **Schema Validation**: Verify table structure and constraints
2. **Data Integrity**: Test foreign key relationships
3. **Performance**: Test query performance and indexing
4. **Migration**: Test database migration scripts

## GitHub Actions CI/CD

### Workflow Configuration

The project includes GitHub Actions workflows for:

1. **CI Pipeline**: Automated testing on pull requests
2. **Security Scanning**: Dependency vulnerability checks
3. **Docker Testing**: Containerized test execution
4. **Artifact Collection**: Test reports and coverage

### CI Test Execution

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          docker-compose up -d
          docker-compose run --rm web python run_tests.py --all
```

## Manual Testing

### Test Scenarios

#### 1. User Interface Testing
- **Navigation**: Test all navigation links
- **Responsive Design**: Test on different screen sizes
- **Dark Mode**: Test theme switching
- **Accessibility**: Test keyboard navigation and screen readers

#### 2. Functional Testing
- **Source Management**: Add, edit, delete sources
- **Article Processing**: Test article collection and processing
- **AI Features**: Test SIGMA generation and IOC extraction
- **Export Functions**: Test data export capabilities
- **Chunk Debugger**:
  1. Open a long article (≥150 chunks) and trigger *Chunk Debug*.
  2. Confirm the ⚠️ Partial Analysis banner lists processed vs total chunks and that the *Finish Full Analysis* button appears.
  3. Click *Finish Full Analysis* and wait for the banner to switch to ✅ Full Analysis with all chunks rendered.
  4. Spot-check a chunk that previously timed out to ensure the warning message is present.
  5. Use **Show 40-60% Confidence** to surface (or confirm absence of) borderline chunks.

#### 3. Performance Testing
- **Page Load Times**: Measure page load performance
- **API Response Times**: Test API endpoint performance
- **Database Queries**: Test query performance
- **Memory Usage**: Monitor memory consumption

## Test Data Management

### Test Fixtures

```python
# tests/fixtures/sample_data.py
SAMPLE_ARTICLES = [
    {
        "title": "Test Article 1",
        "url": "https://example.com/test1",
        "content": "Test content for article 1",
        "source_id": 1
    },
    # ... more sample data
]
```

### Test Database

```bash
# Create test database
docker exec cti_postgres createdb cti_scraper_test

# Load test data
docker exec cti_postgres psql -U cti_user -d cti_scraper_test -f tests/fixtures/test_data.sql
```

## Debugging and Troubleshooting

### Common Issues

1. **Port Conflicts**: Check for conflicts on ports 8001, 5432, 6379
2. **Database Connection**: Ensure PostgreSQL container is running
3. **Environment Variables**: Verify `.env` file configuration
4. **Docker Issues**: Check Docker daemon status

### Debug Commands

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f web
docker-compose logs -f postgres
docker-compose logs -f redis

# Debug specific service
docker-compose exec web bash
docker-compose exec postgres psql -U cti_user -d cti_scraper
```

### Error Analysis

1. **Browser Console**: Check browser developer tools
2. **Server Logs**: Review application logs
3. **Database Logs**: Check PostgreSQL logs
4. **Network Issues**: Verify network connectivity

## Performance Optimization

### Testing Performance

```bash
# Load testing
docker-compose run --rm web python -m pytest tests/performance/ -v

# Memory profiling
docker-compose run --rm web python -m pytest tests/performance/test_memory.py -v

# Database performance
docker-compose run --rm web python -m pytest tests/performance/test_database.py -v
```

### Optimization Areas

1. **Database Queries**: Optimize slow queries
2. **API Endpoints**: Improve response times
3. **Frontend Assets**: Optimize CSS and JavaScript
4. **Caching**: Implement effective caching strategies

## Security Testing

### Security Test Categories

1. **Input Validation**: Test for SQL injection, XSS
2. **Authentication**: Test access controls
3. **Data Protection**: Test data encryption and privacy
4. **API Security**: Test API endpoint security

### Security Test Execution

```bash
# Run security tests
docker-compose run --rm web python -m pytest tests/security/ -v

# Dependency scanning
docker-compose run --rm web python -m safety check

# Code analysis
docker-compose run --rm web python -m bandit -r src/
```

## Test Reporting

### Coverage Reports

```bash
# Generate coverage report
docker-compose run --rm web python run_tests.py --all --coverage

# View coverage report
open htmlcov/index.html
```

### Test Reports

```bash
# Generate test report
docker-compose run --rm web python -m pytest --html=report.html --self-contained-html

# View test report
open report.html
```

## Best Practices

### Test Development

1. **Write Tests First**: Use TDD approach
2. **Test Isolation**: Ensure tests don't depend on each other
3. **Mock External Dependencies**: Use mocks for external services
4. **Clean Test Data**: Use fixtures for consistent test data

### Test Maintenance

1. **Regular Updates**: Keep tests current with code changes
2. **Performance Monitoring**: Track test execution time
3. **Coverage Monitoring**: Maintain coverage targets
4. **Documentation**: Keep test documentation current

## Resources

### Documentation

- [Docker Architecture Guide](docs/deployment/DOCKER_ARCHITECTURE.md)
- [API Endpoints Reference](docs/API_ENDPOINTS.md)
- [Testing Guide](docs/development/TESTING_GUIDE.md)

### Tools

- **Playwright**: Browser automation and testing
- **FastAPI Test Client**: API testing
- **Pytest**: Test framework
- **Docker**: Containerized testing

---

**Note**: This guide is maintained alongside the codebase. For the most up-to-date information, refer to the test files and configuration in the repository.
