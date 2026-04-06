---
name: codebase-test-trueup
description: "Audit test coverage gaps and generate unit tests to close them. Use when the user says \"test trueup\", \"coverage gaps\", \"test coverage audit\", \"fill coverage\", \"write missing tests\", \"backfill tests\", \"scope tests\", \"test what I changed\", or any request to identify and fill test gaps. Three modes: audit (report only), fill (generate tests for worst gaps), scope (cover changes from current session)."
---

# Codebase Test True-Up

Systematically identify and close test coverage gaps. The goal is **raising unit-level coverage on the code that matters most** — recently changed, high-risk, or session-relevant modules — without generating low-value or redundant tests.

## Philosophy

Coverage is a proxy for confidence. Chasing 100% is wasteful; ignoring gaps is reckless. This skill targets the intersection of **low coverage** and **high change frequency** — the code most likely to regress. Tests generated here must be stateless unit tests that run without Docker, databases, or network access.

## Scope boundaries

**In scope:** Source files under `src/` that can be meaningfully unit-tested with mocks. Test output lands in the appropriate `tests/` subdirectory following existing conventions.

**Off limits:**
- `AGENTS.md`, `CLAUDE.md` — never modify
- Integration, API, UI, or E2E tests — those require containers and belong to dedicated workflows
- Refactoring source code to improve testability — tests adapt to the code, not the other way around
- Deleting or modifying existing tests — this skill only adds

---

## Bugfix Detection & Regression Tests (applies to all modes)

Every mode in this skill must actively look for bugfixes and evaluate whether regression tests exist. A bugfix without a regression test is a bug that can come back.

### How to detect bugfixes

Bugfixes surface through multiple signals. Check all of them:

**1. Commit message prefixes (for audit and fill modes):**
```bash
# Conventional-commit prefixes used in this repo:
git log --oneline -50 | grep -E '^\w{8} (fix|security|revert)(\(|:)'
```
The prefixes `fix:`, `fix(scope):`, `security:`, and `revert:` all indicate code that corrected broken behavior.

**2. Session context (for scope mode):**
When working in a chat session, identify bugfixes from:
- The user describing a bug ("X is broken", "Y returns wrong value", "Z crashes when...")
- The user referencing an issue or error report
- Code changes that modify conditional logic, add null checks, fix off-by-ones, correct type handling, or add missing error handling
- Changes described with words like "fix", "patch", "correct", "handle", "prevent", "guard"

**3. Diff patterns (for scope and fill modes):**
These diff shapes strongly suggest a bugfix even without an explicit label:
- Adding/changing a condition in an `if/elif` (correcting a logic error)
- Adding a `try/except` or `except` clause (handling an unhandled exception)
- Changing a comparison operator (`==` to `is`, `>` to `>=`, etc.)
- Adding a `None`/empty check before an operation
- Fixing a string format, key name, or attribute access (typo/naming fix)
- Adding `.strip()`, `.lower()`, type coercion, or encoding handling
- Reverting or replacing a recent change

### Regression test requirements

When a bugfix is detected, a regression test is **mandatory** unless the fix is purely cosmetic (whitespace, comments, log messages). The regression test must:

**A. Reproduce the precondition** — set up the exact state that triggered the bug:
```python
@pytest.mark.regression
def test_fetch_article_403_no_longer_crashes_regression(self):
    """Regression: fetch_article() crashed with unhandled HTTPError when
    the source returned 403. Fixed by adding archive.org fallback.

    Fix: 48b2211e
    Bug: primary fetch raised HTTPError(403) with no fallback path
    """
    # Arrange: mock the primary fetch to return 403
    mock_response = Mock(status_code=403)
    mock_client = AsyncMock()
    mock_client.get.side_effect = HTTPError(response=mock_response)
    ...
```

**B. Assert the fixed behavior** — the assertion must be something that **would have failed before the fix**:
```python
    # Act
    result = await fetch_article(url, client=mock_client)

    # Assert: now falls back to archive instead of crashing
    assert result.source == "archive.org"
    assert result.content is not None
```

