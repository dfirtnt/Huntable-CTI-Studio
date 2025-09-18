# End-to-End Testing with Playwright

This directory contains end-to-end tests for CTIScraper using Playwright and MCP orchestration.

## Overview

The E2E test suite provides comprehensive testing of the CTIScraper web interface, including:

- **Web Interface Testing**: Homepage, navigation, and page functionality
- **API Testing**: REST API endpoints and responses
- **Source Management**: Adding, editing, and managing threat intelligence sources
- **Article Processing**: Content collection and threat hunting scoring
- **Responsive Design**: Mobile and desktop viewport testing
- **Performance Testing**: Page load times and responsiveness
- **Accessibility Testing**: Basic accessibility compliance

## Test Structure

```
tests/e2e/
├── conftest.py              # Pytest fixtures and configuration
├── test_web_interface.py    # Main E2E test suite
├── playwright_config.py     # Playwright configuration
├── mcp_orchestrator.py      # MCP-based test orchestration
└── README.md               # This file
```

## Running Tests

### Local Development

1. **Start CTIScraper**:
   ```bash
   docker-compose up -d
   ```

2. **Install Playwright**:
   ```bash
   pip install playwright pytest-playwright
   playwright install chromium
   ```

3. **Run E2E Tests**:
   ```bash
   # Run all E2E tests
   pytest tests/e2e/ -v
   
   # Run specific test
   pytest tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_homepage_loads -v
   
   # Run with browser visible
   pytest tests/e2e/ -v --headed=true
   ```

### CI/CD Pipeline

The GitHub Actions CI pipeline automatically runs E2E tests using the Playwright Docker image:

```yaml
# .github/workflows/ci.yml
services:
  playwright:
    image: mcr.microsoft.com/playwright:v1.40.0
```

## MCP Orchestration

The `mcp_orchestrator.py` provides intelligent test orchestration:

- **Health Checks**: Verifies application is running before tests
- **Test Execution**: Runs Playwright tests with proper configuration
- **Failure Analysis**: Analyzes test failures and suggests fixes
- **Report Generation**: Creates comprehensive test reports
- **Artifact Collection**: Gathers videos, traces, and screenshots

### Using MCP Orchestrator

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

## Test Artifacts

Tests generate several types of artifacts:

- **Videos**: Test execution recordings (`test-results/videos/`)
- **Traces**: Detailed execution traces (`test-results/traces/`)
- **Screenshots**: Page screenshots (`test-results/screenshots/`)
- **Reports**: HTML and JSON test reports (`playwright-report/`)

## Configuration

### Playwright Settings

Configure Playwright behavior in `pytest.ini`:

```ini
[tool:pytest]
browser = chromium
headed = false
slow_mo = 100
timeout = 30000
video = retain-on-failure
trace = on-first-retry
```

### Environment Variables

Set these environment variables for testing:

```bash
export CTI_SCRAPER_URL=http://localhost:8000
export CTI_SCRAPER_TIMEOUT=30000
export PLAYWRIGHT_HEADLESS=true
```

## Test Categories

### Core Functionality Tests
- `test_homepage_loads`: Verify homepage loads correctly
- `test_navigation_menu`: Test navigation between pages
- `test_sources_page`: Verify sources management interface
- `test_articles_page`: Test articles display and functionality

### API Tests
- `test_api_endpoints`: Verify REST API responses
- `test_health_endpoint`: Check application health status

### User Experience Tests
- `test_search_functionality`: Test search features
- `test_responsive_design`: Verify mobile responsiveness
- `test_performance`: Check page load times
- `test_accessibility`: Basic accessibility compliance

### Advanced Tests
- `test_threat_hunting_scoring`: Verify scoring system
- `test_source_management`: Test source CRUD operations
- `test_data_export`: Verify export functionality

## Debugging Failed Tests

### Common Issues

1. **Application Not Running**:
   ```bash
   # Check if CTIScraper is running
   curl http://localhost:8000/health
   ```

2. **Database Issues**:
   ```bash
   # Check database connectivity
   docker exec cti_postgres psql -U cti_user -d cti_scraper -c "SELECT 1;"
   ```

3. **Browser Issues**:
   ```bash
   # Run with visible browser
   pytest tests/e2e/ -v --headed=true
   ```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Run with debug output
pytest tests/e2e/ -v -s --log-cli-level=DEBUG

# Run single test with debug
pytest tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_homepage_loads -v -s
```

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Wait Strategies**: Use proper wait conditions for dynamic content
3. **Error Handling**: Implement robust error handling
4. **Data Cleanup**: Clean up test data after tests
5. **Performance**: Keep tests fast and efficient

## Contributing

When adding new E2E tests:

1. Follow the existing test structure
2. Use descriptive test names
3. Add proper docstrings
4. Include error handling
5. Update this README if needed

## Troubleshooting

### Playwright Installation Issues

```bash
# Reinstall Playwright browsers
playwright install --force

# Check browser installation
playwright --version
```

### Test Environment Issues

```bash
# Reset test environment
docker-compose down
docker-compose up -d
sleep 10
```

### CI/CD Issues

Check the GitHub Actions logs for:
- Service health checks
- Browser installation
- Test execution logs
- Artifact uploads
