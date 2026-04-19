# Skipped Tests Summary

## Overview
This document tracks tests that are currently skipped and need to be fixed.

**Last Updated**: 2026-03-10 (audit: doc vs code)
**Current Status**: 
- **Passing**: 568+ (many modules previously listed as SKIPPED now pass; see Test Status by Category)
- **Failed**: 12 (down from 128)
- **Skipped**: 167
- **Errors**: 583 (mostly async coroutine warnings, down from 625)

**Audit note**: The following modules were listed in this doc as "SKIPPED" but run **PASSING** when executed (unit/integration context): RSS Parser (46), Content Processor (50), Deduplication Service (35), Database Operations (23), Modern Scraper (18), test_search_parser (16), test_core (3), test_database (16). Counts and status below have been corrected.

## Unskip candidates (actually skipped, worth enabling)

| Target | Count | Blocker | Fix |
|--------|-------|---------|-----|
| **test_source_manager.py** `TestSourceConfigLoader` | 5 | Tests mock JSON + single `write()`; implementation uses **YAML** and multiple `write()` calls | Use YAML in mocks (or patch `yaml.safe_load`); assert `write` called with expected content or drop `assert_called_once()` |
| **test_annotations_api.py** | many | `pytest.skip("No articles available")` | Seed test DB with articles in API test setup (or shared fixture) |
| **test_endpoints.py** | 4 | 500 / "No articles" / 422 skips | Same: ensure DB + seed data in API job |
| **test_article_detail_advanced_ui.py** | 2 | No articles; observables mode inactive | Seed data; skip observables test if feature off |
| ~~test_annotation_ui_persistence.py~~ | 3 | Removed in UI test diet (all tests skipped, zero coverage) | N/A |
| **test_eval_ui_rendering.py** | 1 | "Requires eval data" | Add eval fixtures |
| **integration/test_annotation_persistence.py** | 3 | Async fixture teardown in different event loop | Same-loop teardown or dedicated integration run (see docs/solutions/...) |
| **Fixture-not-found** (sigma similarity, scraper_parsing, sigma_validator_roundtrip, compare_sources, workflow_config_schema) | 1 each | Golden/input/fixture file missing | Commit files to repo or skip only when file absent in CI |
| **test_sigma_enrich_ui.py** | 8 | "No rules in queue" | Seed rules or mock queue |
| **test_workflow_config_api.py** | 2 | No presets / ExtractAgent prompt not configured | Config or fixtures |
| **Quarantined** (dedupe_preserved, prompt_sync, training_endpoint_fallback, api_articles_limit) | 5 | Assertion/mock/500 issues | See Quarantined table for intended fixes |

## Quarantined Tests

Tests marked with `@pytest.mark.quarantine` that require fixes. All quarantined tests must be tracked in this table.

| Test File | Test Name | Reason | Owner | Created | Intended Fix |
|-----------|-----------|--------|-------|---------|--------------|
| test_hybrid_extractor.py | test_dedupe_preserved | Assertion failure: assert 0 == 1 | @system | 2026-01-15 | Fix regex pattern or assertion logic |
| test_ui/test_prompt_sync_ui.py | test_sigma_help_matches_sigma_generation_prompt | Prompt comparison assertion failure | @system | 2026-01-15 | Update prompt comparison logic |
| test_observable_training_api.py | test_training_endpoint_fallback | Mock setup issue with Celery task fallback | @system | 2026-01-15 | Fix Celery task mock |
| test_api/test_endpoints.py | test_api_articles_limit | API may return 500 if database is not accessible | @system | 2026-01-15 | Fix database connectivity or make assertion lenient |
| test_web_application.py | test_api_articles_with_limit | API may return 500 if database is not accessible | @system | 2026-01-15 | Fix database connectivity or make assertion lenient |
| e2e/test_web_interface.py | All 13 tests | Playwright browsers not installed in Docker | @system | 2026-01-15 | Install browsers: `playwright install` in container |
| test_web_application.py | All 10 API/route tests | Conditional skip on 500 / ASGI | @system | 2025-01-XX | Run in API job (USE_ASGI_CLIENT); may pass with DB up |
| test_annotation_persistence.py | test_create_annotation | Async fixture teardown runs in different event loop (asyncpg/pytest-asyncio) | @system | 2026-03-10 | Same-loop teardown or avoid rollback+real manager mix; see docs/solutions/test-failures/async-fixture-teardown-different-loop-IntegrationTests-20260310.md |
| test_annotation_persistence.py | test_get_annotation | Async fixture teardown runs in different event loop (asyncpg/pytest-asyncio) | @system | 2026-03-10 | Same as above |
| test_annotation_persistence.py | test_get_article_annotations | Async fixture teardown runs in different event loop (asyncpg/pytest-asyncio) | @system | 2026-03-10 | Same as above |

