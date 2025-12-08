# CTIScraper Test Index

## 📋 Complete Test Inventory

### 🎯 Test Statistics
- **Total Test Files**: 100+
- **Total Test Methods**: 1200+
- **Active Tests**: 900+
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

### Playwright Tests (TypeScript/JavaScript) (3 files)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `playwright/sigma.spec.ts` | 2 | ✅ Passing | SIGMA generation with LMStudio |
| `playwright/workflow_tabs.spec.ts` | 10 | ✅ Passing | Workflow agent config subpages visibility (Configuration, Executions, SIGMA Queue) |
| `test_help_buttons.spec.js` | 1 | ✅ Passing | Help button visibility in AI/ML modals |

### UI Tests (28 files, 383+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_ai_assistant_ui.py` | 17 | ✅ Passing | AI Assistant interface |
| `test_analytics_pages_ui.py` | 11 | ✅ Passing | Analytics dashboard pages (Hunt Metrics, Scraper Metrics, ML Comparison) |
| `test_analytics_ui.py` | 20 | ✅ Passing | Analytics main page and navigation |
| `test_article_classification.py` | 9 | ✅ Passing | Article classification UI |
| `test_article_interactions_ui.py` | 10 | ✅ Passing | Article list interactions and detail page |
| `test_collect_now_button.py` | 9 | ✅ Passing | Collection button functionality |
| `test_dashboard_functionality.py` | 11 | ✅ Passing | Dashboard functionality and flows |
| `test_diags_ui.py` | 51 | ✅ Passing | Diagnostics page UI tests |
| `test_health_page.py` | 15 | ✅ Passing | Health monitoring page |
| `test_help_ui.py` | 42 | ✅ Passing | Help page and modal interactions |
| `test_ioc_article_2175.py` | 1 | ✅ Passing | IOC extraction on specific article |
| `test_ioc_extraction_behavior.py` | 3 | ✅ Passing | IOC extraction behavior tests |
| `test_ioc_model_display.py` | 2 | ✅ Passing | IOC model display and field mapping |
| `test_ioc_no_gpt_display.py` | 1 | ✅ Passing | IOC display without GPT validation |
| `test_ioc_regenerate.py` | 1 | ✅ Passing | IOC regeneration functionality |
| `test_ioc_simple.py` | 1 | ✅ Passing | Simple IOC extraction tests |
| `test_jobs_monitor_ui.py` | 8 | ✅ Passing | Jobs monitor page interactions |
| `test_mobile_annotation.py` | 13 | ✅ Passing | Mobile annotation system |
| `test_modal_interactions_ui.py` | 20 | ✅ Passing | Modal interactions (Escape key, click outside, Cmd/Ctrl+Enter) |
| `test_navigation_ui.py` | 11 | ✅ Passing | Navigation and breadcrumb functionality |
| `test_ollama_test_button_ui.py` | 13 | ✅ Passing | Ollama test button UI |
| `test_pdf_upload_ui.py` | 6 | ✅ Passing | PDF upload functionality |
| `test_prompt_sync_ui.py` | 24 | ✅ Passing | Prompt sync (help modals vs prompt files) |
| `test_rag_chat_ui.py` | 16 | ✅ Passing | RAG chat interface |
| `test_settings_ui.py` | 63 | ✅ Passing | Settings page functionality |
| `test_sources_ui.py` | 8 | ✅ Passing | Sources page and management |
| `test_ui_flows.py` | 16 | ✅ Passing | User workflow testing |
| `test_workflow_tabs_ui.py` | 3 | ✅ Passing | Workflow agent config subpages visibility (runs TypeScript Playwright test) |

