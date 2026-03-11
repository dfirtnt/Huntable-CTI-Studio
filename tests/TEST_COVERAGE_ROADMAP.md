# Test Coverage Roadmap

**Last Updated**: March 10, 2026  
**Status**: Comprehensive test coverage analysis and recommended improvements

---

## 📊 Current Test Coverage Summary

| Test Type | Files | Approximate Test Count | Coverage Level |
|-----------|-------|----------------------|----------------|
| **Playwright (TS)** | 42 files | ~280 tests | ✅ Excellent (Agent Config, Workflow) |
| **UI Tests (Python)** | 36 files | ~150 tests | ✅ Good (Most pages covered) |
| **API Tests** | 16 files | 117 tests | ⚠️ Moderate (Key endpoints missing) |
| **Integration Tests** | 12 files | 48 tests | ⚠️ Moderate (Need lifecycle coverage) |
| **Total** | 106 files | ~595 tests | **Good foundation, gaps identified** |

### Recent Additions (March 2026)
- ✅ 15 workflow config API tests (CRUD, validation, prompts, versions)
- ✅ 8 preset lifecycle API tests (import/export, save/restore)
- ✅ 6 agent config UI smoke tests
- ✅ 9 sources page UI smoke tests
- ✅ 1 Playwright test (real preset import with restoration)
- ✅ Fixed hardcoded database passwords (security improvement)

---

## 🔴 HIGH PRIORITY - Critical Missing Coverage

### 1. SIGMA Queue Management (Integration + E2E)
**Current Status**: Only basic enrich API tests exist  
**Gap**: Missing full lifecycle testing from queue → approve/reject → rules DB

**Recommended Tests**:

#### Integration: `tests/integration/test_sigma_queue_lifecycle.py`
```python
# Recommended test cases:
- test_add_rule_to_queue_and_retrieve()
- test_approve_rule_persists_to_rules_database()
- test_reject_rule_removes_from_queue()
- test_edit_queued_rule_yaml_validates_and_saves()
- test_bulk_approve_rejects_operations()
- test_queue_filtering_by_status_and_article()
- test_queue_search_by_rule_title()
- test_duplicate_detection_on_add()
```

#### Playwright: `tests/playwright/sigma_queue_comprehensive.spec.ts`
```typescript
// Recommended test cases:
- "should generate rule and add to queue"
- "should edit queued rule YAML inline"
- "should approve rule and verify it appears in rules list"
- "should reject rule and verify it's removed"
- "should enrich rule with additional context"
- "should save and load enrichment prompt presets"
- "should handle syntax errors in YAML editor"
- "should undo approve/reject within timeout"
- "should filter queue by article, status, date"
- "should export queue as JSON"
```

**Impact**: 🔥 **Critical** - Core detection engineering workflow  
**Estimated Effort**: 2-3 days  
**Justification**: SIGMA queue is a primary product feature. End-to-end testing ensures rule lifecycle integrity.

---

### 2. Analytics & Hunt Metrics (API + UI)
**Current Status**: No dedicated tests for 17+ analytics endpoints  
**Gap**: Analytics endpoints untested, no validation of aggregations/time-series

**Recommended Tests**:

#### API: `tests/api/test_analytics_api.py`
```python
# Recommended test cases (API validation):
@pytest.mark.api
class TestScraperAnalytics:
    - test_scraper_overview_returns_valid_structure()
    - test_collection_rate_time_series_format()
    - test_source_health_aggregation()
    - test_source_performance_metrics()

@pytest.mark.api
class TestHuntMetrics:
    - test_hunt_overview_returns_summary_stats()
    - test_score_distribution_histogram_data()
    - test_keyword_performance_aggregation()
    - test_keyword_analysis_by_source()
    - test_score_trends_time_series()
    - test_recent_high_scores_sorting()
    - test_advanced_metrics_complex_query()
    
@pytest.mark.api
class TestAnalyticsEvents:
    - test_post_analytics_event_persists()
    - test_get_events_with_filters()
    - test_event_aggregation_by_type()
```

#### Playwright: `tests/playwright/analytics_dashboard.spec.ts`
```typescript
// Recommended test cases (E2E UI):
- "should load analytics dashboard with charts"
- "should apply time range filter and update charts"
- "should display hover tooltips on chart data points"
- "should zoom into time range on chart"
- "should export chart data to CSV"
- "should switch between scraper and hunt metrics views"
- "should refresh data on demand"
- "should handle empty state gracefully"
```