**C. Use the `@pytest.mark.regression` marker** — so regression tests can be run as a suite:
```python
@pytest.mark.regression
def test_<function>_<bug_description>_regression(self):
```

**D. Include structured metadata in the docstring:**
```python
"""Regression: <one-line description of the bug>.

Fix: <commit hash or "current session">
Bug: <what went wrong — the triggering condition and incorrect behavior>
"""
```

### Regression audit (runs in all modes)

Before generating any tests, scan for bugfixes that lack regression tests:

```bash
# Get fix/security commits from the last N commits
git log --oneline -50 | grep -E '^\w{8} (fix|security|revert)(\(|:)'

# For each, check the changed files
git show --name-only --pretty=format: <hash> | grep '^src/'

# Search existing tests for a regression test mentioning that hash or the fixed function
grep -r "<hash>" tests/ || grep -r "<function_name>.*regression" tests/
```

Report any bugfixes missing regression tests as **high priority** items — higher than general coverage gaps.

### Regression priority in each mode

| Mode | Regression behavior |
|------|-------------------|
| **Audit** | Report section "Bugfixes Missing Regression Tests" with commit hash, changed files, and whether a regression test exists. This section appears FIRST in the report, before general coverage gaps. |
| **Fill** | Regression tests for unprotected bugfixes are generated BEFORE general coverage tests. They are the highest-priority fill targets regardless of coverage %. |
| **Scope** | If the session contains a bugfix, the regression test is the FIRST test generated. The agent should explicitly confirm with the user: "This looks like a bugfix for X. I'll write a regression test that reproduces the original failure. Does this match the bug?" |

---

## Mode 1: Audit

**Trigger:** "test trueup audit", "coverage gaps", "show me coverage", "what's untested"

Report-only. No files are created or modified.

### Step 1: Run coverage

```bash
python3 run_tests.py unit --coverage 2>&1
```

Parse the coverage table from stdout. Extract per-file coverage percentages for all files under `src/`.

### Step 2: Identify recently changed files

```bash
# Files changed in the last 30 commits
git log --name-only --pretty=format: -30 -- 'src/**/*.py' | sort -u | grep -v '^$'
```

### Step 3: Cross-reference and prioritize

Build a priority list by combining:
- **Coverage %** — lower is higher priority
- **Recent change frequency** — more changes = higher priority
- **Module risk tier** (use this weighting):

| Tier | Modules | Why |
|------|---------|-----|
| Critical | `src/workflows/`, `src/services/`, `src/core/` | Business logic, data transformation, ingestion |
| High | `src/database/`, `src/config/`, `src/worker/` | Persistence contracts, configuration, scheduling |
| Medium | `src/web/routes/`, `src/prompts/` | Request handling, prompt construction |
| Low | `src/web/templates/`, `src/utils/` | Presentation, utilities (often already tested) |

### Step 4: Check for existing test files

For each priority source file, check whether a corresponding test file exists:

```bash
# For src/services/foo_service.py, check:
# - tests/services/test_foo_service.py
# - tests/unit/test_foo_service.py
# - tests/test_foo_service.py
```

### Step 5: Regression audit

Run the regression detection process described in "Bugfix Detection & Regression Tests" above. For each `fix:`, `security:`, or `revert:` commit in the last 50 commits, check whether a regression test exists that references the commit hash or the fixed function.

### Step 6: Report

Output the regression section **first**, then the coverage table sorted by priority:

```
Test Coverage Audit
===================

BUGFIXES MISSING REGRESSION TESTS (highest priority)
-----------------------------------------------------
Commit    | Message                                          | Changed File(s)                  | Regression Test?
--------- | ------------------------------------------------ | -------------------------------- | ----------------
48b2211e  | fix: RSS scraping fallback, anti-bot FP, ...    | src/core/fetcher.py + 2 more     | MISSING
e679e32a  | fix: replace dead event_ids/registry_keys ...   | src/services/llm_service.py      | MISSING
7fac5e19  | security: fix XSS in executions/diags ...       | src/web/routes/executions.py + 3 | PARTIAL (1 of 4)
...

Unprotected bugfixes: N of M total fix commits

COVERAGE GAPS (sorted by priority)
-----------------------------------
Source File                              | Coverage | Recent Changes | Test File              | Priority
---------------------------------------- | -------- | -------------- | ---------------------- | --------
src/workflows/agentic_workflow.py        |       2% |              5 | (none)                 | CRITICAL
src/worker/celery_app.py                 |      13% |              3 | (none)                 | CRITICAL
src/services/workflow_trigger_service.py |       8% |              2 | tests/services/test_.. | HIGH
src/core/fetcher.py                      |      22% |              4 | tests/test_fetcher..   | HIGH
...

Files with 0% coverage and no test file: N
Files changed recently with <30% coverage: M
Estimated tests needed to reach 40% baseline: ~K
```

Do NOT generate tests in audit mode. Present the report and stop.

---

## Mode 2: Fill

**Trigger:** "test trueup fill", "fill coverage", "write missing tests", "backfill tests"

Generate unit tests for the highest-priority gaps identified by the audit.

### Step 1: Run the audit

Execute Mode 1 (Steps 1-5) silently. Use the priority list to select targets.

### Step 2: Select targets

**Regression tests come first.** If the audit found bugfixes missing regression tests, those are the first fill targets — they take priority over general coverage gaps regardless of coverage %. Then pick the top 3-5 source files by coverage priority. Ask the user for confirmation:

```
Coverage fill targets:

REGRESSION (auto-selected — bugfixes without regression tests):
  R1. 48b2211e fix: RSS scraping fallback... → src/core/fetcher.py
  R2. e679e32a fix: replace dead event_ids... → src/services/llm_service.py

COVERAGE (top 3 by priority):
  C1. src/services/sigma_generation_service.py — 5% coverage, 3 recent changes
  C2. src/core/fetcher.py — 22% coverage, 4 recent changes (also R1)
  C3. src/config/workflow_config_loader.py — 11% coverage, 2 recent changes

Proceed with these? (or specify different files)
```

### Step 3: Read and understand each target

For each selected source file:

1. **Read the entire source file.** Understand every public function and class.
2. **Read imports** to identify external dependencies that need mocking.
3. **Read any existing test file** for this module — understand what's already covered.
4. **Read `tests/conftest.py`** fixtures and `tests/utils/async_mocks.py` — reuse existing mock infrastructure.

### Step 4: Generate tests

For each target, write a test file following these **mandatory conventions**:

**File placement:**
- If a test file already exists for this module, add tests to it
- If not, create one in the matching `tests/` subdirectory:
  - `src/services/foo.py` -> `tests/services/test_foo.py`
  - `src/core/foo.py` -> `tests/core/test_foo.py`
  - `src/config/foo.py` -> `tests/config/test_foo.py`
  - `src/database/foo.py` -> `tests/database/test_foo.py`
  - `src/workflows/foo.py` -> `tests/workflows/test_foo.py`
  - `src/worker/foo.py` -> `tests/worker/test_foo.py`

**Test structure (mandatory):**
```python
"""Tests for src/<module>/<file>.py."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the class/functions under test
from src.<module>.<file> import <ClassName>, <function_name>

pytestmark = pytest.mark.unit


class Test<ClassName>:
    """Test <ClassName> functionality."""

    # Use class-level fixtures for shared mocks
    @pytest.fixture
    def mock_dependency(self):
        """Create mock <dependency>."""
        mock = AsyncMock()  # or Mock() for sync
        # Configure return values
        return mock

    @pytest.fixture
    def instance(self, mock_dependency):
        """Create <ClassName> with mocked dependencies."""
        with patch("src.<module>.<file>.<import>", mock_dependency):
            return <ClassName>(...)

    def test_<method>_<scenario>(self, instance):
        """<method> should <expected behavior> when <condition>."""
        # Arrange
        ...
        # Act
        result = instance.<method>(...)
        # Assert
        assert result == expected

    @pytest.mark.asyncio
    async def test_<async_method>_<scenario>(self, instance):
        """<async_method> should <expected behavior> when <condition>."""
        result = await instance.<async_method>(...)
        assert result == expected
```