### Integration Tests (25 files, 200+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_agentic_workflow_comprehensive.py` | 10+ | ✅ Passing | Full agentic workflow simulation (Chat -> Queue) |
| `test_ai_api.py` | 10+ | ✅ Passing | AI API integration |
| `test_ai_assistant.py` | 10+ | ✅ Passing | AI Assistant integration |
| `test_ai_cross_model_integration.py` | 11 | ✅ Passing | Cross-model AI integration |
| `test_ai_real_api_integration.py` | 10 | ✅ Passing | Real AI API integration |
| `test_analytics_integration.py` | 10+ | ✅ Passing | Analytics integration |
| `test_annotation_feedback_integration.py` | 10+ | ✅ Passing | Annotation and feedback loop |
| `test_backup_restore.py` | 10+ | ✅ Passing | Backup and restore workflows |
| `test_celery_workflow_integration.py` | 10+ | ✅ Passing | Celery task workflows |
| `test_content_pipeline_integration.py` | 10+ | ✅ Passing | Content processing pipeline |
| `test_error_recovery_integration.py` | 10+ | ✅ Passing | Error recovery and resilience |
| `test_export_backup_integration.py` | 10+ | ✅ Passing | Export and backup workflows |
| `test_gpt4o_filtering.py` | 10+ | ✅ Passing | GPT-4o content filtering |
| `test_huntable_probability.py` | 10+ | ✅ Passing | Huntable probability integration |
| `test_lightweight_integration.py` | 12 | ✅ Passing | Lightweight integration |
| `test_mobile_annotation_direct.py` | 10+ | ✅ Passing | Mobile annotation direct integration |
| `test_ollama_test_button_integration.py` | 10+ | ✅ Passing | Ollama test button integration |
| `test_rag_conversation_integration.py` | 10+ | ✅ Passing | RAG conversation workflows |
| `test_retraining_integration.py` | 10+ | ✅ Passing | Retraining integration |
| `test_scoring_system_integration.py` | 10+ | ✅ Passing | Scoring workflows |
| `test_sigma_generation_e2e.py` | 10+ | ✅ Passing | SIGMA generation E2E |
| `test_source_health.py` | 10+ | ✅ Passing | Source health monitoring |
| `test_source_management_integration.py` | 10+ | ✅ Passing | Source lifecycle management |
| `test_summarization.py` | 10+ | ✅ Passing | Summarization integration |
| `test_system_integration.py` | 13 | ✅ Passing | Full system integration |

### API Tests (12 files, 123+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_analytics.py` | 22 | ✅ Passing | Analytics API endpoints |
| `test_annotations_api.py` | 18 | ✅ Passing | Annotation CRUD endpoint tests |
| `test_chat_api.py` | 10+ | ⚠️ Import Error | Chat API endpoints |
| `test_dashboard.py` | 17 | ✅ Passing | Dashboard API endpoints |
| `test_endpoints.py` | 17 | ✅ Passing | REST API endpoints |
| `test_extract_observables_api.py` | 6 | ✅ Passing | Extract observables API |
| `test_lmstudio_api.py` | 11 | ✅ Passing | LMStudio API integration |
| `test_ml_feedback.py` | 4 | ✅ Passing | ML feedback API |
| `test_ollama_test_endpoints.py` | 13 | ✅ Passing | Ollama test endpoints |
| `test_rag_endpoints.py` | 13 | ✅ Passing | RAG endpoints |
| `test_sorting_api.py` | 1 | ✅ Passing | Sorting API |
| `test_sorting_fallback.py` | 1 | ✅ Passing | Sorting fallback |

### E2E Tests (19 files, 120+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_accessibility.py` | 7 | ✅ Passing | Accessibility testing |
| `test_advanced_search_workflow.py` | 6 | ✅ Passing | Advanced search workflow |
| `test_ai_assistant_workflow.py` | 9 | ✅ Passing | AI Assistant workflow |
| `test_analytics_workflow.py` | 4 | ✅ Passing | Analytics workflow |
| `test_annotation_workflow.py` | 8 | ✅ Passing | Annotation workflow |
| `test_article_classification_workflow.py` | 6 | ✅ Passing | Article classification workflow |
| `test_article_navigation.py` | 3 | ✅ Passing | Article navigation |
| `test_backup_workflow.py` | 6 | ✅ Passing | Backup workflow |
| `test_error_handling.py` | 5 | ✅ Passing | Error handling workflows |
| `test_ml_feedback_workflow.py` | 8 | ✅ Passing | ML feedback workflow |
| `test_ml_hunt_comparison_workflow.py` | 5 | ✅ Passing | ML vs Hunt comparison workflow |
| `test_mobile_annotation_e2e.py` | 5 | ✅ Passing | Mobile annotation E2E |
| `test_multi_browser.py` | 8 | ✅ Passing | Multi-browser support |
| `test_pdf_upload_workflow.py` | 5 | ✅ Passing | PDF upload workflow |
| `test_performance.py` | 7 | ✅ Passing | Performance testing |
| `test_rag_chat_workflow.py` | 8 | ✅ Passing | RAG chat workflow |
| `test_settings_workflow.py` | 3 | ✅ Passing | Settings workflow |
| `test_source_management_workflow.py` | 7 | ✅ Passing | Source management workflow |
| `test_web_interface.py` | 13 | ✅ Passing | Complete web interface workflows |

