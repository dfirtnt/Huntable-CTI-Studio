# Test Failure Inventory

**Date**: 2026-01-15  
**Purpose**: Categorize and track pytest test failures for systematic fixing

## Summary

- **Total Errors**: ~26 (E2E + Integration system tests)
- **Total Failures**: ~128 (various categories)
- **Async Errors**: Significantly reduced (from 625 to warnings only)

## Error Categories

### 1. E2E Test Errors (13 tests)
**File**: `tests/e2e/test_web_interface.py`
**Category**: Infrastructure/Connection
**Tests**:
- `test_homepage_loads`
- `test_navigation_menu`
- `test_sources_page`
- `test_articles_page`
- `test_api_endpoints`
- `test_search_functionality`
- `test_responsive_design`
- `test_error_handling`
- `test_performance`
- `test_accessibility`
- `test_threat_hunting_scoring`
- `test_source_management`
- `test_data_export`

**Root Cause**: Likely requires running web server, connection issues, or missing infrastructure
**Fix Strategy**: Verify web server is running, check connection URLs, add proper `@pytest.mark.e2e` markers

### 2. Integration System Test Errors (13 tests)
**File**: `tests/integration/test_system_integration.py`
**Category**: Infrastructure/DB Connectivity
**Tests**:
- `TestSystemHealth::test_system_startup`
- `TestSystemHealth::test_database_connectivity`
- `TestSystemHealth::test_quality_assessment_pipeline`
- `TestDataFlow::test_article_to_analysis_flow`
- `TestDataFlow::test_api_data_consistency`
- `TestErrorHandling::test_system_error_handling`
- `TestErrorHandling::test_database_error_handling`
- `TestPerformance::test_system_response_times`
- `TestPerformance::test_concurrent_user_simulation`
- `TestSecurity::test_input_validation`
- `TestSecurity::test_authentication_requirements`
- `TestDataIntegrity::test_article_data_integrity`

**Root Cause**: Requires full system stack (DB, Redis, Celery, Web server)
**Fix Strategy**: Verify test containers are running, check database connectivity, ensure proper test environment setup

## Failure Categories

### 3. API Test Failures (4 tests)
**Files**: 
- `tests/api/test_annotations_api.py`
- `tests/api/test_endpoints.py`
- `tests/api/test_observable_training_api.py`

**Tests**:
- `TestCreateAnnotation::test_create_cmd_annotation`
- `TestAPIEndpoints::test_api_articles`
- `TestObservableTrainingSummary::test_summary_endpoint`
- `TestObservableTrainingRun::test_training_endpoint_fallback`

**Category**: Mock/Assertion issues
**Fix Strategy**: Review mock setups, fix assertions, update test data

### 4. Integration Test Failures (22+ tests)
**Files**:
- `tests/integration/test_ai_cross_model_integration.py` (12 failures)
- `tests/integration/test_lightweight_integration.py` (10+ failures)
- `tests/integration/test_sigma_save_workflow.py` (1 failure)

**Category**: Infrastructure/Mock/Assertion issues
**Fix Strategy**: 
- Verify infrastructure availability
- Fix mock setups
- Update assertions for changed behavior
- Check if tests require external APIs

### 5. Service Test Failures (5+ tests)
**Files**:
- `tests/services/test_scraper_parsing.py`
- `tests/test_content_filter.py`
- `tests/test_content_processor.py`

**Tests**:
- `TestScraperParsing::test_rss_parsing_with_fixture`
- `TestContentFilter::test_filter_articles_batch`
- `TestContentProcessor::test_process_articles_empty_list`
- `TestContentProcessor::test_process_articles_success`
- `TestContentProcessor::test_process_articles_with_existing_hashes`
- `TestContentProcessor::test_process_articles_with_existing_urls`

**Category**: Mock/Async/Assertion issues
**Fix Strategy**: Fix mock configurations, update assertions, fix async/await issues

## Priority Order

1. **High Priority**: E2E and Integration system test errors (26 errors) - Block full test suite
2. **Medium Priority**: API test failures (4 failures) - Core functionality
3. **Medium Priority**: Service test failures (5+ failures) - Core functionality
4. **Lower Priority**: Integration test failures (22+ failures) - May require external dependencies

## Next Steps

1. Fix E2E test errors (add proper markers, verify infrastructure)
2. Fix Integration system test errors (verify containers, fix connectivity)
3. Fix API test failures (review mocks, fix assertions)
4. Fix Service test failures (fix mocks, update assertions)
5. Fix Integration test failures (systematic review)