## Playwright Quarantined (test.describe.skip)

| Test File | Tests | Blocker | Status | Fix |
|-----------|-------|---------|--------|-----|
| playwright/workflow_executions.spec.ts | 17 (11 active + 6 skip) | Tests trigger real workflow executions that pollute production DB | Permanently quarantined | Mock workflow trigger API or use isolated test DB |
| playwright/observables_plain.spec.ts | 1 | Requires test data seeding (article with specific content) | Permanently quarantined | Seed article fixture or parametrize article ID |
| playwright/observables_exact_selection.spec.ts | 1 | Requires article 658 with specific phrases | Permanently quarantined | Seed article fixture or mock annotation API |

## Integration (skipped)

The following integration tests are skipped due to async event-loop/teardown issues. For full-system confidence goals and marker semantics, see [docs/development/testing.md](../docs/development/testing.md) (Integration vs lightweight).

- **test_annotation_persistence.py** (3 tests): `test_create_annotation`, `test_get_annotation`, `test_get_article_annotations` — reason and intended fix documented in the Quarantined Tests table above and in [docs/solutions/test-failures/async-fixture-teardown-different-loop-IntegrationTests-20260310.md](../docs/solutions/test-failures/async-fixture-teardown-different-loop-IntegrationTests-20260310.md).

## Test Status by Category

### ✅ Threat Hunting Scorer (26 tests - ALL PASSING)
All threat hunting scorer tests are working correctly and validate:
- Keyword matching algorithms
- Scoring logic
- Edge cases
- Return formats

### ✅ RSS Parser (46 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 46 tests pass. Doc previously said SKIPPED; code has no skip decorators.

**Test coverage includes**:
- Feed parsing and validation
- Entry extraction
- Date/URL/content extraction
- Quality filtering
- Author/tag extraction

### ✅ Content Processor (50 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 50 tests pass (doc said 47 SKIPPED).

**Test coverage includes**:
- Article processing pipeline
- Deduplication detection
- Quality filtering
- Metadata enhancement
- URL normalization

### ✅ Deduplication Service (35 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 35 tests pass.

**Test coverage includes**:
- SimHash computation
- Duplicate detection (exact & near)
- Content hashing
- Database integration

### ✅ Modern Scraper (18 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 18 tests pass.

**Test coverage includes**:
- URL discovery strategies
- Structured data extraction
- CSS selector scraping
- Legacy scraper fallback

### ✅ Database Operations (23 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 23 tests pass (doc said 33 tests SKIPPED; actual count 23).

**Test coverage includes**:
- CRUD operations (sources, articles, annotations)
- Database statistics
- Health metrics
- Performance analytics

### ✅ test_search_parser (16 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 16 tests pass (doc previously implied SKIPPED).

### ✅ test_core (3 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 3 tests pass.

### ✅ test_database (16 tests - PASSING)
**Status**: AUDIT 2026-03-10 — All 16 tests pass (doc said 5; actual 16).

### ✅ Content Filter (25 tests - ALL PASSING)
**Status**: FIXED - All tests now passing

**What was fixed**:
- ✅ Installed scikit-learn and pandas dependencies
- ✅ Implemented FilterResult and FilterConfig classes
- ✅ Fixed ML-based filtering logic and cost optimization
- ✅ Added quality scoring and batch processing

**Test coverage includes**:
- ML-based content filtering
- Cost optimization
- Quality scoring
- Batch processing

### ✅ SIGMA Validator (50 tests - ALL PASSING)
**Status**: FIXED - All tests now passing

**What was fixed**:
- ✅ Implemented ValidationError class
- ✅ Fixed SigmaRule validation logic
- ✅ Added custom validator support and batch validation
- ✅ Fixed rule structure validation

**Test coverage includes**:
- SIGMA rule validation
- Rule structure validation
- Custom validators
- Batch validation

### ✅ Source Manager (41 tests - 36 passed, 5 skipped)
**Status**: AUDIT 2026-03-10 — `tests/core/test_source_manager.py` (5 tests) all pass. `tests/test_source_manager.py`: 36 pass, **5 skipped** (class `TestSourceConfigLoader` — "SourceManager implementation needs review - missing SourceConfigLoader class", i.e. file-level loader vs core’s SourceConfigLoader).