**Mocking rules:**
- Use `unittest.mock` (not pytest-mock)
- Use `AsyncMock()` for all async functions/methods
- Use `Mock()` or `MagicMock()` for sync
- Use `patch()` as context manager or decorator to mock imports
- Reuse fixtures from `tests/conftest.py`: `mock_async_session`, `mock_async_engine`, `mock_async_http_client`
- Reuse `tests/utils/async_mocks.AsyncMockSession` and `setup_async_query_chain` for DB mocking
- Never hit real databases, HTTP endpoints, Redis, or LLM APIs

**What to test (priority order):**
1. Public methods — especially branching logic, error paths, and return value construction
2. Data transformation — input/output mapping correctness
3. Edge cases — empty inputs, None values, missing keys, boundary conditions
4. Error handling — exceptions raised, caught, or propagated correctly

**What NOT to test:**
- Private methods (test them through public API)
- Simple property accessors or trivial getters
- Framework boilerplate (FastAPI route registration, SQLAlchemy model definitions)
- Anything that requires a running database, HTTP server, or external service

### Step 5: Verify

Run the new tests to confirm they pass:

```bash
python3 run_tests.py unit --verbose 2>&1
```

If any test fails:
1. Read the error output
2. Fix the test (not the source code)
3. Re-run until green

### Step 6: Re-measure coverage

```bash
python3 run_tests.py unit --coverage 2>&1
```

### Step 7: Report

```
Test Fill Results
=================

REGRESSION TESTS ADDED
-----------------------
Commit   | Test                                                        | Protects
-------- | ----------------------------------------------------------- | --------
48b2211e | test_rss_scrape_fallback_on_anti_bot_403_regression         | src/core/fetcher.py
48b2211e | test_metadata_preserved_after_fallback_scrape_regression    | src/core/fetcher.py
e679e32a | test_langfuse_wiring_uses_registry_artifacts_regression     | src/services/llm_service.py

COVERAGE TESTS ADDED
---------------------
Module                                   | Before | After  | Tests Added
---------------------------------------- | ------ | ------ | -----------
src/services/sigma_generation_service.py |     5% |    34% | 12
src/core/fetcher.py                      |    22% |    41% | 8 (+2 regression)
src/config/workflow_config_loader.py     |    11% |    28% | 6

Total new tests: 29 (3 regression + 26 coverage)
All passing: YES
```

Do NOT commit. The user manages git workflow separately.

---

## Mode 3: Scope

**Trigger:** "test trueup scope", "scope tests", "test what I changed", "cover my changes", "test this session", or when invoked during/after a feature or fix conversation.

Context-aware mode that focuses on **changes made in the current chat session** (or a user-specified scope) to ensure those specific fixes/features have adequate test coverage.

### Step 1: Determine scope

Identify what changed using multiple signals, in priority order:

