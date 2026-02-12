# Testing

<!-- MERGED FROM: development/TESTING_STRATEGY.md, development/TEST_PLAN.md, development/TEST_GROUPS.md, development/TEST_DATA_SAFETY.md -->

# Testing Strategy

## Overview

This document defines the testing strategy for CTIScraper, a single-user, local-first CTI research application. The strategy focuses on regression confidence across core analyst workflows while maintaining testability and speed.

## Test Pyramid

```
        /\
       /E2E\        ≤2 Playwright tests (full analyst workflows)
      /------\
     /Integration\  ~20 tests (cross-component, stateful)
    /------------\
   /    Unit      \  ~80 tests (pure functions, stateless)
  /----------------\
```

## Test Categories

### Stateless Tests (No Containers)

These tests do NOT require database connections or containers:

- Pure frontend tests (Jinja templates + Tailwind + vanilla JS behavior; React only for CDN RAGChat if tested)
- Backend unit tests without DB connections
- Similarity search with in-memory fixtures
- YAML parsing, linting, round-trip logic
- Utility functions, selectors, scoring logic

**Requirements:**
- No `APP_ENV=test` required
- No `TEST_DATABASE_URL` required
- Can run in parallel without isolation

### Stateful Tests (Containers Required)

These tests require ephemeral test containers:

- Database writes (articles, annotations, sigma rules)
- Celery task execution
- Integration tests with persistence
- E2E workflows

**Requirements:**
- `APP_ENV=test` must be set
- `TEST_DATABASE_URL` must be set (never `DATABASE_URL`)
- Test containers must be running (`make test-up`)
- Database name must contain "test"

## Fixture Strategy

### Location
All fixtures are stored in `tests/fixtures/` with the following structure:

```
tests/fixtures/
├── rss/              # RSS and Atom feed samples
├── html/             # HTML page samples
├── sigma/            # SIGMA YAML rules (valid, invalid, round-trip)
├── similarity/       # Similarity search inputs/outputs (golden files)
└── articles/         # Article JSON samples
```

### Golden Files

Golden files (especially in `similarity/`) include:
- Version metadata (schema version, created date, model version)
- Stable ranking for fixed corpus
- Relative comparisons ("A > B > C" relationships)
- Score ranges (min/max) rather than exact floats

**Update Process:**
1. Run similarity search with fixed corpus
2. Capture rule ordering and score ranges
3. Update `expected_ordering.json` with new version
4. Document what changed in version notes
5. Commit both input and expected files together

### Factories

Factories in `tests/factories/` provide reusable test data creation:
- `ArticleFactory` - Article creation
- `AnnotationFactory` - Annotation creation
- `AgentConfigFactory` - Agent config creation
- `EvalFactory` - Eval run creation
- `SigmaFactory` - SIGMA rule creation

## Database Safety

### Guard Function

`assert_test_environment()` in `tests/utils/test_environment.py` ensures:
- `APP_ENV=test` is set
- `TEST_DATABASE_URL` is set (mandatory, no fallback to `DATABASE_URL`)
- `DATABASE_URL` is either unset OR points to a test database
- Database name contains "test"
- Production database (`cti_scraper` without "test") is never used

### Implementation

- Invoked in `pytest_configure()` hook (pytest bootstrap)
- Invoked in Celery app initialization (when `APP_ENV=test`)
- Fails fast with clear error messages

## API Key Safety

### Cloud LLM Prohibition

Cloud LLM API keys are **prohibited** in tests by default:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `CHATGPT_API_KEY`

**Behavior:**
- If cloud keys are present and `ALLOW_CLOUD_LLM_IN_TESTS` is not set → tests fail
- If `ALLOW_CLOUD_LLM_IN_TESTS=true` is set → tests proceed with warning
- Local LLM keys (`LMSTUDIO_API_URL`) are allowed by default

**Rationale:** Prevents accidental API usage and costs during test execution.

## Test Containers

### Configuration

