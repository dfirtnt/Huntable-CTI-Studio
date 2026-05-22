---
title: "Model rollback 422 guard bypassed when MLModelVersionManager is mocked"
date: 2026-05-21
module: model_rollback_api
problem_type: test_failure
component: service_object
severity: medium
symptoms:
  - "test_rollback_version_without_artifact_returns_422 returns HTTP 200 instead of 422"
  - "test_rollback_artifact_file_missing_on_disk_returns_422 returns HTTP 200 instead of 422"
  - "422 guard condition evaluates to False even when os.path.exists is patched to return False"
  - "Rollback proceeds as if a valid artifact exists despite mocked missing file"
root_cause: test_isolation
resolution_type: code_fix
tags:
  - mocking
  - unittest-mock
  - http-422
  - artifact-validation
  - model-rollback
  - os-path-exists
  - magic-mock
  - late-import
related_components:
  - testing_framework
---

# Model rollback 422 guard bypassed when MLModelVersionManager is mocked

## Problem

Two API tests asserting HTTP 422 for missing model artifacts instead received HTTP 200, because the route handler called `_resolve_artifact_path` through a class imported inside the function body — a class that the tests had replaced with a `MagicMock`. The `MagicMock` returned a truthy object for every attribute access, silently bypassing the file-existence guard.

## Symptoms

- `TestModelRollbackEndpoint::test_rollback_version_without_artifact_returns_422` → `assert 200 == 422`
- `TestModelRollbackEndpoint::test_rollback_artifact_file_missing_on_disk_returns_422` → `assert 200 == 422`
- Both failures occurred even though `patch("os.path.exists", return_value=False)` was active
- No exception was raised; the rollback endpoint returned `{"success": True, ...}`

## What Didn't Work

The original guard in `src/web/routes/models.py` resolved the artifact path via a static method on the manager class, imported inside the handler body:

```python
from src.utils.model_versioning import MLModelVersionManager as _MVM

if not _MVM._resolve_artifact_path(version.model_file_path):
    raise HTTPException(status_code=422, detail=...)
```

The tests patched `src.utils.model_versioning.MLModelVersionManager`. Because `from ... import` re-resolves the name at call time against the patched module, `_MVM` became a `MagicMock`. Any attribute access on a `MagicMock` — including `._resolve_artifact_path(...)` — returns another `MagicMock`, which is always truthy. So `not _MVM._resolve_artifact_path(...)` evaluated to `False`, the guard was skipped, and the endpoint returned 200.

Patching `os.path.exists` had no effect because the real `_resolve_artifact_path` implementation was never reached — the call hit the Mock, not the class.

## Solution

Replace the class-method call with an inline `os.path.exists` check that preserves the primary→backup fallback logic. `patch("os.path.exists")` intercepts at the global `os` module level regardless of any class-level mocking.

**Before:**

```python
from src.utils.model_versioning import MLModelVersionManager as _MVM

if not _MVM._resolve_artifact_path(version.model_file_path):
    raise HTTPException(
        status_code=422,
        detail=f"No artifact found for model version {version.version_number}. ..."
    )
```

**After:**

```python
import os

_primary = version.model_file_path
_backup = os.path.join("backups/models", os.path.basename(_primary)) if _primary else None
_resolved = next((p for p in (_primary, _backup) if p and os.path.exists(p)), None)
if not _resolved:
    raise HTTPException(
        status_code=422,
        detail=f"No artifact found for model version {version.version_number}. ..."
    )
```

The backup path string `"backups/models"` matches `MLModelVersionManager.BACKUP_MODELS_DIR` and is hardcoded to avoid any attribute lookup on the potentially-mocked class.

## Why This Works

The root cause is a **mock-boundary mismatch**: the tests mock the entire manager class, but the route called a static method on that class to perform the file check. When `unittest.mock.patch` replaces the class with a `MagicMock`, every method call on it returns another truthy `MagicMock` — the real `os.path.exists` logic inside `_resolve_artifact_path` is never reached.

By inlining the check with `os.path.exists` directly, the test's `patch("os.path.exists", return_value=False)` now intercepts every call at the `os` module boundary, which the patch actually controls. The fix also preserves the primary→backup fallback semantics:

| Scenario | `_primary` | `os.path.exists` | `_resolved` | Response |
|---|---|---|---|---|
| `model_file_path=None` | `None` | N/A | `None` | 422 |
| Path set, file absent | truthy | `False` | `None` | 422 |
| Path set, file present | truthy | `True` | primary path | 200 (rollback) |

**General rule:** `os.path.exists` (and most `os.*` calls) are patchable at the `os` module boundary. Static methods on a mocked class are not, because the class itself has been replaced.

## Prevention

**1. Avoid importing a class inside a handler body when that class will be mocked in tests.**

Imports inside a function body re-resolve at call time — they pick up whatever the module attribute currently points to, including mocks. Prefer module-level imports, or extract the specific helper into a free function that can be patched precisely:

```python
# Instead of:
from src.utils.model_versioning import MLModelVersionManager as _MVM
_MVM._resolve_artifact_path(path)

# Prefer: extract as a free function and import it at module level
from src.utils.artifact_utils import resolve_artifact_path
resolve_artifact_path(path)
```

**2. Patch the helper, not just the lower-level primitive.**

If a guard delegates to a named helper, patch that helper directly rather than a lower-level primitive (`os.path.exists`). This makes the test intent explicit and avoids the mock-chain problem:

```python
with patch("src.web.routes.models.resolve_artifact_path", return_value=None):
    response = client.post("/api/model/rollback/1")
assert response.status_code == 422
```

**3. When patching `os.path.exists` globally, verify the production code actually calls it.**

If the test patches `os.path.exists` and the test still passes unexpectedly, add a side-effect assertion to confirm the patch was triggered:

```python
with patch("os.path.exists", return_value=False) as mock_exists:
    response = client.post("/api/model/rollback/1")
assert mock_exists.called, "os.path.exists was never called — guard may be bypassed"
assert response.status_code == 422
```

**4. Treat `@staticmethod` helpers that wrap `os` calls as an abstraction risk in test contexts.**

When a static method's only job is to call `os.path.exists` with fallback logic, consider whether the caller should use `os.path.exists` directly instead. Static methods on a class are invisible to patches targeting the class.

## Related Issues

- `src/web/routes/models.py` — `api_model_rollback` handler (lines ~694–703 as of 2026-05-21)
- `tests/api/test_model_rollback_api.py` — `TestModelRollbackEndpoint`
- `src/utils/model_versioning.py` — `MLModelVersionManager._resolve_artifact_path` (the static method that was called through the mock)
