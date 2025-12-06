# CTIScraper Testing Guide

Comprehensive testing documentation for the CTI Scraper application, covering all test types, execution contexts, and best practices.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Test Infrastructure](#test-infrastructure)
3. [Test Categories](#test-categories)
4. [Execution Contexts](#execution-contexts)
5. [Test Structure](#test-structure)
6. [Writing Tests](#writing-tests)
7. [Docker Testing](#docker-testing)
8. [Coverage Reports](#coverage-reports)
9. [Continuous Integration](#continuous-integration)
10. [Performance Testing](#performance-testing)
11. [Debugging Tests](#debugging-tests)
12. [Test Data Management](#test-data-management)
13. [Best Practices](#best-practices)
14. [Troubleshooting](#troubleshooting)
15. [Test Maintenance](#test-maintenance)
16. [Resources](#resources)

## Quick Start

### Health Check (Recommended First Step)

```bash
# Quick smoke test
python run_tests.py --smoke
```

### Install Test Dependencies

```bash
# Install test dependencies
python run_tests.py --install
```

### Run Full Test Suite

```bash
# Complete test suite with coverage
python run_tests.py --all --coverage
```

### Run ML Feedback Tests (Essential Regression Prevention)

```bash
# Run the 3 critical ML feedback tests
./scripts/run_ml_feedback_tests.sh

# Run individual ML feedback test categories
docker exec cti_web python -m pytest tests/integration/test_huntable_probability.py -v
docker exec cti_web python -m pytest tests/api/test_ml_feedback.py -v
docker exec cti_web python -m pytest tests/integration/test_retraining_integration.py -v
```

## Test Infrastructure

### Test Scripts

- **`run_tests.py`**: Unified Python test runner with multiple execution modes
- **`scripts/run_tests_by_group.py`**: Grouped test execution script (executes tests by group and reports broken tests)
- **`pytest.ini`**: Pytest configuration file

### Test Stack Overview

| Layer     | Tool                              | Purpose                               |
| --------- | --------------------------------- | ------------------------------------- |
| UI        | **Playwright (Docker)**           | End-to-end workflow verification      |
| API       | **FastAPI TestClient**            | REST endpoint validation              |
| Database  | **PostgreSQL**                    | Schema and integrity tests            |
| ML        | **Pytest**                        | Regression testing for feedback loops |
| CI        | **GitHub Actions**                | Automated pipeline execution          |
| Local Dev | **Cursor IDE / Browser DevTools** | Debugging and manual testing          |

## Test Categories

### Test Suite Overview

**Total Test Coverage**: 710+ test methods across 38+ test files

| Category | Files | Tests | Duration | Purpose | Dependencies |
|----------|-------|-------|----------|---------|--------------|
| **Smoke** | 1 | 5+ | ~30s | Quick health check | Minimal |
| **Unit** | 24 | 580+ | ~1m | Component testing | None |
| **API** | 3 | 30+ | ~2m | Endpoint testing | Application running |
| **Integration** | 6 | 50+ | ~3m | System testing | Full Docker stack |
| **Integration Workflow** | 8 | 60+ | ~5m | End-to-end workflows | Full Docker stack |
| **UI** | 6 | 80+ | ~5m | Web interface testing | Playwright, browser |
| **E2E** | 1 | 13 | ~5m | End-to-end workflows | Full environment |
| **ML Feedback** | 3 | 11 | ~1m | Regression prevention | Database |
| **All** | 46+ | 770+ | ~10m | Complete test suite | Full environment |

### Test Execution Summary

| Type            | Command                                      | Description                            |
| --------------- | -------------------------------------------- | -------------------------------------- |
| **Smoke**       | `python run_tests.py --smoke`                | Quick health check (~30s)              |
| **E2E**         | `docker-compose run web pytest tests/e2e -v` | Browser automation via Playwright      |
| **API**         | `pytest tests/api -v`                        | FastAPI endpoint validation            |
| **Database**    | `pytest tests/database -v`                   | Schema and data validation             |
| **ML Feedback** | `./scripts/run_ml_feedback_tests.sh`         | Regression and feedback loop stability |
| **Integration Workflow** | `pytest tests/integration -m integration_workflow -v` | End-to-end workflow tests |
| **Security**    | `pytest tests/security -v`                   | Bandit, safety, and dependency checks  |
| **Grouped Execution** | `python scripts/run_tests_by_group.py` | Execute tests by group with failure reporting |
| **Performance** | `pytest tests/performance -v`                | Load and profiling tests               |
| **Allure Reports** | `python run_tests.py --all`                | Generate comprehensive test reports     |
| **CI/CD**       | *GitHub Actions*                             | Auto-tests on push/pull requests       |

## Execution Contexts

### Localhost Testing (Default)
**Best for**: Development, debugging, rapid iteration

```bash
# Activate test environment
source venv-test/bin/activate

# Run tests locally
python run_tests.py --smoke
python run_tests.py --unit
python run_tests.py --api
python run_tests.py --integration
python run_tests.py --ui
python run_tests.py --all --coverage

```

### Docker Testing
**Best for**: Integration testing, production-like environment

```bash
# Ensure Docker containers are running
docker-compose up -d

# Run tests in Docker containers
python run_tests.py --docker --smoke
python run_tests.py --docker --integration
python run_tests.py --docker --all --coverage

```

### CI/CD Testing
**Best for**: Automated quality gates, regression testing

```bash
# CI/CD mode (automatically detected in GitHub Actions)
python run_tests.py --ci --all --coverage
```

## Test Structure

### Directory Layout

```
tests/
├── test_*.py              # Individual test modules
├── conftest.py           # Pytest configuration and fixtures
├── fixtures/             # Test data and fixtures
├── mocks/                # Mock objects and stubs
├── integration/          # Integration test suites
├── ui/                   # UI test suites
├── api/                  # API test suites
├── workflows/            # Workflow test suites
└── e2e/                  # End-to-end test suites
```

### Test Modules by Category

#### Unit Tests (580+ tests)
Core functionality testing with mocked dependencies:

- **`test_source_manager.py`** (35 tests) - Source configuration and validation
- **`test_gpt4o_optimizer.py`** (22 tests) - GPT-4o content optimization
- **`test_utils.py`** (14 tests) - Utility functions
- **`test_content_filter.py`** (25 tests) - ML-based content filtering
- **`test_sigma_validator.py`** (50 tests) - SIGMA rule validation
- **`test_content_cleaner.py`** (30 tests) - HTML cleaning and text processing
- **`test_http_client.py`** (39 tests) - HTTP client functionality
- **`test_threat_hunting_scorer.py`** (26 tests) - Threat hunting scoring
- **`test_ioc_extractor.py`** (20 tests) - IOC extraction
- **`test_ai_integration.py`** (15 tests) - AI integration workflows
- **`test_ollama_integration.py`** (20 tests) - Ollama local AI integration
- **`test_gpt4o_endpoint.py`** (15 tests) - GPT-4o API endpoints
- **`test_database_operations.py`** (33 tests) - Database operations
- **`test_content_processor.py`** (47 tests) - Content processing pipeline
- **`test_rss_parser.py`** (46 tests) - RSS feed parsing
- **`test_deduplication_service.py`** (35 tests) - Duplicate detection
- **`test_modern_scraper.py`** (18 tests) - Web scraping functionality
- **`test_search_parser.py`** (15 tests) - Search functionality
- **`test_web_application.py`** (10 tests) - Web application logic
- **`test_core.py`** (8 tests) - Core system functionality
- **`test_database.py`** (5 tests) - Database models and schemas

#### UI Tests (380+ tests)
User interface testing with Playwright sync API:

- **`test_ai_assistant_ui.py`** (17 tests) - AI Assistant interface
- **`test_analytics_pages_ui.py`** (11 tests) - Analytics dashboard pages
- **`test_analytics_ui.py`** (20 tests) - Analytics main page
- **`test_article_classification.py`** (9 tests) - Article classification UI
- **`test_article_interactions_ui.py`** (10 tests) - Article interactions
- **`test_collect_now_button.py`** (9 tests) - Collection button functionality
- **`test_dashboard_functionality.py`** (11 tests) - Dashboard functionality
- **`test_diags_ui.py`** (51 tests) - Diagnostics page
- **`test_health_page.py`** (15 tests) - Health monitoring page
- **`test_help_ui.py`** (42 tests) - Help page and modals
- **`test_ioc_*.py`** (9 tests) - IOC extraction UI tests (5 files)
- **`test_jobs_monitor_ui.py`** (8 tests) - Jobs monitor
- **`test_mobile_annotation.py`** (13 tests) - Mobile annotation
- **`test_modal_interactions_ui.py`** (20 tests) - Modal interactions
- **`test_navigation_ui.py`** (11 tests) - Navigation and breadcrumbs
- **`test_ollama_test_button_ui.py`** (13 tests) - Ollama test button
- **`test_pdf_upload_ui.py`** (6 tests) - PDF upload
- **`test_prompt_sync_ui.py`** (24 tests) - Prompt synchronization
- **`test_rag_chat_ui.py`** (16 tests) - RAG chat interface
- **`test_settings_ui.py`** (63 tests) - Settings page
- **`test_sources_ui.py`** (8 tests) - Sources management
- **`test_ui_flows.py`** (16 tests) - User workflow testing
- **`test_workflow_tabs_ui.py`** (3 tests) - Workflow agent config subpages visibility

#### Integration Tests (200+ tests)
Cross-component testing with real dependencies:

- **`test_agentic_workflow_comprehensive.py`** - Full agentic workflow simulation
- **`test_ai_api.py`** - AI API integration
- **`test_ai_assistant.py`** - AI Assistant integration
- **`test_ai_cross_model_integration.py`** (11 tests) - Cross-model AI integration
- **`test_ai_real_api_integration.py`** (10 tests) - Real AI API integration
- **`test_analytics_integration.py`** - Analytics integration
- **`test_annotation_feedback_integration.py`** - Annotation feedback loop
- **`test_backup_restore.py`** - Backup and restore
- **`test_celery_workflow_integration.py`** - Celery workflows
- **`test_content_pipeline_integration.py`** - Content pipeline
- **`test_error_recovery_integration.py`** - Error recovery
- **`test_export_backup_integration.py`** - Export/backup workflows
- **`test_gpt4o_filtering.py`** - GPT-4o filtering
- **`test_huntable_probability.py`** - Huntable probability
- **`test_lightweight_integration.py`** (12 tests) - Lightweight integration
- **`test_mobile_annotation_direct.py`** - Mobile annotation
- **`test_ollama_test_button_integration.py`** - Ollama integration
- **`test_rag_conversation_integration.py`** - RAG conversations
- **`test_retraining_integration.py`** - Retraining workflows
- **`test_scoring_system_integration.py`** - Scoring system
- **`test_sigma_generation_e2e.py`** - SIGMA generation
- **`test_source_health.py`** - Source health monitoring
- **`test_source_management_integration.py`** - Source management
- **`test_summarization.py`** - Summarization
- **`test_system_integration.py`** (13 tests) - Full system integration

#### Integration Workflow Tests (NEW)
End-to-end workflow testing with real services:

- **`test_agentic_workflow_comprehensive.py`** - Full agentic workflow simulation (Chat -> Queue) with mocked services
- **`test_langgraph_server.py`** - LangGraph server integration, chat logic, and node transitions
- **`test_celery_workflow_integration.py`** - Celery task workflows (collection, embedding, retry, concurrency)
- **`test_scoring_system_integration.py`** - Scoring workflows (initial scoring, rescore, keyword updates, ML integration)
- **`test_annotation_feedback_integration.py`** - Annotation and feedback loop (creation, retraining, version tracking)
- **`test_content_pipeline_integration.py`** - Content processing pipeline (RSS to storage, validation, deduplication)
- **`test_source_management_integration.py`** - Source lifecycle (add, configure, collect, monitor, recover)
- **`test_rag_conversation_integration.py`** - RAG chat workflows (single/multi-turn, context, provider fallback)
- **`test_error_recovery_integration.py`** - Resilience tests (database loss, API failures, task retry, concurrent load)
- **`test_export_backup_integration.py`** - Export and backup workflows (creation, restoration, filtering, performance)

#### API Tests (30+ tests)
API endpoint testing:

- **`test_endpoints.py`** (15 tests) - REST API endpoints
- **`test_rag_endpoints.py`** (20+ tests) - RAG chat and semantic search endpoints

#### E2E Tests (13 tests)
End-to-end workflow testing with Playwright sync API:

- **`test_web_interface.py`** (13 tests) - Complete web interface workflows

### Test Status by Module

#### ✅ Fully Functional (280+ tests)
- **Threat Hunting Scorer** (26 tests) - All passing
- **Content Filter** (25 tests) - All passing
- **SIGMA Validator** (50 tests) - All passing
- **Source Manager** (35 tests) - All passing
- **Content Cleaner** (30 tests) - All passing
- **HTTP Client** (38/39 tests) - 1 retry test failing
- **AI Integration** (15 tests) - All passing
- **GPT-4o Optimizer** (22 tests) - All passing
- **GPT-4o Endpoint** (15 tests) - All passing
- **Ollama Integration** (20 tests) - All passing
- **IOC Extractor** (20 tests) - All passing
- **UI Tests** (80+ tests) - All passing (Playwright sync API)
- **API Tests** (35+ tests) - All passing
- **E2E Tests** (13 tests) - All passing (Playwright sync API)
- **RAG Service** (25+ tests) - All passing
- **Embedding Service** (30+ tests) - All passing
- **Celery Embedding Tasks** (20+ tests) - All passing

#### ⏭️ Skipped Tests (202 tests)
Tests that need async mock configuration fixes:

- **RSS Parser** (46 tests) - Async mock configuration needed
- **Content Processor** (47 tests) - Async mock configuration needed
- **Deduplication Service** (35 tests) - SimHash algorithm tests need refinement
- **Modern Scraper** (18 tests) - Async mock configuration needed
- **Database Operations** (33 tests) - Async mock configuration needed
- **Search Parser** (15 tests) - Async mock configuration needed
- **Web Application** (10 tests) - Async mock configuration needed
- **Core** (8 tests) - Async mock configuration needed
- **Database** (5 tests) - Async mock configuration needed

#### ⚠️ Partially Working (32 tests)
- **HTTP Client** (1/39 tests failing) - Retry logic test needs fixing

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

### Test Configuration

#### Conftest Files
- **`conftest.py`** - Main pytest configuration
- **`conftest_lightweight.py`** - Lightweight integration test fixtures
- **`conftest_ai.py`** - AI-specific test configuration

#### Test Runners
- **`run_ai_tests.py`** - AI Assistant Priority 1 tests
- **`run_lightweight_tests.py`** - Lightweight integration tests

#### Markers
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.ui` - UI tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.ai` - AI-related tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.skip` - Skipped tests

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

### Environment Variables

```bash
# For UI tests
export CTI_SCRAPER_URL="http://localhost:8001"

# For real API tests (optional)
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-ant-your-key"
```

## Coverage Reports

### Generating Coverage

```bash
# Generate HTML coverage report
python run_tests.py --all --coverage
open htmlcov/index.html

# Generate coverage for specific modules
python run_tests.py --unit --coverage

# HTML coverage report
python3 -m pytest tests/ --cov=src --cov-report=html:htmlcov

# Terminal coverage report
python3 -m pytest tests/ --cov=src --cov-report=term-missing

# XML coverage report (for CI/CD)
python3 -m pytest tests/ --cov=src --cov-report=xml
```

### Coverage Targets

- **Unit Tests**: 90%+ coverage
- **Integration Tests**: 80%+ coverage
- **API Tests**: 85%+ coverage
- **Overall**: 85%+ coverage

### Coverage Reports
- **HTML Report**: `htmlcov/index.html`
- **Terminal Report**: Displayed in console
- **XML Report**: `coverage.xml` (for CI/CD)

## Continuous Integration

### GitHub Actions

The project includes GitHub Actions workflows for:

- **CI Pipeline**: Automated testing on pull requests
- **Security Scanning**: Dependency vulnerability checks
- **Code Quality**: Linting and type checking
- **Docker Testing**: Containerized test execution

**Workflow File:** `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Tests
        run: |
          docker-compose up -d
          docker-compose run --rm web pytest -v
```

**Includes:**

- Automated testing on PRs
- Security scanning (Bandit, Safety)
- Coverage and test artifact uploads

### Local CI Simulation

```bash
# Simulate CI pipeline locally
python run_tests.py --ci

# Simulate CI environment
export CI=true
python run_tests.py --ci --all --coverage
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

### Debug Commands

```bash
# Check service status
docker-compose ps

# View test logs
docker-compose logs -f web

# Debug specific test
pytest tests/test_models.py::TestArticleModel::test_article_creation -v -s
```

### Browser DevTools

- **Console:** JavaScript errors
- **Network:** API requests and responses
- **Elements:** DOM structure
- **Sources:** Breakpoints for frontend debugging

## Test Data Safety

### Overview

**All tests are verified to be non-impactful to production database data and application configuration files.**

### Safety Guarantees

1. **Database Isolation**: All integration tests use `cti_scraper_test` database (not production `cti_scraper`)
2. **Transaction Rollback**: All database changes are rolled back after each test
3. **Config Read-Only**: Tests only read config files, never write to them
4. **ML Model Protection**: All ML model retraining tests are disabled
5. **Default Exclusions**: Tests marked `prod_data`/`production_data` are excluded by default

### Protection Mechanisms

**Test Database Usage:**
- Integration tests use `cti_scraper_test` database
- Default connection: `postgresql+asyncpg://cti_user:cti_pass@localhost:5432/cti_scraper_test`
- Transaction rollback fixture prevents data persistence

**Configuration File Protection:**
- Tests only read from `config/sources.yaml` (no writes)
- No tests modify configuration files

**ML Model Protection:**
- All retraining tests are disabled per `TEST_MUTATION_AUDIT.md`
- Tests marked `prod_data`/`production_data` are excluded by default

**UI Tests Safety:**
- UI tests connect to `localhost:8001` (application instance)
- No database writes from UI tests
- No config file modifications from UI tests

### Verification

See `docs/TEST_DATA_SAFETY.md` for complete data safety audit results and verification commands.

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

### Test Execution Order

1. **Smoke tests** - Quick health check
2. **Unit tests** - Component validation
3. **API tests** - Endpoint validation
4. **Integration tests** - System validation
5. **UI tests** - User interface validation
6. **Performance tests** - Load validation

### Environment Management

- Use **localhost** for development speed
- Use **Docker** for integration validation
- Use **CI/CD** for automated quality gates

### Test Data Management

- Use **mocked data** for unit tests
- Use **test databases** for integration tests
- Use **isolated environments** for UI tests

### Error Handling

- **Fail fast** on critical errors
- **Continue testing** on non-critical errors
- **Generate reports** for all test runs

## Troubleshooting

### Common Issues

1. **Database Connection**: Ensure PostgreSQL container is running
2. **Port Conflicts**: Check for port conflicts on 8001, 5432, 6379
3. **Environment Variables**: Verify `.env` file configuration
4. **Dependencies**: Ensure all test dependencies are installed

**Tests fail to start:**
```bash
# Check application status
docker-compose ps

# Check test environment
source venv-test/bin/activate
python --version
pip list
```

**Docker tests fail:**
```bash
# Check Docker containers
docker ps

# Check container logs
docker-compose logs web
docker-compose logs worker
```

**Coverage reports missing:**
```bash
# Check coverage installation
pip install pytest-cov

# Check coverage configuration
cat pytest.ini | grep cov
```

**UI tests fail:**
```bash
# Check Playwright installation
playwright install

# Check browser availability
playwright --version
```

### Environment Issues

**Virtual environment problems:**
```bash
# Recreate test environment
rm -rf venv-test
python3 -m venv venv-test
source venv-test/bin/activate
pip install -r requirements.txt
pip install -r requirements-test.txt
```

**Docker environment problems:**
```bash
# Clean restart
docker-compose down
docker-compose up -d

# Check container health
docker-compose ps
```

### Issue Resolution Table

| Issue                    | Resolution                                        |
| ------------------------ | ------------------------------------------------- |
| **Port conflicts**       | Check ports 8001 / 5432 / 6379                    |
| **Database not ready**   | Confirm PostgreSQL container and `.env` variables |
| **Network/API failures** | Review browser console, Docker logs               |
| **Docker errors**        | Restart Docker daemon and containers              |

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

### Adding New Tests

1. Follow existing test structure and naming conventions
2. Add appropriate markers (`@pytest.mark.unit`, etc.)
3. Include comprehensive docstrings
4. Update this guide with new test information

### Fixing Skipped Tests

1. Review `SKIPPED_TESTS.md` for specific issues
2. Fix async mock configurations
3. Remove `@pytest.mark.skip` decorators
4. Run tests and verify they pass

## Resources

### Documentation

- [Pytest Documentation](https://docs.pytest.org/)
- [Docker Testing Guide](docs/deployment/DOCKER_ARCHITECTURE.md)
- [API Testing Guide](docs/API_ENDPOINTS.md)
- [Allure Reports Guide](docs/development/ALLURE_REPORTS.md)

### Tools

- **Pytest**: Test framework and runner
- **Coverage.py**: Code coverage measurement
- **Docker**: Containerized testing
- **GitHub Actions**: Continuous integration
- **Playwright**: Browser automation
- **Allure**: Test reporting

### Additional Documentation

- **`AI_PRIORITY_1_TESTS_IMPLEMENTATION.md`** - AI test implementation summary
- **`SKIPPED_TESTS.md`** - Detailed skipped test information
- **`AI_PRIORITY_1_TESTS_IMPLEMENTATION.md`** - AI test implementation summary

### Test Priorities

#### Priority 1 (Critical)
- ✅ AI Assistant tests (implemented)
- ✅ Core functionality tests (working)
- ✅ UI tests (working)
- ✅ RAG Chat feature tests (implemented)
- ✅ Embedding service tests (implemented)

#### Priority 2 (Important)
- 🔄 Fix skipped async tests
- 🔄 Database operation tests
- 🔄 Content processing tests

#### Priority 3 (Nice to Have)
- 🔄 Performance benchmarking
- 🔄 Load testing
- 🔄 Security testing

## Visual Test Tracking

CTIScraper includes advanced visual test tracking capabilities:

### Allure Reports

```bash
# Generate Allure results
python run_tests.py --all

# Start dedicated container (recommended)
./manage_allure.sh start

# Serve interactive reports (host)
allure serve allure-results

# Generate static reports
allure generate allure-results --clean -o allure-report
```

### Features

- **Rich Visual Analytics**: Pie charts, bar charts, and trend graphs
- **Interactive Dashboard**: Web-based visualization of test execution
- **Step-by-Step Debugging**: Detailed test execution visualization
- **ML/AI Monitoring**: Special focus on AI inference performance
- **Historical Tracking**: Monitor performance trends over time

### Test Results

- **HTML Reports**: `test-results/report.html`
- **Coverage Reports**: `htmlcov/index.html`
- **CI/CD Reports**: GitHub Actions artifacts

### Metrics

- **Test Duration**: Track execution time
- **Coverage Percentage**: Monitor code coverage
- **Failure Rate**: Track test reliability

## Support

For test-related issues:

1. Check this guide for common solutions
2. Review `SKIPPED_TESTS.md` for known issues
3. Check test logs for specific error messages
4. Ensure Docker containers are running for integration tests
5. **Issues**: GitHub Issues
6. **Discussions**: GitHub Discussions
7. **Code Examples**: See `tests/` directory
8. **CI/CD**: Check `.github/workflows/`

---

**Note**: This testing guide is maintained alongside the codebase. For the most up-to-date information, refer to the test files and configuration in the repository.

*Last updated: January 2025*