### CLI Tests (3 files, 20+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_backup_commands.py` | 10+ | ✅ Passing | Backup CLI commands |
| `test_embed_commands.py` | 10+ | ✅ Passing | Embedding CLI commands |
| `test_rescore_command.py` | 10+ | ✅ Passing | Rescore CLI command |

### Utils Tests (4 files, 10+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_environment.py` | 5+ | ✅ Passing | Test environment utilities |
| `test_failure_analyzer.py` | 5+ | ✅ Passing | Test failure analysis |
| `test_isolation.py` | 1 | ✅ Passing | Test isolation utilities |
| `test_output_formatter.py` | 1 | ✅ Passing | Test output formatting |

### Workflows Tests (1 file, 10+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_langgraph_server.py` | 10+ | ✅ Passing | LangGraph server integration |

### Smoke Tests (2 files, 30+ tests)

| File | Tests | Status | Description |
|------|-------|--------|-------------|
| `test_agentic_workflow_smoke.py` | 10+ | ✅ Passing | Agentic workflow smoke tests |
| `test_critical_smoke_tests.py` | 26 | ✅ Passing | Critical endpoint smoke tests |

## 🎯 Test Status Summary

### ✅ Fully Functional (900+ tests)
- **AI Assistant Tests**: 36 tests (Priority 1 implementation)
- **Core Functionality**: 222 tests (previously fixed)
- **Service/Utility Tests**: 142 tests (chunk analysis, prompt loader, query safety, simhash, model evaluation)
- **Playwright Tests**: 13 tests (help buttons, SIGMA generation, workflow tabs)
- **UI Tests**: 383+ tests (analytics, dashboard, diags, help, IOC, jobs, mobile, navigation, ollama, PDF, RAG, settings, sources, workflows, modal interactions - all working)
- **Integration Tests**: 200+ tests (agentic workflow, AI, analytics, annotation, backup, Celery, content pipeline, error recovery, export, GPT-4o, huntable probability, lightweight, mobile, Ollama, RAG, retraining, scoring, SIGMA, source health/management, summarization, system - all working)
- **API Tests**: 123+ tests (analytics, annotations, dashboard, endpoints, extract observables, LMStudio, ML feedback, Ollama, RAG, sorting - all working)
- **E2E Tests**: 120+ tests (accessibility, advanced search, AI assistant, analytics, annotation, article classification/navigation, backup, error handling, ML feedback/hunt comparison, mobile annotation, multi-browser, PDF upload, performance, RAG chat, settings, source management, web interface - all working)
- **CLI Tests**: 20+ tests (backup, embed, rescore commands - all working)
- **Utils Tests**: 10+ tests (environment, failure analyzer, isolation, output formatter - all working)
- **Workflows Tests**: 10+ tests (LangGraph server - all working)
- **Smoke Tests**: 30+ tests (agentic workflow, critical endpoints - all working)
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
- **`AI_TESTING.md`** - AI Assistant test documentation
- **`AI_PRIORITY_1_TESTS_IMPLEMENTATION.md`** - AI test implementation summary

### Quick Reference
- **Total Tests**: 1200+
- **Active Tests**: 900+ (75%+)
- **Skipped Tests**: 205 (~17%)
- **Failing Tests**: 32 (~3%)
- **Test Files**: 100+
- **Categories**: 9 (Unit, UI, Integration, API, E2E, CLI, Utils, Workflows, Smoke)

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
