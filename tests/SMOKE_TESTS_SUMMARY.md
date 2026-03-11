# Smoke Tests Summary

## Overview
Fast smoke tests that validate core application functionality in under 5 seconds total.
These tests run on every commit to ensure basic health before more comprehensive testing.

## Test Suites

### 1. Sources Page Smoke Tests
**File:** `tests/ui/test_sources_smoke_ui.py`  
**Tests:** 9  
**Runtime:** ~0.6s  
**Markers:** `@pytest.mark.smoke`, `@pytest.mark.sources`

#### Coverage:
- ✅ Page loads successfully
- ✅ API endpoints respond
- ✅ UI sections render
- ✅ Action buttons exist
- ✅ Modals present
- ✅ PDF upload section
- ✅ Manual URL scraping form
- ✅ Failing sources endpoint
- ✅ Breadcrumb navigation

### 2. Agent Configuration Smoke Tests
**File:** `tests/ui/test_agent_config_smoke_ui.py`  
**Tests:** 6  
**Runtime:** ~0.8s  
**Markers:** `@pytest.mark.smoke`, `@pytest.mark.workflow`

#### Coverage:
- ✅ Workflow page loads
- ✅ Configuration tab accessible
- ✅ Workflow config API health
- ✅ Save button present
- ✅ Agent panels load
- ✅ Preset selector present

## Performance Metrics

| Test Suite | Tests | Runtime | Avg/Test |
|------------|-------|---------|----------|
| Sources | 9 | 0.63s | 70ms |
| Agent Config | 6 | 0.87s | 145ms |
| **Combined** | **15** | **1.24s** | **83ms** |

## Running Smoke Tests

### Run All Smoke Tests
```bash
python run_tests.py smoke
```

### Run Specific Suite
```bash
# Sources only
pytest tests/ui/test_sources_smoke_ui.py -m smoke

# Agent Config only
pytest tests/ui/test_agent_config_smoke_ui.py -m smoke
```

### Run in CI/CD
```bash
APP_ENV=test TEST_DATABASE_URL="..." pytest -m smoke -v
```

## Success Criteria

- ✅ All tests complete in <5 seconds total
- ✅ All tests pass consistently
- ✅ No false positives/negatives
- ✅ Can run in parallel with other tests
- ✅ Suitable for pre-commit hooks

## Integration with Test Infrastructure

### Markers Used
- `@pytest.mark.smoke` - Fast health check tests
- `@pytest.mark.sources` - Sources page specific
- `@pytest.mark.workflow` - Workflow/agent config specific
- `@pytest.mark.asyncio` - Async test execution

### Fixtures Used
- `async_client` - HTTP client for API testing (from conftest.py)

### Environment Requirements
- `APP_ENV=test` - Required for test mode
- `TEST_DATABASE_URL` - Test database connection
- Application running on test URL (default: http://localhost:8001)

## Comparison with Existing Tests

### Before (Existing)
- Total smoke tests: ~31 (mostly API endpoints)
- Runtime: Variable, some slow
- Coverage: API-focused, limited UI

### After (New)
- Total smoke tests: 46 (31 existing + 15 new)
- Runtime: 15 new tests in 1.24s
- Coverage: API + UI page health

## Next Steps

### Potential Additions
1. Dashboard page smoke tests (4-5 tests)
2. Articles page smoke tests (6-7 tests)
3. PDF Upload page smoke tests (3-4 tests)
4. Settings page smoke tests (5-6 tests)

### Maintenance
- Review test performance monthly
- Update assertions if UI changes
- Add tests for new critical pages
- Remove tests for deprecated features

## References

- Test Plan: `TEST_PLAN_SOURCES.md`
- Test Plan: `TEST_PLAN_AGENT_CONFIG.md`
- Test Runner: `run_tests.py`
- Config: `tests/conftest.py`
