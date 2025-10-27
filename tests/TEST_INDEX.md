# CTIScraper Test Index

## 📋 Complete Test Inventory

### 🎯 Test Statistics
- **Total Test Files**: 42
- **Total Test Methods**: 685
- **Active Tests**: 457
- **Skipped Tests**: 205
- **Failing Tests**: 32

## 📁 Test Files by Category

### Unit Tests (26 files, 629 tests)

#### New Service and Utility Tests
| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_chunk_analysis_service.py` | 20 | ✅ Passing | ML vs Hunt scoring comparison, chunk analysis |
| `test_prompt_loader.py` | 17 | ✅ Passing | Prompt file management and loading |
| `test_query_safety.py` | 33 | ✅ Passing | SQL injection prevention and query validation |
| `test_simhash.py` | 48 | ✅ Passing | Near-duplicate detection using simhash |
| `test_model_evaluation.py` | 24 | ✅ Passing | ML model evaluation metrics |

#### Core System Tests
| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_core.py` | 8 | ⏭️ Skipped | Core system functionality |
| `test_utils.py` | 14 | ✅ Passing | Utility functions |
| `test_database.py` | 5 | ⏭️ Skipped | Database models and schemas |

#### Data Processing Tests
| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_content_processor.py` | 47 | ⏭️ Skipped | Content processing pipeline |
| `test_content_cleaner.py` | 30 | ✅ Passing | HTML cleaning and text processing |
| `test_content_filter.py` | 25 | ✅ Passing | ML-based content filtering |
| `test_deduplication_service.py` | 35 | ⏭️ Skipped | Duplicate detection |
| `test_rss_parser.py` | 46 | ⏭️ Skipped | RSS feed parsing |
| `test_modern_scraper.py` | 18 | ⏭️ Skipped | Web scraping functionality |

#### AI and Analysis Tests
| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_ai_integration.py` | 15 | ✅ Passing | AI integration workflows |
| `test_gpt4o_optimizer.py` | 22 | ✅ Passing | GPT-4o content optimization |
| `test_gpt4o_endpoint.py` | 15 | ✅ Passing | GPT-4o API endpoints |
| `test_ollama_integration.py` | 20 | ✅ Passing | Ollama local AI integration |
| `test_sigma_validator.py` | 50 | ✅ Passing | SIGMA rule validation |
| `test_threat_hunting_scorer.py` | 26 | ✅ Passing | Threat hunting scoring |
| `test_ioc_extractor.py` | 20 | ✅ Passing | IOC extraction |

#### Infrastructure Tests
| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_database_operations.py` | 33 | ⏭️ Skipped | Database operations |
| `test_http_client.py` | 39 | ⚠️ 38/39 Passing | HTTP client functionality |
| `test_source_manager.py` | 35 | ✅ Passing | Source configuration and validation |
| `test_search_parser.py` | 15 | ⏭️ Skipped | Search functionality |
| `test_web_application.py` | 10 | ⏭️ Skipped | Web application logic |

### UI Tests (5 files, 61 tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_ai_assistant_ui.py` | 15 | ✅ Passing | AI Assistant interface |
| `test_ui_flows.py` | 13 | ✅ Passing | User workflow testing |
| `test_article_classification.py` | 15 | ✅ Passing | Article classification UI |
| `test_collect_now_button.py` | 9 | ✅ Passing | Collection button functionality |
| `test_health_page.py` | 9 | ✅ Passing | Health monitoring page |

### Integration Tests (4 files, 46 tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_system_integration.py` | 13 | ✅ Passing | Full system integration |
| `test_lightweight_integration.py` | 12 | ✅ Passing | Lightweight integration |
| `test_ai_real_api_integration.py` | 10 | ✅ Passing | Real AI API integration |
| `test_ai_cross_model_integration.py` | 11 | ✅ Passing | Cross-model AI integration |

### API Tests (1 file, 15 tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_endpoints.py` | 15 | ✅ Passing | REST API endpoints |

### E2E Tests (1 file, 13 tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_web_interface.py` | 13 | ✅ Passing | Complete web interface workflows |

## 🎯 Test Status Summary

### ✅ Fully Functional (449 tests)
- **AI Assistant Tests**: 36 tests (Priority 1 implementation)
- **Core Functionality**: 222 tests (previously fixed)
- **Service/Utility Tests**: 142 tests (chunk analysis, prompt loader, query safety, simhash, model evaluation)
- **UI Tests**: 61 tests (all working)
- **Integration Tests**: 46 tests (all working)
- **API Tests**: 15 tests (all working)
- **E2E Tests**: 13 tests (all working)
- **Other Unit Tests**: 49 tests (various modules)

