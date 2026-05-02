# Testing

## Test Pyramid

```
        /\
       /E2E\        <=2 Playwright tests (full analyst workflows)
      /------\
     /Integration\  ~20 tests (cross-component, stateful)
    /------------\
   /    Unit      \  ~80 tests (pure functions, stateless)
  /----------------\
```

## Test Categories

### Stateless Tests (no containers)

Do not require database connections or containers:

- Pure frontend tests (Jinja templates + Tailwind + vanilla JS behavior)
- Backend unit tests without DB connections
- Similarity search with in-memory fixtures
- YAML parsing, linting, round-trip logic
- Utility functions, selectors, scoring logic

No `APP_ENV=test` or `TEST_DATABASE_URL` required. Can run in parallel.

### Stateful Tests (containers required)

- Database writes (articles, annotations, sigma rules)
- Celery task execution
- Integration tests with persistence
- E2E workflows

Require `APP_ENV=test`, `TEST_DATABASE_URL` (never `DATABASE_URL`), and
test containers running (`make test-up`). Database name must contain "test".

## Database Safety

`assert_test_environment()` in `tests/utils/test_environment.py` enforces:

- `APP_ENV=test` is set
- `TEST_DATABASE_URL` is set (no fallback to `DATABASE_URL`)
- Database name contains "test"
- Production database (`cti_scraper` without "test") is never used

Invoked at pytest bootstrap (`pytest_configure()`) and in Celery app init when
`APP_ENV=test`. Fails fast with clear error messages.

## API Key Safety

