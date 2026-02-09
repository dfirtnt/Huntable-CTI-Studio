# Test Groups Documentation

**Date**: 2025-11-24  
**Purpose**: Document all test groups, their mappings, execution order, and dependencies

## Overview

Tests are organized into groups for organized execution and reporting. Each group represents a category of tests with similar characteristics, dependencies, and execution times.

## Test Groups

### 1. smoke

**Description**: Quick health check tests  
**Duration**: ~30 seconds  
**Dependencies**: Minimal (application running)  
**Test Path**: `-m smoke`  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Verify critical endpoints and basic functionality are working.

**Test Files**:
- `tests/smoke/test_critical_smoke_tests.py`

**Run Command**:
```bash
python run_tests.py smoke
python scripts/run_tests_by_group.py --group smoke
```

---

### 2. unit

**Description**: Unit tests excluding other categories  
**Duration**: ~1 minute  
**Dependencies**: None (uses mocks)  
**Test Path**: `tests/` with marker exclusion  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test individual components in isolation with mocked dependencies.

**Test Paths**:
- `tests/` (root level test files)
- Excludes: smoke, integration, api, ui, e2e, performance markers

**Test Files**:
- `tests/test_*.py` (root level)
- `tests/core/`
- `tests/services/`
- `tests/utils/`
- `tests/workflows/`
- `tests/cli/`

**Run Command**:
```bash
python run_tests.py unit
python scripts/run_tests_by_group.py --group unit
```

**Note**: CLI, workflows, and services tests fall under this category but are not explicitly mapped. They are included via the unit test path.

---

### 3. api

**Description**: API endpoint tests  
**Duration**: ~2 minutes  
**Dependencies**: Application running  
**Test Path**: `tests/api/`  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test REST API endpoints and their responses.

**Test Files**:
- `tests/api/test_annotations_api.py`
- `tests/api/test_endpoints.py`

**Run Command**:
```bash
python run_tests.py api
python scripts/run_tests_by_group.py --group api
```

---

### 4. integration

**Description**: System integration tests  
**Duration**: ~3 minutes  
**Dependencies**: Full Docker stack (database, Redis, Celery)  
**Test Path**: `tests/integration/` with `integration_workflow` marker  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test cross-component interactions and workflows.

**Test Files**:
- `tests/integration/test_ai_cross_model_integration.py`
- `tests/integration/test_ai_real_api_integration.py`
- `tests/integration/test_lightweight_integration.py`
- `tests/integration/test_system_integration.py`

**Run Command**:
```bash
python run_tests.py integration
python scripts/run_tests_by_group.py --group integration
```

**Note**: Uses test database (`cti_scraper_test`) with transaction rollback for isolation.

---

### 5. ui

**Description**: Web interface tests  
**Duration**: ~5 minutes  
**Dependencies**: Playwright, browser, application running on localhost:8001  
**Test Path**: `tests/ui/`  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test web interface functionality, interactions, and user workflows.

**Test Files**:
- `tests/ui/test_*.py` (31 files)
- Includes comprehensive UI tests for all pages

**Run Command**:
```bash
python run_tests.py ui
python scripts/run_tests_by_group.py --group ui
```

**Note**: UI tests are read-only and do not modify database or config files.

---

### 6. e2e

**Description**: End-to-end tests  
**Duration**: ~3 minutes  
**Dependencies**: Full environment (Docker stack, browser)  
**Test Path**: `tests/e2e/`  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test complete user workflows from start to finish.

**Test Files**:
- `tests/e2e/test_web_interface.py`
- Playwright tests in `tests/playwright/`

**Run Command**:
```bash
python run_tests.py e2e
python scripts/run_tests_by_group.py --group e2e
```

---

### 7. performance

**Description**: Performance tests  
**Duration**: ~2 minutes  
**Dependencies**: Application running  
**Test Path**: `tests/` with `performance` marker  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test performance characteristics, load handling, and response times.

**Test Files**:
- Tests marked with `@pytest.mark.performance`

**Run Command**:
```bash
python run_tests.py performance
python scripts/run_tests_by_group.py --group performance
```

---

### 8. ai

**Description**: AI-specific tests  
**Duration**: ~3 minutes  
**Dependencies**: AI services (can be mocked)  
**Test Path**: Specific files + `ai` marker  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test AI integrations and workflows (includes legacy AI Assistant test coverage).