**Test coverage includes**:
- Source configuration management (core)
- Source validation
- Import/export functionality
- Statistics tracking

### ✅ Content Cleaner (30 tests - ALL PASSING)
**Status**: FIXED - All tests now passing

**What was fixed**:
- ✅ Implemented ContentExtractor and TextNormalizer classes
- ✅ Fixed HTML cleaning logic and navigation element removal
- ✅ Added metadata extraction and Unicode normalization
- ✅ Fixed special character removal and text processing

**Test coverage includes**:
- HTML cleaning and sanitization
- Content extraction
- Text normalization
- Metadata extraction

### ⚠️ HTTP Client (39 tests - 38 PASSING, 1 FAILING)
**Status**: MOSTLY FIXED - 1 retry test still failing

**What was fixed**:
- ✅ Implemented RateLimiter, RequestConfig, and Response classes
- ✅ Fixed HTTP client logic and async/await issues
- ✅ Added rate limiting functionality and URL validation
- ✅ Fixed statistics tracking and edge case handling

**Remaining issue**:
- ❌ `test_request_with_retry` - retry logic doesn't match test expectations

**Test coverage includes**:
- HTTP client functionality
- Rate limiting
- Request configuration
- Response handling

## How to Re-enable Tests

### Prerequisites
1. Install async testing dependencies
2. Understand async mock patterns in pytest

### Steps to Fix
1. **Update async fixtures**:
   ```python
   @pytest.fixture
   async def async_session():
       session = AsyncMock()
       session.__aenter__ = AsyncMock(return_value=session)
       session.__aexit__ = AsyncMock(return_value=None)
       # Configure other async methods
       return session
   ```

2. **Mock async operations properly**:
   ```python
   mock_func.return_value = AsyncMock(return_value=expected_result)
   # OR
   mock_func.side_effect = AsyncMock(return_value=expected_result)
   ```

3. **Remove skip decorator**:
   ```python
   # Remove this line:
   @pytest.mark.skip(reason="...")
   ```

4. **Run tests and verify**:
   ```bash
   pytest tests/test_<module>.py -v
   ```

## Priority Order
1. **Database Operations** - Core infrastructure (23 tests) - ✅ PASSING (audit 2026-03-10)
2. **Content Processor** - Main processing logic (50 tests) - ✅ PASSING
3. **RSS Parser** - Primary data ingestion (46 tests) - ✅ PASSING
4. **Deduplication Service** - Critical for data quality (35 tests) - ✅ PASSING
5. **Source Manager** - Source configuration (41 tests: 36 passed, 5 skipped in test_source_manager) - ✅ MOSTLY PASSING
6. **SIGMA Validator** - Rule validation (50 tests) - ✅ FIXED
7. **Content Filter** - ML-based filtering (25 tests) - ✅ FIXED
8. **HTTP Client** - Network operations (39 tests) - ⚠️ MOSTLY FIXED (1 failing)
9. **Content Cleaner** - Content processing (30 tests) - ✅ FIXED
10. **Modern Scraper** - Alternative ingestion (18 tests) - ✅ PASSING

### ⏭️ ML Model Version Tests (3 tests - SKIPPED)
**Skip Reason**: Tests increment ML model versions in production database

**Skipped tests**:
- `test_model_retraining_trigger` (test_ml_feedback_workflow.py)
- `test_new_model_version_creation` (test_ml_feedback_workflow.py)
- `test_model_retrain_button` (test_ml_hunt_comparison_workflow.py)

**Test coverage includes**:
- Model retraining workflow
- Model version creation
- Model performance comparison

**To re-enable**: Run in isolated test environment with separate database

## Recent Updates
- **2024-10-27**: Disabled 3 ML model version tests that increment production model versions
- **2024-10-06**: Implemented Priority 1 AI Assistant tests (36 new tests)
- **2024-10-06**: Added comprehensive test documentation and runners
- **2024-10-06**: Updated test structure and organization
- **2024-12-19**: Fixed 5 high-priority test modules (ContentFilter, SigmaValidator, SourceManager, ContentCleaner, HTTPClient)
- **2024-12-19**: Implemented supporting classes and dependencies
- **2024-12-19**: 442 tests now passing (up from 27)

## Notes
- All test logic is sound
- Failures are purely due to mock configuration
- Test structure and assertions are ready to use
- Focus on fixing async mock patterns first
- 5 major test modules now fully functional