**Impact**: 🔥 **Critical** - Key product visibility feature  
**Estimated Effort**: 3-4 days  
**Justification**: Analytics dashboard is primary monitoring interface. Data accuracy and UI reliability are essential.

---

### 3. Article Detail Page (E2E)
**Current Status**: Advanced UI tests exist, but no comprehensive E2E workflow  
**Gap**: Missing full user journey testing (view → annotate → trigger workflow → view results)

**Recommended Tests**:

#### Playwright: `tests/playwright/article_detail_full_workflow.spec.ts`
```typescript
// Recommended test cases:
- "should view article and display all sections"
- "should trigger workflow and monitor execution status"
- "should view generated SIGMA rules after workflow completes"
- "should add annotation and verify persistence"
- "should edit annotation and save changes"
- "should delete annotation with confirmation"
- "should mark article as high value and update hunt score"
- "should export article with annotations to JSON"
- "should share article via generated link"
- "should navigate to previous/next article"
- "should copy observables to clipboard"
- "should view article metadata (source, date, author)"
- "should view related articles (if feature exists)"
```

**Impact**: 🔥 **Critical** - Primary user interaction surface  
**Estimated Effort**: 2-3 days  
**Justification**: Article detail is the central hub for analyst workflow. Must ensure all interactions work reliably.

---

### 4. Observable Training (Integration)
**Current Status**: Only basic UI tests exist  
**Gap**: Missing data persistence validation and training pipeline integration

**Recommended Tests**:

#### Integration: `tests/integration/test_observable_training_lifecycle.py`
```python
# Recommended test cases:
- test_submit_training_example_persists_to_database()
- test_retrieve_training_data_for_model_training()
- test_observable_deduplication_on_submit()
- test_observable_validation_rules_enforced()
- test_batch_import_training_data_from_csv()
- test_training_data_export_format()
- test_observable_labeling_workflow()
- test_training_data_versioning()
- test_remove_invalid_observables()
- test_training_data_statistics_aggregation()
```

**Impact**: 🟡 **High** - ML training pipeline dependency  
**Estimated Effort**: 2 days  
**Justification**: Training data quality directly impacts model performance. Integration tests ensure data integrity.

---

## 🟡 MEDIUM PRIORITY - Important But Non-Critical

### 5. Evaluation & Comparison (Integration + UI)
**Current Status**: Basic eval execution tests exist  
**Gap**: Missing comparison workflows and aggregate metrics validation

**Recommended Tests**:

#### Integration: `tests/integration/test_evaluation_comparison_integration.py`
```python
# Recommended test cases:
- test_run_eval_on_two_config_versions_and_compare()
- test_aggregate_metrics_calculation_accuracy()
- test_subagent_evaluation_backfill()
- test_export_eval_bundle_includes_all_artifacts()
- test_eval_bundle_import_restores_state()
- test_comparison_delta_calculation()
- test_eval_execution_status_tracking()
```

#### Playwright: `tests/playwright/evaluation_comparison_ui.spec.ts`
```typescript
// Recommended test cases:
- "should navigate to evaluation comparison view"
- "should select two config versions to compare"
- "should display side-by-side metrics comparison"
- "should filter comparison by subagent"
- "should filter comparison by article"
- "should export comparison report to CSV"
- "should visualize improvement/regression"
```

**Impact**: 🟡 **Medium** - Important for model iteration  
**Estimated Effort**: 3 days  
**Justification**: Enables data-driven decisions on config changes.

---

### 6. Backup & Export (API + Integration)
**Current Status**: Minimal testing of backup functionality  
**Gap**: No validation of backup/restore integrity

**Recommended Tests**:

#### API: `tests/api/test_backup_api.py`
```python
# Recommended test cases:
- test_create_backup_triggers_job()
- test_backup_status_returns_progress()
- test_list_backups_returns_available_files()
- test_backup_download_serves_file()
- test_backup_schedule_configuration()
- test_backup_retention_policy()
```

#### Integration: `tests/integration/test_backup_restore_integration.py`
```python
# Recommended test cases:
- test_create_backup_writes_valid_file()
- test_backup_file_integrity_validation()
- test_incremental_backup_only_includes_changes()
- test_full_backup_includes_all_tables()
- test_restore_from_backup_in_test_environment()  # CAREFUL: test env only!
- test_backup_compression_and_encryption()
```