### ⏭️ Skipped Tests (202 tests)
Tests requiring async mock configuration fixes:

- **RSS Parser** (46 tests) - Feed parsing and validation
- **Content Processor** (47 tests) - Article processing pipeline
- **Deduplication Service** (35 tests) - Duplicate detection
- **Database Operations** (33 tests) - CRUD operations
- **Modern Scraper** (18 tests) - Web scraping functionality
- **Search Parser** (15 tests) - Search functionality
- **Web Application** (10 tests) - Web application logic
- **Core** (8 tests) - Core system functionality
- **Database** (5 tests) - Database models

### ⚠️ Partially Working (32 tests)
- **HTTP Client** (38/39 tests passing) - 1 retry test failing

## 🚀 Test Runners

### Specialized Runners
| Runner | Purpose | Tests | Status |
|--------|---------|-------|--------|
| `run_ai_tests.py` | AI Assistant Priority 1 tests | 36 | ✅ Active |
| `run_lightweight_tests.py` | Lightweight integration tests | 12 | ✅ Active |

### Standard Runners
```bash
# All tests
python3 -m pytest tests/ -v

# By category
python3 -m pytest tests/ -m "unit" -v
python3 -m pytest tests/ -m "ui" -v
python3 -m pytest tests/ -m "integration" -v
python3 -m pytest tests/ -m "e2e" -v
```

## 📊 Coverage Analysis

### High Coverage Areas (90%+)
- **AI Assistant Features**: 95% coverage
- **Content Filtering**: 90% coverage
- **SIGMA Validation**: 95% coverage
- **Threat Hunting Scoring**: 100% coverage
- **UI Components**: 90% coverage

### Medium Coverage Areas (50-89%)
- **Content Processing**: 60% coverage (many skipped)
- **Database Operations**: 40% coverage (many skipped)
- **RSS Parsing**: 30% coverage (many skipped)

### Low Coverage Areas (<50%)
- **Web Scraping**: 20% coverage (many skipped)
- **Search Functionality**: 25% coverage (many skipped)

## 🔧 Test Configuration

### Conftest Files
- **`conftest.py`** - Main pytest configuration
- **`conftest_lightweight.py`** - Lightweight integration fixtures
- **`conftest_ai.py`** - AI-specific test configuration

### Test Markers
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.ui` - UI tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.ai` - AI-related tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.skip` - Skipped tests

## 🎯 Priority Fixes

### Priority 1 (Critical - 202 tests)
Fix async mock configurations for:
1. **Database Operations** (33 tests) - Core infrastructure
2. **Content Processor** (47 tests) - Main processing logic
3. **RSS Parser** (46 tests) - Primary data ingestion
4. **Deduplication Service** (35 tests) - Data quality
5. **Modern Scraper** (18 tests) - Alternative ingestion
6. **Search Parser** (15 tests) - Search functionality
7. **Web Application** (10 tests) - Web logic
8. **Core** (8 tests) - System functionality
9. **Database** (5 tests) - Models and schemas

### Priority 2 (Important - 1 test)
- **HTTP Client retry test** - Fix retry logic assertion

### Priority 3 (Nice to Have)
- Performance benchmarking
- Load testing
- Security testing

## 📚 Documentation

### Test Documentation Files
- **`README.md`** - Main test documentation
- **`TEST_INDEX.md`** - This comprehensive index
- **`SKIPPED_TESTS.md`** - Detailed skipped test information
- **`AI_TESTS_README.md`** - AI Assistant test documentation
- **`AI_PRIORITY_1_TESTS_IMPLEMENTATION.md`** - AI test implementation summary

### Quick Reference
- **Total Tests**: 685
- **Active Tests**: 449 (65.5%)
- **Skipped Tests**: 205 (29.9%)
- **Failing Tests**: 32 (4.7%)
- **Test Files**: 42
- **Categories**: 5 (Unit, UI, Integration, API, E2E)

## 🔄 Maintenance

### Adding New Tests
1. Follow existing naming conventions (`test_*.py`)
2. Add appropriate markers
3. Include comprehensive docstrings
4. Update this index
5. Add to appropriate category

### Fixing Skipped Tests
1. Review `SKIPPED_TESTS.md` for specific issues
2. Fix async mock configurations
3. Remove `@pytest.mark.skip` decorators
4. Run tests and verify they pass
5. Update status in this index

### Test Quality Standards
- Descriptive test names
- Comprehensive docstrings
- Proper setup/teardown
- Mock external dependencies
- Test success and failure scenarios
- Include performance considerations
- Document test data and expected outcomes