**A. Current session context (primary signal):**
Review the current conversation to identify:
- Files that were created or edited during this session
- Functions/classes that were added or modified
- Bug fixes applied (what was the bug? what's the fix?)
- Features added (what's the new behavior?)

**B. Git working tree (secondary signal):**
```bash
# Unstaged + staged changes
git diff --name-only -- 'src/**/*.py'
git diff --cached --name-only -- 'src/**/*.py'

# Untracked source files
git ls-files --others --exclude-standard -- 'src/**/*.py'
```

**C. User-specified scope (override):**
If the user names specific files, modules, or features, use those instead of auto-detection.

```bash
# Example: user says "scope tests for fetcher changes"
# Focus on src/core/fetcher.py and related modules
```

### Step 2: Classify changes as bugfix vs. feature vs. refactor

Before analyzing details, classify each changed file's changes. This classification drives test generation priorities.

**Classification rules:**

| Signal | Classification |
|--------|---------------|
| User said "fix", "bug", "broken", "crash", "wrong", "incorrect" | **Bugfix** |
| Diff adds/changes a conditional, null check, try/except, or comparison operator | **Bugfix** (likely) |
| Diff adds new methods, new parameters, new classes | **Feature** |
| Diff restructures without changing behavior | **Refactor** |
| Commit message starts with `fix:` or `security:` | **Bugfix** (confirmed) |
| Mixed (fix + feature in same file) | Classify each hunk separately |

**If uncertain, ask the user:** "The change to `<function>` looks like it could be a bugfix (adding a null check before the DB call). Was this fixing a bug? If so, what was the failure?" — the answer determines whether a regression test is needed.

### Step 3: Analyze the changes deeply

For each changed file:

1. **Read the full diff** (or the session's edit history) to understand exactly what changed
2. **Identify new code paths** — new branches, new methods, new error handling
3. **Identify changed behavior** — modified return values, altered conditions, new side effects
4. **Map dependencies** — what does this code call? What calls this code?
5. **For bugfixes: reconstruct the failure scenario** — what input/state caused the bug? What happened vs. what should have happened?

Produce a change summary with explicit bugfix callouts:

```
Scope Analysis
==============

src/core/fetcher.py:
  - [BUGFIX] fetch_article() — added archive.org fallback when primary fetch returns 403
    Bug: HTTPError(403) propagated unhandled, crashing the collection pipeline
    Fix: catch 403, fall back to archive.org, return FetchResult with source="archive.org"
    Regression test needed: YES — reproduce 403 from primary, assert fallback fires
  - [FEATURE] lines 142-158 — retry logic with exponential backoff
  - [REFACTOR] _normalize_url() — now strips tracking parameters
    Note: behavior change (not pure refactor) — test the new stripping logic

src/services/source_sync.py:
  - [FEATURE] sync_source() — added --new-only flag support
  - [FEATURE] _filter_existing_urls() new helper
```

### Step 4: Check existing test coverage for the scope

```bash
# For each scoped file, find existing tests
# Read them to understand what IS covered
# For bugfixes: specifically check if a regression test already exists
grep -r "regression" tests/ | grep -i "<function_name>"
```

Identify gaps specific to the changes:
- **Bugfixes with no regression test** (highest priority gap)
- New code paths with no test
- Modified behavior where tests still assert old behavior
- New error handling with no failure-case test
- New parameters/flags with no test exercising them

### Step 5: Generate targeted tests

Follow the same conventions as Mode 2 (Step 4), but with scope-specific ordering and priorities.

**Generation order:**
1. Regression tests for bugfixes (FIRST — before anything else)
2. Tests for new feature code paths
3. Tests for changed behavior
4. Edge case tests

**For every bugfix identified in Step 2, confirm with the user before writing:**

```
This looks like a bugfix:
  Function: fetch_article()
  Bug: HTTPError(403) from primary source propagated unhandled
  Fix: catch 403, fall back to archive.org

I'll write a regression test that:
  1. Mocks the primary fetch to return 403
  2. Asserts archive.org fallback is used
  3. Asserts FetchResult.source == "archive.org"

Does this match the bug? (adjust if I'm misunderstanding the failure)
```

Then generate using these patterns:

**Regression test pattern (for bugfixes) — REQUIRED for every bugfix:**
```python
@pytest.mark.regression
def test_<function>_<bug_description>_regression(self):
    """Regression: <one-line description of the bug>.

    Fix: <commit hash or "current session">
    Bug: <triggering condition> caused <incorrect behavior>
    """
    # Arrange: reproduce the EXACT state that triggered the bug
    # Be specific — use the actual values/types that caused the failure
    ...

    # Act: call the function that was fixed
    result = ...

    # Assert: verify the FIXED behavior
    # This assertion WOULD HAVE FAILED before the fix
    assert result == expected_after_fix
```

**Regression guard test (optional but recommended) — test the INVERSE to prove the old broken path is gone:**
```python
@pytest.mark.regression
def test_<function>_<bug_description>_no_longer_raises_regression(self):
    """Regression guard: <function> no longer raises <ExceptionType> on <condition>.

    Fix: <commit hash or "current session">
    """
    # The old code would have raised here
    # Now it should succeed silently or return a fallback
    result = function_under_test(triggering_input)
    assert result is not None  # or whatever the correct non-crashing behavior is
```

**Feature test pattern (for new features):**
```python
def test_<function>_<feature_description>(self):
    """<Feature name>: <what the new behavior should be>."""
    # Arrange
    ...
    # Act
    result = ...
    # Assert: verify the new behavior
    assert ...

def test_<function>_<feature>_disabled_by_default(self):
    """<Feature name>: existing behavior unchanged when feature not activated."""
    # Verify backward compatibility
    ...
```

**Naming rules:**
- Regression tests MUST end with `_regression`: `test_fetch_article_403_fallback_regression`
- Feature tests describe the behavior: `test_sync_source_new_only_skips_existing`
- Never use numbered suffixes: `test_fetch_article_2` (unacceptable)

### Step 6: Verify and report

Same as Mode 2 (Steps 5-7), but the report is scoped and separates regression from feature tests:

```
Scope Test Results
==================

Changes covered: 3 files, 7 modified functions
Bugfixes detected: 1
Tests generated: 14 (2 regression + 12 feature/coverage)

REGRESSION TESTS (bugfix protection)
--------------------------------------
src/core/fetcher.py:
  + test_fetch_article_403_fallback_regression              @regression
  + test_fetch_article_403_no_longer_raises_regression      @regression
  Bug: HTTPError(403) propagated unhandled → now falls back to archive.org

FEATURE & COVERAGE TESTS
--------------------------
src/core/fetcher.py:
  + test_fetch_article_retry_exponential_backoff
  + test_fetch_article_retry_exhaustion_raises
  + test_normalize_url_strips_utm_params
  + test_normalize_url_preserves_path_and_fragment

src/services/source_sync.py:
  + test_sync_source_new_only_skips_existing
  + test_sync_source_new_only_false_syncs_all
  + test_filter_existing_urls_empty_db
  + test_filter_existing_urls_partial_overlap

All passing: YES
Bugfixes with regression tests: 1/1
Uncovered change paths remaining: 0
```

Do NOT commit. The user manages git workflow separately.

---

## Scoped requests (any mode)

The user can narrow any mode to specific files or modules:

```
test trueup audit src/core/fetcher.py
test trueup fill src/services/
test trueup scope --files src/core/fetcher.py src/services/source_sync.py
```

When a scope is specified:
- **Audit** reports only on those files
- **Fill** generates tests only for those files (skips the confirmation step)
- **Scope** uses the specified files instead of auto-detecting from session/git

---

## Guardrails

- Never modify source code under `src/` — only create/edit files under `tests/`
- Never modify `AGENTS.md` or `CLAUDE.md`
- Never commit or push — the user manages git separately
- Never generate tests that require Docker, databases, network access, or running services
- Never delete or modify existing tests — only add new ones
- Never add `# type: ignore`, `# noqa`, or `pragma: no cover` to silence warnings
- Never mock more than necessary — if a function is pure, test it directly without mocks
- Always read the source file before writing tests — never guess at APIs or signatures
- Always run the tests after writing them — never present untested test code
- Always use `pytestmark = pytest.mark.unit` — tests must run in the stateless unit suite
- If a module is genuinely untestable without infrastructure (e.g., Celery task execution, Playwright browser control), skip it and note why in the report