- **File**: `docker-compose.test.yml`
- **Services**: `postgres_test` (port 5433), `redis_test` (port 6380), `web_test` (port 8002)
- **Volumes**: **No named volumes** - data exists only in container filesystem
- **Network**: Isolated `test_network`

### Lifecycle (Script-Driven)

- **Start**: `make test-up` or `./scripts/test_setup.sh`
- **Run tests**: `make test` or `./scripts/run_tests.sh` (auto-configures env vars)
- **Tear down**: `make test-down` or `./scripts/test_teardown.sh`

**Rationale:** Avoids brittle pytest hooks, supports parallel runs, reduces local dev friction.

## Determinism Rules

### Similarity Search

- Assert relative ordering ("A > B > C"), not exact scores
- Use score ranges (min/max), not exact floats
- Golden files include version metadata for tracking changes

### Randomness

- Use seeded random number generators
- No network calls in unit/integration tests
- Use fixtures instead of live data

### Flaky Test Prevention

- Avoid time-dependent assertions
- Use deterministic fixtures
- Mock external services consistently

## Regression Tracking

### Coverage Approach

- Use `pytest-cov` for line coverage
- Target: 70%+ for critical modules (SIGMA, annotations, workflows)
- Track coverage trends over time (not absolute numbers)

### Risk Tracking

- Document regression risks in this document
- Track test execution time (target: <10min for full suite)
- Monitor flaky test rate (target: <1%)

### Quarantine Tracking

Quarantined tests (marked with `@pytest.mark.quarantine`) are tracked in `tests/SKIPPED_TESTS.md` with:
- Test file and name
- Reason for quarantine
- Owner (who will fix)
- Created date
- Intended fix approach

CI reports quarantine counts to prevent skip creep.

### UI tests without agent config mutation

Some UI tests mutate agent/workflow/settings config (run evaluations, save settings, save workflow config). To run only UI tests that **do not** mutate agent configs:

```bash
python3 run_tests.py ui --exclude-markers agent_config_mutation
```

This excludes:

- **Pytest (tests/ui/)**: tests marked `@pytest.mark.agent_config_mutation` (run evaluation, save settings, save workflow config).
- **Playwright TypeScript (tests/playwright/)**: specs that change workflow/agent config are ignored via `CTI_EXCLUDE_AGENT_CONFIG_TESTS=1` (e.g. `agent_config_*.spec.ts`, `workflow_save_button.spec.ts`, `workflow_config_persistence.spec.ts`, `workflow_config_versions.spec.ts`).

## CI Recommendations

### Speed

- Run stateless tests in parallel
- Use test containers for stateful tests only
- Cache dependencies and fixtures

### Flake Prevention

- Retry failed tests once (not in CI)
- Use deterministic fixtures
- Avoid time-dependent tests
- Mock external services

### Execution Order

1. Stateless tests (fast, parallel)
2. Integration tests (with containers)
3. E2E tests (slow, sequential)

## Out of Scope

- **Analytics pages** (`/analytics` and subpages) - Likely to be deprecated
- Authentication/authorization tests - Single-user application
- Security/adversarial tests - Not a security-hardened system
- Multi-user tests - Local-first, single-user design


---

# Test Plan

## Overview

This document outlines the test plan for CTIScraper, focusing on critical analyst workflows and high-risk modules.

## Top 20 Critical Analyst Workflows (Risk-Based)

### HIGH Priority

1. **RSS ingestion → article persistence** - Core data ingestion path
2. **Article annotation → database persistence** - User interaction and training data
3. **Extraction agent execution → workflow state** - Core analysis capability
4. **SIGMA generation → validation → save** - Primary output generation
5. **SIGMA similarity search → deterministic ordering** - Prevents duplicate rules

### MEDIUM Priority