Cloud LLM keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHATGPT_API_KEY`) are
**never available to the test process by default**:

- `run_tests.py` removes these keys from the process environment before running
  any tests. No test run can hit commercial cloud APIs.
- If `ALLOW_CLOUD_LLM_IN_TESTS=true` is set, keys are not stripped and tests
  proceed with a warning.
- Local LLM keys (`LMSTUDIO_API_URL`) are allowed by default.

## Test Containers

| Setting | Value |
|---|---|
| File | `docker-compose.test.yml` |
| Services | `postgres_test` (port 5433), `redis_test` (port 6380), `web_test` (port 8002) |
| Volumes | None — data exists only in container filesystem |
| Network | Isolated `test_network` |

**Lifecycle:**
```bash
make test-up        # Start containers
make test           # Run tests
make test-down      # Tear down
```

`run_tests.py` auto-starts `cti_postgres_test` and `cti_redis_test` when
running `api`, `ui`, `integration`, `e2e`, or `all`.

## Fixture Strategy

All fixtures in `tests/fixtures/`:

```
tests/fixtures/
├── rss/          # RSS and Atom feed samples
├── html/         # HTML page samples
├── sigma/        # Sigma YAML rules (valid, invalid, round-trip)
├── similarity/   # Similarity search inputs/outputs (golden files)
└── articles/     # Article JSON samples
```

**Golden files** (in `similarity/`) use relative ordering ("A > B > C") and
score ranges (min/max), not exact floats, to avoid brittleness.

**Factories** in `tests/factories/`:
`ArticleFactory`, `AnnotationFactory`, `AgentConfigFactory`, `EvalFactory`,
`SigmaFactory`

## Test Groups

### smoke
**Command:** `python3 run_tests.py smoke`  
**Duration:** ~30 seconds  
**Path:** `-m smoke`  
Quick health check — verifies critical endpoints and basic functionality.

### unit
**Command:** `python3 run_tests.py unit`  
**Duration:** ~1 minute  
**Path:** `tests/` with marker exclusion (no smoke/integration/api/ui/e2e)  
Individual components in isolation with mocked dependencies. Covers:
`tests/cli/`, `tests/config/`, `tests/core/`, `tests/database/`, `tests/docs/`,
`tests/services/`, `tests/utils/`, `tests/worker/`, `tests/workflows/`,
`tests/unit/`, `tests/quality/`

### api
**Command:** `python3 run_tests.py api`  
**Duration:** ~2 minutes  
**Path:** `tests/api/`  
REST API endpoints and responses. Requires application running.

### integration
**Command:** `python3 run_tests.py integration`  
**Duration:** ~3 minutes  
**Path:** `tests/integration/` with `integration` marker  
Full-stack cross-component tests (test DB + Redis + optionally web). Use
`@pytest.mark.integration` for full-stack confidence. Tests marked
`@pytest.mark.integration_light` (mocked HTTP/DB) are not selected by this
command. See `tests/SKIPPED_TESTS.md` for currently skipped integration tests.

### ui
**Command:** `python3 run_tests.py ui`  
**Duration:** ~38 minutes (Section 1, pytest) + ~5 minutes (Section 2, Node.js)  
**Path:** `tests/ui/` (pytest) and `tests/playwright/*.spec.ts` (Node.js)

Two independent sections run in sequence:

1. **Section 1 — pytest** (`tests/ui/`, Python Playwright via `pytest-playwright`).
   Serial by default. Bulk of wall time.
2. **Section 2 — Node.js Playwright** (`tests/playwright/*.spec.ts`,
   `@playwright/test` runner, `workers: 4` locally).

```bash
python3 run_tests.py ui                           # Both sections
python3 run_tests.py ui --skip-playwright-js      # Section 1 only
python3 run_tests.py ui --playwright-only         # Section 2 only
python3 run_tests.py ui --playwright-last-failed  # Rerun Section 2 failures
```

Use `--parallel` for `pytest-xdist -n auto` on Section 1 (may flake against
a single live app). To exclude config-mutating tests:

```bash
python3 run_tests.py ui --skip-playwright-js --exclude-markers agent_config_mutation
```

This excludes `@pytest.mark.agent_config_mutation` tests (run evaluation, save
settings, save workflow config) from pytest and sets
`CTI_EXCLUDE_AGENT_CONFIG_TESTS=1` for the Node.js runner.

### e2e
**Command:** `python3 run_tests.py e2e`  
**Duration:** ~3 minutes  
**Path:** `tests/e2e/`, `tests/playwright/`  
Complete user workflows end-to-end.

### performance
**Command:** `python3 run_tests.py performance`  
**Path:** Tests marked `@pytest.mark.performance`  
Requires `PERFORMANCE_TEST_ENABLED=true`. Not run in standard CI.

### ai
**Command:** `python3 run_tests.py ai`  
**Path:** `tests/integration/test_ai_*.py` and `@pytest.mark.ai`  
AI/LLM integration tests. Require secrets; run only in scheduled/manual
workflows if at all.

## Test Directory Mapping

| Directory | Group |
|---|---|
| `tests/smoke/` | smoke |
| `tests/api/` | api |
| `tests/integration/` | integration |
| `tests/ui/` | ui |
| `tests/e2e/`, `tests/playwright/` | e2e / ui |
| `tests/cli/`, `tests/core/`, `tests/services/`, `tests/utils/`, `tests/worker/`, `tests/workflows/` | unit |
| `tests/unit/` | unit (MCP tools, model versioning/rollback) |
| `tests/quality/` | unit (regression/contract/security/a11y markers) |

## CI Coverage

| CI Job | Command | Status |
|---|---|---|
| smoke | `python3 run_tests.py smoke` | Running |
| unit | `python3 run_tests.py unit` | Running |
| api | `python3 run_tests.py api` | Running |
| integration | `python3 run_tests.py integration` | Running |
| playwright | `npx playwright test` | Running |

**CI workflow files:**
- `.github/workflows/tests.yml` — smoke, unit, api, integration
- `.github/workflows/playwright.yml` — Playwright E2E/UI tests

### What NOT to run in CI

| Group | Reason |
|---|---|
| `agent_config_mutation` | Mutates live config; exclude with `--exclude-markers agent_config_mutation` + `CTI_EXCLUDE_AGENT_CONFIG_TESTS=1` |
| `performance` | Requires `PERFORMANCE_TEST_ENABLED=true` |
| `prod_smoke` | Reads non-test `DATABASE_URL`; requires `ALLOW_PROD_SMOKE=1 -m prod_smoke` |
| `ai` / cloud LLM | Require secrets and cost money |
| Quarantined | Already in `tests/SKIPPED_TESTS.md` |

## Determinism Rules

- Assert relative ordering ("A > B > C"), not exact scores
- Use score ranges (min/max), not exact floats
- Use seeded random number generators
- No network calls in unit/integration tests
- Use fixtures instead of live data
- **Never call real cloud LLM providers in tests.** Always mock `request_chat`
  or the equivalent boundary. LM Studio (local) is allowed.

## Quarantine Tracking

Quarantined tests (`@pytest.mark.quarantine`) are tracked in
`tests/SKIPPED_TESTS.md` with test name, reason, owner, created date, and
intended fix. CI reports quarantine counts to prevent skip creep.

## Data Safety

All tests are non-impactful to production data and configuration:

| Category | DB Access | Config Access | ML Models | Safe? |
|---|---|---|---|---|
| Smoke | None | None | None | Yes |
| Unit | Mocked | Mocked | Mocked | Yes |
| API | Test DB | Read-only | None | Yes |
| Integration | Test DB + Rollback | Read-only | Disabled | Yes |
| UI | None (via API) | None | None | Yes |
| E2E | Test DB | Read-only | Disabled | Yes |
| Performance | Test DB | Read-only | None | Yes |
| AI | Test DB | Read-only | Mocked | Yes |

**Safety mechanisms:**
- Integration tests use `cti_scraper_test` with transaction rollback
- Config files are read-only in tests
- ML retraining tests are disabled
- `default_excludes` in `run_tests.py` automatically excludes `infrastructure`,
  `prod_data`, and `production_data` markers

## Out of Scope

- Analytics pages (`/analytics`) — likely to be deprecated
- Authentication/authorization — single-user application
- Multi-user tests — local-first, single-user design

_Last updated: 2026-05-01_