**Test Files**:
- `tests/ui/test_ai_assistant_ui.py` (deprecated/disabled with AI Assistant removal)
- `tests/integration/test_ai_*.py`
- Tests marked with `@pytest.mark.ai`

**Run Command**:
```bash
python run_tests.py ai
python scripts/run_tests_by_group.py --group ai
```

---

## Test Directory Mapping

| Directory | Group | Notes |
|-----------|-------|-------|
| `tests/smoke/` | smoke | Explicitly mapped |
| `tests/api/` | api | Explicitly mapped |
| `tests/integration/` | integration | Explicitly mapped |
| `tests/ui/` | ui | Explicitly mapped |
| `tests/e2e/` | e2e | Explicitly mapped |
| `tests/cli/` | unit | Falls under unit (not explicitly mapped) |
| `tests/core/` | unit | Falls under unit (not explicitly mapped) |
| `tests/services/` | unit | Falls under unit (not explicitly mapped) |
| `tests/utils/` | unit | Falls under unit (not explicitly mapped) |
| `tests/workflows/` | unit | Falls under unit (not explicitly mapped) |
| `tests/playwright/` | e2e/ui | Playwright tests included in e2e/ui groups |

## Execution Order

Tests are executed in this order when running all groups:

1. **smoke** - Quick health check first
2. **unit** - Fast unit tests
3. **api** - API endpoint verification
4. **integration** - System integration
5. **ui** - User interface tests
6. **e2e** - End-to-end workflows
7. **performance** - Performance characteristics
8. **ai** - AI functionality

**Rationale**: Start with fast, low-dependency tests, then progress to slower, higher-dependency tests.

## Dependencies

### Minimal Dependencies
- **smoke**: Application running
- **unit**: None (uses mocks)

### Medium Dependencies
- **api**: Application running
- **performance**: Application running

### Full Dependencies
- **integration**: Docker stack (database, Redis, Celery)
- **ui**: Playwright, browser, application on localhost:8001
- **e2e**: Full environment
- **ai**: AI services (can be mocked)

## Integration Status

### Fully Integrated ✅
- smoke
- unit
- api
- integration
- ui
- e2e
- performance
- ai

### Partially Integrated ⚠️
- **CLI tests** (`tests/cli/`) - Falls under unit, not explicitly mapped
- **Workflows tests** (`tests/workflows/`) - Falls under unit, not explicitly mapped
- **Services tests** (`tests/services/`) - Falls under unit, not explicitly mapped

**Recommendation**: These are covered by the `unit` group but could benefit from explicit mapping for clarity.

### Separate Runners (Not Integrated)
- `tests/run_ai_tests.py` - Specialized AI test runner
- `tests/run_lightweight_tests.py` - Lightweight integration runner
- `tests/smoke/run_smoke_tests.py` - Smoke test runner

**Recommendation**: Consider migrating functionality to `run_tests.py` for consistency.

## Grouped Execution

Use `scripts/run_tests_by_group.py` to execute tests by group:

```bash
# Run all groups
python scripts/run_tests_by_group.py

# Run specific group
python scripts/run_tests_by_group.py --group smoke

# Run multiple groups
python scripts/run_tests_by_group.py --group ui --group e2e

# Stop at first failure
python scripts/run_tests_by_group.py --stop-on-failure

# Verbose output
python scripts/run_tests_by_group.py --verbose
```

**Output**:
- Console output with progress indicators
- JSON report (`test_results_by_group.json`)
- Markdown summary (`test_results_summary.md`)
- Broken tests list (`broken_tests.txt`)

## Test Safety

All test groups are verified to be non-impactful to production data and configuration files. See `docs/TEST_DATA_SAFETY.md` for details.

**Key Safety Mechanisms**:
- Test database isolation (`cti_scraper_test`)
- Transaction rollback fixtures
- Read-only config access
- Disabled ML model tests
- Default marker exclusions

## Recommendations

### Short-Term
1. ✅ Document all test groups (this document)
2. ✅ Create grouped execution script
3. ✅ Verify data safety

### Medium-Term
1. Add explicit mappings for CLI, workflows, services test types
2. Migrate specialized runners to `run_tests.py`
3. Add test isolation verification tests

### Long-Term
1. Add test group dependencies (e.g., integration depends on smoke passing)
2. Add parallel execution support per group
3. Add test group coverage reporting
