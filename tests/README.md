# CTIScraper Test Suite Documentation

## 📊 Test Suite Overview

**Total Test Coverage**: 710+ test methods across 38+ test files

### Test Categories

| Category | Files | Tests | Status | Description |
|----------|-------|-------|--------|-------------|
| **Unit Tests** | 24 | 580+ | ✅ Active | Core functionality testing |
| **UI Tests** | 6 | 80+ | ✅ Active | User interface testing (Playwright sync API) |
| **Integration Tests** | 6 | 50+ | ✅ Active | Cross-component testing including ML feedback |
| **API Tests** | 3 | 40+ | ✅ Active | API endpoint testing including ML feedback APIs |
| **E2E Tests** | 1 | 13 | ✅ Active | End-to-end workflow testing |
| **ML Feedback Tests** | 3 | 11 | ✅ Active | Essential regression prevention for ML features |

## 🚀 Quick Start

### Run All Tests
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run with coverage
python3 -m pytest tests/ --cov=src --cov-report=html
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

### Run Specific Test Categories
```bash
# Unit tests only
python3 -m pytest tests/ -m "not integration and not ui and not e2e" -v

# UI tests only
python3 -m pytest tests/ui/ -v

# Integration tests only
python3 -m pytest tests/integration/ -v

# API tests only
python3 -m pytest tests/api/ -v

# E2E tests only
python3 -m pytest tests/e2e/ -v

# RAG feature tests
python3 tests/run_lightweight_tests.py rag

# Embedding service tests
python3 tests/run_lightweight_tests.py embedding
```

### Specialized Test Runners
```bash
# AI Assistant tests (Priority 1)
python3 tests/run_ai_tests.py

# Lightweight integration tests
python3 tests/run_lightweight_tests.py light

# Full integration tests (requires Docker)
python3 tests/run_lightweight_tests.py full
```

## 📁 Test Structure

### Unit Tests (539 tests)
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

### UI Tests (61 tests)
User interface testing with Playwright sync API:

- **`test_ai_assistant_ui.py`** (15 tests) - AI Assistant interface
- **`test_ui_flows.py`** (13 tests) - User workflow testing
- **`test_collect_now_button.py`** (9 tests) - Collection button functionality
- **`test_article_classification.py`** (15 tests) - Article classification UI
- **`test_health_page.py`** (9 tests) - Health monitoring page

### Integration Tests (46 tests)
Cross-component testing with real dependencies:

- **`test_system_integration.py`** (13 tests) - Full system integration
- **`test_lightweight_integration.py`** (12 tests) - Lightweight integration
- **`test_ai_real_api_integration.py`** (10 tests) - Real AI API integration
- **`test_ai_cross_model_integration.py`** (11 tests) - Cross-model AI integration

### API Tests (35+ tests)
API endpoint testing:

- **`test_endpoints.py`** (15 tests) - REST API endpoints
- **`test_rag_endpoints.py`** (20+ tests) - RAG chat and semantic search endpoints

### E2E Tests (13 tests)
End-to-end workflow testing with Playwright sync API:

- **`test_web_interface.py`** (13 tests) - Complete web interface workflows

## 🎯 Test Status by Module

### ✅ Fully Functional (280+ tests)
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

### ⏭️ Skipped Tests (202 tests)
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

### ⚠️ Partially Working (32 tests)
- **HTTP Client** (1/39 tests failing) - Retry logic test needs fixing

## 🔧 Test Configuration

### Conftest Files
- **`conftest.py`** - Main pytest configuration
- **`conftest_lightweight.py`** - Lightweight integration test fixtures
- **`conftest_ai.py`** - AI-specific test configuration

### Test Runners
- **`run_ai_tests.py`** - AI Assistant Priority 1 tests
- **`run_lightweight_tests.py`** - Lightweight integration tests

### Markers
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.ui` - UI tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.ai` - AI-related tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.skip` - Skipped tests

## 🐳 Docker Testing

### Prerequisites
```bash
# Start Docker containers
docker-compose up -d

# Verify containers are running
docker-compose ps
```

### Environment Variables
```bash
# For UI tests
export CTI_SCRAPER_URL="http://localhost:8001"

# For real API tests (optional)
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-ant-your-key"
```

## 📈 Coverage Reports

### Generate Coverage
```bash
# HTML coverage report
python3 -m pytest tests/ --cov=src --cov-report=html:htmlcov

# Terminal coverage report
python3 -m pytest tests/ --cov=src --cov-report=term-missing

# XML coverage report (for CI/CD)
python3 -m pytest tests/ --cov=src --cov-report=xml
```

### View Coverage
```bash
# Open HTML report
open htmlcov/index.html
```

## 🚨 Known Issues

### Skipped Tests
Many tests are skipped due to async mock configuration issues. See `SKIPPED_TESTS.md` for detailed information.

### Common Problems
1. **Import Errors**: Some tests may fail due to missing dependencies
2. **Async Mock Issues**: Tests with async operations need proper mock configuration
3. **Docker Dependencies**: Some tests require Docker containers to be running

## 🔄 Test Maintenance

### Adding New Tests
1. Follow existing test structure and naming conventions
2. Add appropriate markers (`@pytest.mark.unit`, etc.)
3. Include comprehensive docstrings
4. Update this README with new test information

### Fixing Skipped Tests
1. Review `SKIPPED_TESTS.md` for specific issues
2. Fix async mock configurations
3. Remove `@pytest.mark.skip` decorators
4. Run tests and verify they pass

### Test Best Practices
- Use descriptive test names
- Include setup and teardown logic
- Mock external dependencies
- Test both success and failure scenarios
- Include performance considerations
- Document test data and expected outcomes

## 📚 Additional Documentation

- **`AI_TESTS_README.md`** - AI Assistant test documentation
- **`SKIPPED_TESTS.md`** - Detailed skipped test information
- **`AI_PRIORITY_1_TESTS_IMPLEMENTATION.md`** - AI test implementation summary

## 🎯 Test Priorities

### Priority 1 (Critical)
- ✅ AI Assistant tests (implemented)
- ✅ Core functionality tests (working)
- ✅ UI tests (working)
- ✅ RAG Chat feature tests (implemented)
- ✅ Embedding service tests (implemented)

### Priority 2 (Important)
- 🔄 Fix skipped async tests
- 🔄 Database operation tests
- 🔄 Content processing tests

### Priority 3 (Nice to Have)
- 🔄 Performance benchmarking
- 🔄 Load testing
- 🔄 Security testing

## 📞 Support

For test-related issues:
1. Check this README for common solutions
2. Review `SKIPPED_TESTS.md` for known issues
3. Check test logs for specific error messages
4. Ensure Docker containers are running for integration tests