6. **Eval run → metrics rendering** - Quality assurance
7. **Eval snapshot comparison** - Historical analysis
8. **Agent config create/edit/version** - Configuration management
9. **Celery task state transitions** - Background processing reliability
10. **Web scraper fallback (RSS → Modern → Legacy)** - Ingestion resilience
11. **Article deduplication** - Data quality
12. **Source health monitoring** - Operational awareness

### LOW Priority

13. **Annotation feedback loop** - Training improvement
14. **RAG chat conversation** - Search capability
15. **PDF upload → processing** - Alternative ingestion
16. **Settings persistence** - Configuration
17. **Navigation/routing** - User experience
18. **Modal interactions** - UI behavior
19. **Collapsible panel behavior** - UI behavior
20. **MkDocs build sanity** - Documentation integrity

## Top 30 Critical Modules (Unit/Integration)

### Backend (20 modules)

1. `src/services/sigma_matching_service.py` - Similarity search (HIGH)
2. `src/services/sigma_validator.py` - YAML validation (HIGH)
3. `src/services/sigma_generation_service.py` - Rule generation (HIGH)
4. `src/core/rss_parser.py` - RSS parsing (HIGH)
5. `src/core/fetcher.py` - Content fetching (HIGH)
6. `src/services/deduplication.py` - Deduplication (MEDIUM)
7. `src/worker/celery_app.py` - Task orchestration (MEDIUM)
8. `src/database/async_manager.py` - Database operations (HIGH)
9. `src/services/rag_service.py` - RAG similarity (MEDIUM)
10. `src/workflows/agentic_workflow.py` - Workflow execution (HIGH)
11. `src/services/llm_service.py` - LLM agent execution (HIGH)
12. `src/web/routes/annotations.py` - Annotation API (HIGH)
13. `src/web/routes/evaluation_api.py` - Eval API (MEDIUM)
14. `src/services/evaluation/eval_runner.py` - Eval execution (MEDIUM)
15. `src/core/processor.py` - Content processing (HIGH)
16. `src/utils/ioc_extractor.py` - IOC extraction (MEDIUM, deprecated/disabled)
17. `src/services/embedding_service.py` - Embedding generation (MEDIUM)
18. `src/web/routes/sigma_queue.py` - SIGMA queue (HIGH)
19. `src/services/sigma_semantic_scorer.py` - Semantic scoring (MEDIUM)
20. `src/cli/commands/export.py` - Export functionality (LOW)

### Frontend (10 modules)

1. `src/web/static/js/annotation-manager.js` - Annotation UI (HIGH)
2. `src/web/templates/article_detail.html` - Article detail (HIGH)
3. `src/web/templates/workflow.html` - Workflow UI (HIGH)
4. `src/web/templates/sigma_queue.html` - SIGMA queue UI (HIGH)
5. `src/web/templates/evaluations.html` - Eval UI (MEDIUM, deprecated/removed)
6. `src/web/templates/settings.html` - Settings UI (LOW)
7. Navigation/routing logic (vanilla JS) (LOW)
8. Modal interaction handlers (vanilla JS) (LOW)
9. Collapsible panel components (vanilla JS + Tailwind) (LOW)
10. `src/web/static/js/components/RAGChat.jsx` - React component (LOW)

## Test Implementation Status

### Phase 0: Fix Existing Failures ✅

- Fixed HTTP retry test (1 test)
- Documented 205 skipped tests in `tests/SKIPPED_TESTS.md`
- Added `@pytest.mark.quarantine` marker

### Phase 1: Infrastructure ✅

- Created `docker-compose.test.yml` (test containers)
- Created `tests/utils/test_environment.py` (safety guards)
- Created script-driven lifecycle (`scripts/test_setup.sh`, etc.)
- Updated `tests/conftest.py` with guard invocation
- Updated `src/worker/celery_app.py` with guard
- Updated `src/database/async_manager.py` to prefer `TEST_DATABASE_URL`

### Phase 2: Fixtures & Factories ✅

- Created fixtures directory structure
- Created sample fixtures (RSS, HTML, SIGMA, similarity, articles)
- Created factories (articles, annotations, configs, evals, sigma)
- Created golden files for similarity search

