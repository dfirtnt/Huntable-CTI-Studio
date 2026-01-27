---
name: lgtest
description: When the user invokes "LGTest", reviews the most recent changes (especially from the current chat, but not limited to it) and proposes adding new tests—unit, UI, smoke, API, or integration—as appropriate. Use when the user says "LGTest" or asks to review changes and propose tests.
---

# LGTest — Review Changes & Propose Tests

**Trigger:** User says "LGTest" (or equivalent). Agent reviews recent changes and proposes new tests.

## Workflow

### 1. Gather recent changes

Use (in order of relevance):

- **Primary:** Files modified or discussed in the **current chat** (edits, diffs, mentions).
- **Secondary:** `git status` and `git diff` (uncommitted or last commit).
- **Optional:** Recent commits or branch diff if user implied “branch” or “PR”.

Treat chat-edited paths as highest priority; git state as fallback or extension.

### 2. Map changes to test surface

For each changed or affected area, decide:

| Change type | Prefer | Location pattern |
|-------------|--------|------------------|
| Routes, handlers, API | api | `tests/api/test_*.py` |
| Web UI, templates, JS | ui | `tests/ui/test_*.py` |
| Services, business logic | unit | `tests/services/`, `tests/utils/`, root `tests/test_*.py` |
| DB, queues, external deps | integration | `tests/integration/test_*.py` |
| Full user flows | e2e | `tests/e2e/test_*.py` |
| Startup, connectivity | smoke | `tests/smoke/` |

Project rule: all test entry is via **run_tests.py** (smoke | unit | api | integration | ui | e2e).

### 3. Propose new tests

Output a **LGTest Proposal** in this shape:

```markdown
## LGTest Proposal

### Changes in scope
- [path or area 1]
- [path or area 2]

### Proposed tests

| Type | Target / new file | Rationale |
|------|-------------------|-----------|
| unit | tests/services/test_foo.py | Covers new FooService.bar() |
| api  | tests/api/test_baz_api.py | New /baz route |
| ui   | tests/ui/test_baz_ui.py   | New Baz page and buttons |
```

- **Type:** one of `unit`, `ui`, `smoke`, `api`, `integration`, `e2e`.
- **Target:** existing file to extend, or `tests/<category>/test_<name>.py` for new.
- **Rationale:** one line linking change to test (e.g. “New endpoint X”, “New workflow step Y”).

Add a short **Implementation notes** list only when useful (e.g. “reuse fixtures from test_bar_api.py”, “mark as @pytest.mark.ui”).

### 4. Execution

- **Do not** create or edit test files until the user approves or asks to implement.
- If the user says “go”, “implement”, “add them”, etc., implement the proposed tests and wire them into `run_tests.py` if that’s required for discovery (in this project, discovery is path-based, so usually no run_tests.py edits needed).
- After adding tests, run the relevant group (e.g. `python3 run_tests.py api`) and report success/failure.

## Conventions (this project)

- Test runner: `python3 run_tests.py [smoke|unit|api|integration|ui|e2e]`
- UI tests: Playwright; live under `tests/ui/` and `tests/e2e/`.
- New tests must be discoverable by the existing run_tests.py categories (path-based).

## Example

User says "LGTest". Recent chat edited `src/web/routes/workflow_config.py` and `src/web/templates/workflow.html`.

**Proposal:**

| Type | Target / new file | Rationale |
|------|-------------------|-----------|
| api  | tests/api/test_workflow_config_api.py | New/updated workflow config endpoints |
| ui   | tests/ui/test_workflow_comprehensive_ui.py | Workflow template and UI behavior |

Implementation notes: Extend existing workflow UI test if present; add API test for any new route in `workflow_config.py`.