**Impact**: 🟡 **Medium** - Critical for data safety but infrequently used  
**Estimated Effort**: 2-3 days  
**Justification**: Data loss prevention is critical, but feature is rarely exercised in normal usage.

---

### 7. Settings & Configuration (E2E)
**Current Status**: API tests exist  
**Gap**: Missing comprehensive UI testing for admin configuration

**Recommended Tests**:

#### Playwright: `tests/playwright/settings_comprehensive.spec.ts`
```typescript
// Recommended test cases:
- "should update LLM provider settings and verify applied"
- "should update embedding model and trigger recalculation"
- "should update Redis connection settings"
- "should update Celery worker configuration"
- "should manage API keys (if feature exists)"
- "should configure backup schedule"
- "should test connection to external services"
- "should display validation errors for invalid settings"
- "should restore default settings"
```

**Impact**: 🟡 **Medium** - Admin functionality  
**Estimated Effort**: 2 days  
**Justification**: Settings changes can break the system. UI tests ensure safe configuration.

---

### 8. Search & Filtering (E2E)
**Current Status**: No dedicated search functionality tests  
**Gap**: Search/filter logic not validated end-to-end

**Recommended Tests**:

#### Playwright: `tests/playwright/search_and_filter.spec.ts`
```typescript
// Recommended test cases:
- "should search articles by keyword and display results"
- "should filter articles by date range"
- "should filter articles by source"
- "should filter articles by hunt score range"
- "should apply combined filters (date + source + score)"
- "should clear all filters and reset to full list"
- "should handle search with no results gracefully"
- "should paginate through search results"
- "should sort search results by relevance, date, score"
- "should save search as preset (if feature exists)"
```

**Impact**: 🟡 **Medium** - User productivity feature  
**Estimated Effort**: 1-2 days  
**Justification**: Search is a frequently used feature. Must work reliably.

---

## 🟢 NICE TO HAVE - Enhancements

### 9. Mobile Responsiveness (E2E)
**Current Status**: Basic tests exist  
**Gap**: Need comprehensive mobile workflow testing

**Recommended Tests**:

#### Playwright: `tests/playwright/mobile_critical_paths.spec.ts`
```typescript
// Recommended test cases (mobile viewport):
- "should display article list in mobile layout"
- "should view article detail on mobile device"
- "should trigger workflow from mobile UI"
- "should view SIGMA queue on mobile"
- "should access mobile navigation menu"
- "should view analytics dashboard on mobile"
- "should perform search on mobile"
- "should use touch gestures for navigation"
```

**Impact**: 🟢 **Low** - If mobile is not primary use case  
**Estimated Effort**: 1-2 days  
**Justification**: Nice to have if mobile usage is expected.

---

### 10. Error Recovery & Edge Cases (Integration)
**Current Status**: Some error handling tests exist  
**Gap**: Need systematic coverage of failure scenarios

**Recommended Tests**:

#### Integration: `tests/integration/test_error_recovery.py`
```python
# Recommended test cases:
- test_database_connection_loss_during_workflow_retries()
- test_redis_connection_loss_fallback_behavior()
- test_llm_api_timeout_handling_and_retry()
- test_celery_worker_crash_task_recovery()
- test_disk_space_full_during_backup_error()
- test_invalid_data_rollback_transaction()
- test_concurrent_modification_conflict_resolution()
- test_rate_limit_handling_for_external_apis()
```

**Impact**: 🟢 **Low-Medium** - Reliability in production  
**Estimated Effort**: 2-3 days  
**Justification**: Improves reliability but not immediately critical.

---

### 11. RAG Chat (E2E)
**Current Status**: Basic UI tests exist  
**Gap**: Missing conversation flow and context testing

**Recommended Tests**:

#### Playwright: `tests/playwright/rag_chat_conversation.spec.ts`
```typescript
// Recommended test cases:
- "should start chat session and ask question"
- "should maintain context across multi-turn conversation"
- "should upload document and chat about contents"
- "should switch LLM model mid-conversation"
- "should display sources used in response"
- "should export chat history to markdown"
- "should handle streaming responses"
- "should clear conversation and start fresh"
```

**Impact**: 🟢 **Low** - Feature-dependent priority  
**Estimated Effort**: 1-2 days  
**Justification**: If RAG chat is a key feature, this becomes higher priority.

---

