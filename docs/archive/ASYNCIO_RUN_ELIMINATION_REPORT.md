# asyncio.run() Elimination Report

**Date:** 2026-01-15  
**Objective:** Systematically eliminate `asyncio.run()` from library code paths to prevent event loop conflicts in pytest-asyncio test runs.

## Summary

- **Total `asyncio.run()` occurrences found:** 28 in `src/`, 3 in `tests/`
- **Library code fixed:** 6 occurrences
- **CLI entrypoints (OK):** 12 occurrences (left as-is)
- **Celery tasks (OK):** 7 occurrences (left as-is, use proper pattern)
- **Test utilities (OK):** 3 occurrences (left as-is)

## Fixed Library Code

### 1. `src/core/rss_parser.py` (Line 380)
**Status:** ✅ FIXED  
**Change:** Replaced `asyncio.run()` with direct `await` since `_extract_content()` is already async
```python
# Before:
rss_only = asyncio.run(get_raw_config())

# After:
rss_only = await get_raw_config()
```

### 2. `src/web/routes/models.py` (Lines 46, 172)
**Status:** ✅ FIXED  
**Change:** 
- Line 46: Replaced `asyncio.run()` with direct `await` (route is async)
- Line 172: Used `run_sync()` helper for sync function called from thread
```python
# Before:
latest_version = asyncio.run(get_latest_version())

# After (in async route):
latest_version = await version_manager.get_latest_version()

# After (in sync thread function):
latest_version = run_sync(get_latest_version(), allow_running_loop=False)
```

### 3. `src/services/source_sync.py` (Line 111)
**Status:** ✅ FIXED  
**Change:** Replaced `asyncio.run()` with `run_sync()` helper
```python
# Before:
return asyncio.run(sync_sources(config_path, db_manager))

# After:
return run_sync(sync_sources(config_path, db_manager))
```

### 4. `src/services/evaluation/eval_runner.py` (Lines 27, 415)
**Status:** ✅ FIXED  
**Change:** 
- Line 27: Updated `_run_async_in_thread()` to use `new_event_loop()` pattern
- Line 415: Already had proper try/except, kept as-is (safe fallback)

### 5. `src/web/routes/ml_hunt_comparison.py` (Line 302)
**Status:** ✅ FIXED  
**Change:** Replaced `get_event_loop()` with `get_running_loop()`
```python
# Before:
loop = asyncio.get_event_loop()

# After:
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    raise RuntimeError("process_articles() must be called from async context")
```

### 6. `src/services/sigma_semantic_scorer.py` (Line 182)
**Status:** ✅ FIXED  
**Change:** Replaced `get_event_loop()` with `get_running_loop()`
```python
# Before:
loop = asyncio.get_event_loop()

# After:
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    raise RuntimeError("compare_rules() must be called from async context")
```

## Safe Async Helper Module

**File:** `src/utils/async_tools.py`  
**Status:** ✅ CREATED

Provides `run_sync()` function that:
- Raises `RuntimeError` if called from running event loop (prevents deadlocks)
- Falls back to `asyncio.run()` only when no loop is running
- Includes `allow_running_loop` option for edge cases (with warning)

## Left As-Is (Acceptable)

### CLI Entrypoints (12 occurrences)
These are legitimate uses of `asyncio.run()` in CLI commands:
- `src/cli/commands/search.py`
- `src/cli/commands/export.py`
- `src/cli/commands/rescore.py`
- `src/cli/commands/embed.py`
- `src/cli/commands/init.py`
- `src/cli/commands/stats.py`
- `src/cli/commands/collect.py`
- `src/cli/commands/sync_sources.py`

### Celery Tasks (7 occurrences)
These use `asyncio.run()` in Celery task context (separate process):
- `src/worker/celery_app.py` (multiple tasks)
- `src/worker/tasks/annotation_embeddings.py` (multiple tasks)

**Note:** Celery tasks run in separate processes, so `asyncio.run()` is safe. However, the pattern in `celery_app.py` line 680-686 uses `new_event_loop()` which is the correct approach.

### Test Utilities (3 occurrences)
- `tests/utils/database_connections.py`
- `tests/smoke/run_smoke_tests.py`
- `tests/e2e/mcp_orchestrator.py`

## Test Categorization

### Unit Tests (Marked)
- `tests/test_database_operations.py` - Uses mocks, no real DB
- `tests/test_http_client.py` - Uses mocks
- `tests/test_rss_parser.py` - Uses mocks
- `tests/test_modern_scraper.py` - Uses mocks
- `tests/services/test_scraper_parsing.py` - Uses fixtures
- `tests/services/test_observable_evaluation_evaluator.py` - Uses mocks
- `tests/services/test_observable_evaluation_span_normalization.py` - Pure logic
- `tests/services/test_sigma_validator_roundtrip.py` - Uses fixtures
- `tests/services/test_sigma_similarity_deterministic.py` - Uses golden files

### Integration Tests (Marked)
- `tests/integration/test_lightweight_integration.py` - May need test containers
- `tests/integration/test_ai_cross_model_integration.py` - Requires API keys or mocking

### E2E Tests (Marked)
- `tests/e2e/test_web_interface.py` - Requires web server + Playwright

## Pytest Configuration

**File:** `tests/pytest.ini`  
**Status:** ✅ VERIFIED

- `asyncio_mode = auto` - Automatically detects async test functions
- Consistent fixture and test loop scopes

## Remaining Issues

### Tests Still Failing
1. **Event loop conflicts** - Some tests may still trigger `asyncio.run()` in code paths not yet fixed
2. **Integration tests** - Require test containers (Postgres, Redis)
3. **E2E tests** - Require web server running
4. **Other test failures** - Various assertion/implementation issues

### Next Steps
1. Run unit test suite to verify event loop conflicts are resolved
2. Ensure test containers are available for integration tests
3. Quarantine tests that require infrastructure until containers are set up
4. Fix remaining test-specific issues (assertions, mocks, etc.)

## Verification

To verify fixes:
```bash
# Run unit tests only (should not require containers)
python3 run_tests.py unit

# Run integration tests (requires test containers)
make test-up
python3 run_tests.py integration
make test-down
```

## Impact

- **Before:** 136 failures, many from event loop conflicts
- **Expected After:** Reduced failures, unit tests should pass without containers
- **Integration/E2E:** Will still require proper infrastructure setup