### Phase 3: Backend Tests ✅

**Stateless Tests:**
- `test_sigma_similarity_deterministic.py` - Similarity search ordering
- `test_sigma_validator_roundtrip.py` - YAML round-trip integrity
- `test_scraper_parsing.py` - Scraper parsing with fixtures
- `test_agent_config_validation.py` - Agent config validation/versioning

**Stateful Tests:**
- `test_annotation_persistence.py` - Annotation CRUD
- `test_celery_state_transitions.py` - Celery task states (stubbed)
- `test_sigma_save_workflow.py` - SIGMA generation → validation → save
- `test_rss_ingestion_persistence.py` - RSS → article persistence
- `test_eval_execution.py` - Eval run → metrics (stubbed)
- `test_agent_config_lifecycle.py` - Agent config lifecycle

**Documentation Tests:**
- `test_mkdocs_build.py` - MkDocs build sanity

### Phase 4: Frontend Tests ✅

**Playwright UI Tests (Python):**
- `test_navigation_routing.py` - Navigation/routing
- `test_sigma_editor_validation.py` - SIGMA editor validation + save
- `test_annotation_ui_persistence.py` - Annotation UI state
- `test_eval_ui_rendering.py` - Eval metrics rendering
- `test_modal_interactions.py` - Modal behavior
- `test_collapsible_panels.py` - Collapsible panel behavior

**Playwright E2E Tests (TypeScript):**
- `workflow_full.spec.ts` - Full workflow (ingest → extract → review → generate sigma → validate → save)
- `eval_workflow.spec.ts` - Eval workflow (run eval → view results → compare snapshot)

**Note:** Existing 29 Playwright tests reclassified as "UI smoke" (no changes to test files).

## Rationale for Each Test

### Backend Tests

**Similarity Search Deterministic:**
- **Risk**: Scoring changes could break ordering, causing duplicate rules
- **Approach**: Golden files with relative ordering and score ranges

**SIGMA Validator Round-trip:**
- **Risk**: YAML parsing/serialization bugs could corrupt rules
- **Approach**: Load → validate → dump → reload → compare

**Annotation Persistence:**
- **Risk**: Training data loss or corruption
- **Approach**: CRUD operations with database verification

**RSS Ingestion Persistence:**
- **Risk**: Data ingestion failures could lose articles
- **Approach**: End-to-end RSS → database verification

### Frontend Tests

**Navigation/Routing:**
- **Risk**: Broken navigation breaks user workflows
- **Approach**: Verify page transitions and URL changes

**SIGMA Editor Validation:**
- **Risk**: Invalid rules could be saved, breaking downstream systems
- **Approach**: Verify validation UI and save workflow

**Collapsible Panels:**
- **Risk**: UI regressions violate AGENTS.md accessibility rules
- **Approach**: Verify header click, caret state, keyboard support

## Test Execution

### Running Tests

```bash
# Start test containers
make test-up

# Run all tests
make test

# Run specific test categories
pytest tests/services/ -v  # Stateless backend tests
pytest tests/integration/ -v  # Stateful backend tests
pytest tests/ui/ -v  # Frontend UI tests
npm test -- tests/playwright/workflow_full.spec.ts  # E2E tests

# Tear down containers
make test-down
```

### Test Markers

- `@pytest.mark.unit` - Unit tests (stateless)
- `@pytest.mark.integration` - Integration tests (stateful)
- `@pytest.mark.ui` - UI tests
- `@pytest.mark.e2e` - E2E tests
- `@pytest.mark.quarantine` - Quarantined tests
- `@pytest.mark.ui_smoke` - UI smoke tests (reclassified Playwright)

## Success Criteria