### 12. Performance & Load (Integration)
**Current Status**: No performance regression tests  
**Gap**: No benchmarks to detect performance degradation

**Recommended Tests**:

#### Integration: `tests/integration/test_performance_benchmarks.py`
```python
# Recommended test cases (with time assertions):
- test_workflow_execution_100_articles_under_5_minutes()
- test_sigma_generation_complex_article_under_30_seconds()
- test_search_10k_articles_under_2_seconds()
- test_vector_similarity_search_1m_vectors_under_1_second()
- test_dashboard_load_time_under_3_seconds()
- test_concurrent_workflow_executions_throughput()
- test_database_query_performance_thresholds()
```

**Impact**: 🟢 **Low** - Good to have, not critical initially  
**Estimated Effort**: 2-3 days  
**Justification**: Catch performance regressions before they reach production.

---

## 📊 Implementation Summary

### Test File Additions Recommended

| Category | Current | Recommended New | Total New Tests | Priority |
|----------|---------|-----------------|----------------|----------|
| **Playwright (TS)** | 42 files | +8 files | ~40-60 tests | 🔴 High |
| **API Tests** | 16 files | +3 files | ~30-40 tests | 🔴 High |
| **Integration** | 12 files | +5 files | ~25-35 tests | 🟡 Medium |
| **UI (Python)** | 36 files | +2 files | ~15-20 tests | 🟢 Low |
| **TOTAL** | **106 files** | **+18 files** | **~110-155 tests** | - |

---

## 🎯 Suggested Implementation Order

### Sprint 1: Highest Impact (2-3 weeks)
1. ✅ **Already Complete**: Workflow config API + Preset lifecycle (23 tests)
2. 🔴 **SIGMA Queue lifecycle** (Integration + E2E) - ~20-25 tests
3. 🔴 **Analytics API tests** - ~15-20 tests
4. 🔴 **Article detail E2E workflow** - ~12-15 tests

**Sprint 1 Total**: ~50-60 new tests

---

### Sprint 2: Fill Critical Gaps (2-3 weeks)
5. 🟡 **Observable training integration** - ~10-12 tests
6. 🟡 **Evaluation comparison** (Integration + UI) - ~12-15 tests
7. 🟡 **Backup & export API** - ~8-10 tests
8. 🟡 **Settings E2E** - ~8-10 tests

**Sprint 2 Total**: ~38-47 new tests

---

### Sprint 3: Polish & Enhancements (2 weeks)
9. 🟢 **Search & filtering E2E** - ~10-12 tests
10. 🟢 **Error recovery** - ~8-10 tests
11. 🟢 **Mobile critical paths** - ~8-10 tests
12. 🟢 **Performance benchmarks** - ~7-8 tests

**Sprint 3 Total**: ~33-40 new tests

---

## 📈 Coverage Goals

### Current State (March 2026)
- **Total Tests**: ~595 tests
- **Coverage Level**: Good foundation with identified gaps
- **Critical Workflows**: ✅ Agent Config, ⚠️ SIGMA Queue, ⚠️ Analytics

### Target State (Post-Roadmap)
- **Total Tests**: ~710-750 tests (+115-155)
- **Coverage Level**: Comprehensive across all major features
- **Critical Workflows**: ✅ All primary user journeys covered

---

## 🔧 Testing Standards

All new tests must follow existing patterns:

### Test Markers
```python
@pytest.mark.smoke      # Fast tests (<5s total)
@pytest.mark.api        # API endpoint tests
@pytest.mark.integration_full  # Integration tests
@pytest.mark.ui         # UI/Playwright tests
```

### Database Usage
- ✅ Use `TEST_DATABASE_URL` (port 5433)
- ✅ Read password from `POSTGRES_PASSWORD` env var
- ❌ Never hardcode credentials
- ✅ Always clean up test data

### Cleanup & Restoration
- ✅ Save state before modifications
- ✅ Restore original state after test
- ✅ Delete test artifacts (presets, rules, etc.)
- ✅ Use fixtures for setup/teardown

---

## 📝 Notes

- This roadmap assumes 1-2 developers working part-time on test improvements
- Adjust priorities based on product roadmap and feature usage data
- Some tests may be skipped if features are deprecated
- Performance benchmarks should be revisited as codebase grows

---

**Document Owner**: Test Engineering Team  
**Next Review**: Q2 2026  
**Version**: 1.0
