# Testing

## Test Pyramid

```text
        /\
       /E2E\        Full analyst workflows
      /------\
     /Integration\  Cross-component, stateful
    /------------\
   /    Unit      \  Pure functions, stateless
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
| Services | `postgres_test` (port 5433), `redis_test` (port 6380) — no test web container |
| Volumes | None — data exists only in container filesystem |
| Network | Isolated `test_network` |

Runs that collect `tests/api/` get `USE_ASGI_CLIENT=1` and exercise the app
in-process against `TEST_DATABASE_URL` instead of a running web container.

**Lifecycle:**
```bash
make test-up        # Start containers
make test           # Run tests
make test-down      # Tear down
```

`run_tests.py` auto-starts `cti_postgres_test` and `cti_redis_test` when
running `api`, `ui` (including `ui-smoke`, `ui-fast`, `ui-full`), `integration`,
`e2e`, `all-no-ui`, `all`, or `coverage`.

## Fixture Strategy

All fixtures in `tests/fixtures/`:

```text
tests/fixtures/
├── rss/          # RSS and Atom feed samples
├── html/         # HTML page samples
├── sigma/        # Sigma YAML rules (valid, invalid, round-trip)
├── similarity/   # Similarity search inputs/outputs (golden files)
├── ocr/          # OCR sample images
└── workflow/     # Workflow config JSON samples
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
**Path:** `tests/`, `-m smoke`  
Quick health check — verifies critical endpoints and basic functionality.

### unit
**Command:** `python3 run_tests.py unit`  
**Duration:** ~1 minute  
**Path:** `tests/` with marker exclusion (no smoke/integration/api/ui/e2e/performance)  
Individual components in isolation with mocked dependencies. Covers:
`tests/a11y/`, `tests/cli/`, `tests/config/`, `tests/core/`, `tests/database/`,
`tests/docs/`, `tests/scripts/`, `tests/services/`, `tests/sigma_atom_similarity/`,
`tests/templates/`, `tests/utils/`, `tests/worker/`, `tests/workflows/`,
`tests/unit/`, `tests/quality/`

### api
**Command:** `python3 run_tests.py api`  
**Duration:** ~2 minutes  
**Path:** `tests/api/`  
REST API endpoints and responses. The canonical runner uses the in-process ASGI
app against the isolated test database. Tests that create Sigma queue rows or
workflow-config versions use snapshot/restore fixtures so reused test containers
do not accumulate test artifacts.

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
   Runs with `pytest-xdist -n 4` by default (`-n 2` for `ui-smoke`) when the
   xdist plugin is installed; use `--serial` to disable. Bulk of wall time.
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

Excluding them is not required for safety. Section 2 protects the shared config
in two layers regardless: `globalTeardown` restores a pre-run baseline however
the run ends, and the next run's `globalSetup` heals known corruption before it
snapshots, so damage is bounded to at most one run even if the Playwright
process is killed outright. See
[web-app-testing.md](web-app-testing.md#shared-workflow-config-how-the-suite-avoids-damaging-it)
before adding a spec that writes workflow config.

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
**Path:** `tests/integration/test_ai_cross_model_integration.py` (no marker filter applied)  
AI/LLM integration tests. Require secrets; run only in scheduled/manual
workflows if at all.

### Other test types

`run_tests.py` supports marker-only categories and additional UI tiers not
detailed above. Run `python3 run_tests.py --help` for the full list.

| Type | Path / marker | Notes |
|---|---|---|
| `ui-smoke` | `tests/ui/`, `-m "ui_smoke or smoke"` | Tier 1, stateless, pytest only (~2m) |
| `ui-fast` | `tests/ui/`, `-m ui`, excludes `slow` | Tier 3, full UI minus `@slow` (~15m) |
| `ui-full` | `tests/ui/`, `-m ui`, includes `slow` | Tier 4, everything (~45m) |
| `all-no-ui` | `tests/` minus `tests/ui/`, `tests/e2e/` | Full suite excluding UI + Playwright JS |
| `regression` | `tests/`, `-m regression` | Regression tests for previously fixed behavior |
| `contract` | `tests/`, `-m contract` | API/schema contract tests |
| `security` | `tests/`, `-m security` | Security hardening/abuse-case tests; also uses `USE_ASGI_CLIENT=1` |
| `a11y` | `tests/`, `-m a11y` | Accessibility baseline tests |
| `ai-ui` | `tests/ui/` | AI-related UI tests |
| `ai-integration` | `tests/integration/test_ai_cross_model_integration.py`, `-m integration` | Same file as `ai`, with the `integration` marker applied |
| `coverage` | `tests/`, `--cov=src` | Full suite with coverage report |

## Test Directory Mapping

| Directory | Group |
|---|---|
| `tests/smoke/` | smoke |
| `tests/api/` | api |
| `tests/integration/` | integration |
| `tests/ui/` | ui |
| `tests/e2e/`, `tests/playwright/` | e2e / ui |
| `tests/a11y/`, `tests/cli/`, `tests/config/`, `tests/core/`, `tests/database/`, `tests/docs/`, `tests/scripts/`, `tests/services/`, `tests/sigma_atom_similarity/`, `tests/templates/`, `tests/utils/`, `tests/worker/`, `tests/workflows/` | unit |
| `tests/unit/` | unit (MCP tools, model versioning/rollback) |
| `tests/quality/` | unit (regression/contract/security/a11y markers) |

## CI Coverage

| CI Job | Command | Status |
|---|---|---|
| smoke | `python3 run_tests.py smoke` | Running |
| unit | `python3 run_tests.py unit` | Running |
| api | `python3 run_tests.py api` | Running |
| integration | `python3 run_tests.py integration` | Running |
| ui | `python3 run_tests.py ui` | Running |
| playwright | `npx playwright test -c tests/playwright.config.ts` | Running |

**CI workflow files:**
- `.github/workflows/tests.yml` — smoke, unit, api, integration, ui
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
| API | Test DB | Snapshot/restore | None | Yes |
| Integration | Test DB + Rollback | Read-only | Disabled | Yes |
| UI | None (via API) | None | None | Yes |
| E2E | Test DB | Read-only | Disabled | Yes |
| Performance | Test DB | Read-only | None | Yes |
| AI | Test DB | Read-only | Mocked | Yes |

**Safety mechanisms:**
- Integration tests use `cti_scraper_test` with transaction rollback
- API tests that mutate the Sigma queue or workflow config restore the affected
  tables to their pre-test row set, including when a test fails
- Node.js Playwright specs that mutate the shared workflow config are backstopped
  by `globalTeardown` (restores a baseline whatever kills the run) plus
  heal-on-next-`globalSetup`, since per-spec `finally` blocks need a live `page`
  and do not fire when a worker is killed
- Config files are read-only in tests
- ML retraining tests are disabled
- `default_excludes` in `run_tests.py` automatically excludes `infrastructure`,
  `prod_data`, and `production_data` markers

## Out of Scope

- Analytics pages (`/analytics`) — likely to be deprecated
- Concurrent multi-user session tests — local-first design.
  Authentication/authorization itself is in scope and covered by
  `tests/api/test_route_authorization.py`, `tests/api/test_csrf.py`,
  `tests/api/test_audit_*.py`, and `tests/unit/test_security_middleware.py`;
  see [Authentication](../guides/authentication.md).

_Last updated: 2026-08-13_
_Last reviewed: 2026-09-01_