- ✅ ≥10 frontend tests passing
- ✅ ≥10 backend tests passing
- ✅ ≤2 new Playwright E2E tests (existing 29 reclassified as "UI smoke")
- ✅ MkDocs build sanity test passing
- ✅ All stateful tests use test containers
- ✅ Database safety guards prevent production DB access
- ✅ API key safety guards prevent accidental cloud LLM usage
- ✅ Fixtures directory populated with reusable test data
- ✅ Factories available for common test objects
- ✅ Test execution time <10 minutes for full suite
- ✅ No flaky tests (deterministic execution)


---

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
python3 run_tests.py smoke
python3 scripts/run_tests_by_group.py --group smoke
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
python3 run_tests.py unit
python3 scripts/run_tests_by_group.py --group unit
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
python3 run_tests.py api
python3 scripts/run_tests_by_group.py --group api
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
python3 run_tests.py integration
python3 scripts/run_tests_by_group.py --group integration
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
python3 run_tests.py ui
python3 scripts/run_tests_by_group.py --group ui
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
python3 run_tests.py e2e
python3 scripts/run_tests_by_group.py --group e2e
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
python3 run_tests.py performance
python3 scripts/run_tests_by_group.py --group performance
```

---

### 8. ai

**Description**: AI-specific tests  
**Duration**: ~3 minutes  
**Dependencies**: AI services (can be mocked)  
**Test Path**: Specific files + `ai` marker  
**Integration**: ✅ Fully integrated via `run_tests.py`

**Purpose**: Test AI assistant functionality, LLM integrations, and AI workflows (includes legacy AI Assistant test coverage).

**Test Files**:
- `tests/ui/test_ai_assistant_ui.py` (deprecated/disabled with AI Assistant removal)
- `tests/integration/test_ai_*.py`
- Tests marked with `@pytest.mark.ai`

**Run Command**:
```bash
python3 run_tests.py ai
python3 scripts/run_tests_by_group.py --group ai
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
python3 scripts/run_tests_by_group.py

# Run specific group
python3 scripts/run_tests_by_group.py --group smoke

# Run multiple groups
python3 scripts/run_tests_by_group.py --group ui --group e2e

# Stop at first failure
python3 scripts/run_tests_by_group.py --stop-on-failure

# Verbose output
python3 scripts/run_tests_by_group.py --verbose
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

---

# Test Data Safety Audit Report

**Date**: 2025-11-24  
**Purpose**: Verify all tests are non-impactful to system integrity (database data and app configs)

## Executive Summary

**Status**: ✅ **ALL TESTS ARE SAFE FOR PRODUCTION DATA**

All tests have been audited and verified to be non-impactful to production database data and application configuration files.

## Protection Mechanisms

### 1. Database Isolation

**Test Database Usage:**
- ✅ Integration tests use `cti_scraper_test` database (not production `cti_scraper`)
- ✅ Default connection string: `postgresql+asyncpg://cti_user:cti_pass@localhost:5432/cti_scraper_test`
- ✅ Environment variable `DATABASE_URL` can override, but defaults to test DB

**Transaction Rollback:**
- ✅ Integration tests use `test_database_with_rollback` fixture
- ✅ Fixture location: `tests/integration/conftest.py:55`
- ✅ All database changes are rolled back after each test
- ✅ Prevents any data persistence between tests

**Verification:**
```python
# tests/integration/conftest.py:62
db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://cti_user:cti_pass@localhost:5432/cti_scraper_test")

# Transaction rollback ensures isolation
async with async_session() as session:
    await session.begin()
    yield session
    await session.rollback()  # All changes rolled back
```

### 2. Configuration File Protection

**Read-Only Access:**
- ✅ Tests only **read** from `config/sources.yaml` (no writes)
- ✅ Example: `tests/integration/test_lightweight_integration.py:314` reads config but doesn't modify it
- ✅ No tests write to `config/sources.yaml` or other config files

**Verification:**
- Searched for: `config/sources.yaml`, `sources.yaml`, `write.*config`, `open.*config.*w`
- Result: Only read operations found, no write operations

### 3. ML Model Protection

