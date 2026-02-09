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
