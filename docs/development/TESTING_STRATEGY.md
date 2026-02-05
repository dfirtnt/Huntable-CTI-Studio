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