**Disabled Tests:**
- ✅ All ML model retraining tests are **disabled** per `TEST_MUTATION_AUDIT.md`
- ✅ Tests marked `prod_data`/`production_data` are **excluded by default** in `run_tests.py:513`
- ✅ No tests modify production ML models

**Disabled Test List:**
1. `test_retraining_creates_new_version()` - DISABLED
2. `test_model_retraining_trigger` - SKIPPED
3. `test_new_model_version_creation` - SKIPPED
4. `test_model_retrain_button` - SKIPPED
5. `test_model_retrain_endpoint()` - DISABLED

**Verification:**
- Searched for: `.save()`, `.write()`, `model.*train`, `retrain`, `save_model`
- Result: Only references in disabled/skipped tests

### 4. UI Tests Safety

**Read-Only Operations:**
- ✅ UI tests connect to `localhost:8001` (application instance)
- ✅ UI tests only interact with UI elements (clicks, form fills, navigation)
- ✅ No database writes from UI tests
- ✅ No config file modifications from UI tests

**Verification:**
- All UI tests use Playwright to interact with web interface
- No direct database connections in UI tests
- No file system writes in UI tests

### 5. Unit Tests Safety

**Mocked Dependencies:**
- ✅ Unit tests use mocks for all external dependencies
- ✅ No real database access in unit tests
- ✅ No config file access in unit tests
- ✅ No ML model access in unit tests

**Verification:**
- Unit tests use `unittest.mock` extensively
- All database operations are mocked
- All file operations are mocked

## Test Categories Safety Status

| Category | Database Access | Config Access | ML Model Access | Status |
|----------|----------------|--------------|-----------------|--------|
| **Smoke** | None | None | None | ✅ Safe |
| **Unit** | Mocked | Mocked | Mocked | ✅ Safe |
| **API** | Test DB | Read-only | None | ✅ Safe |
| **Integration** | Test DB + Rollback | Read-only | Disabled | ✅ Safe |
| **UI** | None (via API) | None | None | ✅ Safe |
| **E2E** | Test DB | Read-only | Disabled | ✅ Safe |
| **Performance** | Test DB | Read-only | None | ✅ Safe |
| **AI** | Test DB | Read-only | Mocked | ✅ Safe |

## Default Exclusions

**run_tests.py Protection:**
```python
# run_tests.py:513
default_excludes = ["infrastructure", "prod_data", "production_data"]
```

Tests marked with these markers are **automatically excluded** unless explicitly included.

## Verification Commands

**Check Database Connection:**
```bash
# Verify test database is used
grep -r "cti_scraper_test" tests/
```

**Check Config File Writes:**
```bash
# Verify no config writes
grep -r "write.*config\|open.*config.*w" tests/
```

**Check ML Model Writes:**
```bash
# Verify no model writes
grep -r "\.save()\|\.write()\|model.*train\|retrain" tests/
```

## Recommendations

### Current State: ✅ SAFE

All tests are currently safe and non-impactful. The following mechanisms ensure safety:

1. **Test Database Isolation**: All integration tests use `cti_scraper_test`
2. **Transaction Rollback**: All database changes are rolled back
3. **Config Read-Only**: Tests only read config files, never write
4. **ML Model Protection**: All retraining tests are disabled
5. **Marker Exclusions**: Production data tests are excluded by default

### Future Considerations

1. **Add Test Isolation Verification**: Create a test that verifies rollback actually prevents persistence
2. **Add Config Write Detection**: Add pre-commit hook to detect config file writes in tests
3. **Add Database Name Validation**: Add check to ensure tests don't use production database name
4. **Document Test Database Setup**: Ensure test database is clearly documented in setup guides

## Conclusion

**All tests are verified to be non-impactful to production data and configuration files.**

The combination of:
- Test database isolation (`cti_scraper_test`)
- Transaction rollback fixtures
- Read-only config access
- Disabled ML model tests
- Default marker exclusions

...ensures complete safety for production systems.



---

_Last updated: February 2025_
