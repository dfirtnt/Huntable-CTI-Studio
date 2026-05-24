---
title: Smoke Test Workflow Trigger Pollutes Live Database via Real Article Lookup
date: 2026-05-24
category: test-failures
module: testing
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "Workflow execution list showed 'Intelligence Center' article with completion reason non_windows_os_detected after every smoke test run"
  - "TestCriticalAPIs::test_workflow_trigger_smoke was creating real workflow executions in the dev/production database on each run"
  - "First article returned by GET /api/articles?limit=1 was consistently consumed by the test, accumulating duplicate executions silently"
root_cause: test_isolation
resolution_type: test_fix
tags:
  - smoke-test
  - test-isolation
  - workflow-trigger
  - database-pollution
  - sentinel-id
  - api-testing
---

# Smoke Test Workflow Trigger Pollutes Live Database via Real Article Lookup

## Problem

`TestCriticalAPIs::test_workflow_trigger_smoke` in `tests/api/test_endpoints.py` was fetching the first real article from the live database and triggering the workflow endpoint against it on every test run, creating spurious workflow execution records in the dev/production database as a side effect of normal smoke suite execution.

## Symptoms

- The article "Intelligence Center" accumulated repeated workflow executions with completion reason `non_windows_os_detected` in the `/workflow#executions` UI
- Running the test suite caused observable database writes — new `AgenticWorkflowExecutionTable` records created on each CI or local smoke run
- The contamination was silent: the test passed cleanly (HTTP 200 was explicitly listed as an accepted status), leaving no indication anything was wrong

## What Didn't Work

- Searching all source files for the string "Intelligence Center" returned no results — the article title is a live database record, not a hardcoded fixture, so code search was a dead end
- Inspecting workflow business logic and Celery task handlers found no rogue scheduled calls; the trigger was always coming from the test layer, not application code

## Solution

**Before** — test fetches a real article ID from the live DB and triggers against it:

```python
async def test_workflow_trigger_smoke(self, async_client: httpx.AsyncClient):
    """Test workflow trigger endpoint accepts requests (doesn't wait for completion)."""
    articles_response = await async_client.get("/api/articles?limit=1")
    article_id = None

    if articles_response.status_code == 200:
        articles_data = articles_response.json()
        if articles_data.get("articles"):
            article_id = articles_data["articles"][0]["id"]

    if not article_id:
        article_id = 999999  # Non-existent article ID

    response = await async_client.post(f"/api/workflow/articles/{article_id}/trigger")

    # Accept 200 (success), 400 (validation/duplicate), 404 (article not found), or 500
    assert response.status_code in [200, 400, 404, 500], f"Unexpected status {response.status_code}"

    if response.status_code == 200:
        data = response.json()
        assert "execution_id" in data or "message" in data
    elif response.status_code in [400, 404]:
        data = response.json()
        assert "detail" in data
```

**After** — test uses a sentinel ID that cannot match any real article:

```python
async def test_workflow_trigger_smoke(self, async_client: httpx.AsyncClient):
    """Test workflow trigger endpoint is routable (uses nonexistent ID to avoid real side effects)."""
    # Use a nonexistent article ID — goal is only to confirm the endpoint exists (not 405).
    # Grabbing a real article and triggering it creates spurious workflow executions in the DB.
    response = await async_client.post("/api/workflow/articles/999999/trigger")

    # 404 proves the route exists; 400 and 500 are also acceptable (e.g. DB unavailable).
    assert response.status_code in [400, 404, 500], f"Unexpected status {response.status_code}"
```

**File:** `tests/api/test_endpoints.py`, class `TestCriticalAPIs`

## Why This Works

The test's actual goal was only to confirm the endpoint is routable — that a POST to `/api/workflow/articles/{id}/trigger` returns something other than HTTP 405 (Method Not Allowed). A nonexistent article ID (999999) satisfies that goal: the router still resolves the route and the handler runs, returning 404. No article is loaded, no `AgenticWorkflowExecutionTable` record is created, and the database is untouched.

The original code had two compounding mistakes:

1. **It resolved a real article ID from the live database.** `GET /api/articles?limit=1` returns the first production-seeded row, coupling test behavior to whatever article happens to sort first.
2. **It explicitly listed HTTP 200 as an accepted status code.** This meant the test was content to let the full workflow trigger execute and commit to the database. The fallback to `999999` only applied when the articles endpoint itself was unavailable — in normal operation the real article was always used and the full trigger ran.

## Prevention

- **Smoke tests that only verify routing must never use real resource IDs.** If the stated goal is "endpoint exists and responds," a sentinel or out-of-range ID is always sufficient. Reserve real IDs for integration tests that explicitly own fixture creation and teardown.

- **Remove HTTP 200 from the accepted-status list** of any test whose docstring says it is not testing successful execution. Accepting 200 silently opts the test into real side effects.

- **Treat `GET /api/<collection>?limit=1` inside a test as a smell.** Querying production-seeded data to drive a test couples test behavior to database state and enables unintended writes. Use factories, fixtures, or fixed sentinel values instead.

- **Audit other tests in the same file.** Scan `tests/api/test_endpoints.py` and `tests/api/test_workflow_config_api.py` for other smoke tests that fetch real resource IDs before posting to mutation endpoints. The pattern `articles_data["articles"][0]["id"]` followed by a non-read HTTP verb is the tell.

## Related Issues

- `docs/solutions/test-failures/model-rollback-422-guard-bypassed-by-mock-2026-05-21.md` — same `root_cause: test_isolation`, different mechanism (mock boundary mismatch rather than live DB query in a smoke test)
