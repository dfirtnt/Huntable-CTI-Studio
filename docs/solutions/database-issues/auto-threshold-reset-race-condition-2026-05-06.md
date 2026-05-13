---
title: "Auto-trigger threshold resets to 60 due to concurrent autosave race condition"
date: "2026-05-06"
module: workflow_config
problem_type: database_issue
component: database
severity: high
symptoms:
  - "Auto-Processing Threshold resets to 60 after being saved on the Settings page"
  - "Concurrent PUT autosave requests deactivate all active config rows simultaneously"
  - "Losing thread receives null current_config due to PostgreSQL READ COMMITTED re-evaluation"
  - "Null config fallback silently overwrites user value with hardcoded column default"
root_cause: thread_violation
resolution_type: code_fix
related_components:
  - service_object
  - database
tags:
  - race-condition
  - concurrent-requests
  - postgresql
  - read-committed
  - config-versioning
  - appsettings
  - autosave
  - debounce
---

# Auto-trigger threshold resets to 60 due to concurrent autosave race condition

## Problem

The "Auto-Processing Threshold" (`auto_trigger_hunt_score_threshold`) on the Settings page
would reset to 60 after being explicitly saved, even though the save appeared successful.
Root cause: concurrent PUT autosave requests from `workflow.html` deactivated the active
config row mid-flight in a race, causing a losing thread to fall back to the database column
default (60.0) when constructing a new config row.

## Symptoms

- Threshold value saved (e.g., 95) would revert to 60 after a short delay or page refresh
- The reset was not immediate — it could take seconds to minutes before the value appeared wrong
- Other settings on the same page were unaffected
- Database inspection revealed duplicate config rows at the same version number; the highest-ID rows (which became "active") contained the wrong value (60)
- The problem persisted after a prior partial fix (commit d0e622ae) that isolated the threshold from preset/agent config writes

## What Didn't Work

A prior fix (commit `d0e622ae`) narrowed which code paths could write to
`auto_trigger_hunt_score_threshold`, isolating it from preset saves and agent config
updates. This reduced the frequency of resets but did not address the actual root cause:
the `workflow.html` frontend fires a PUT on every settings change with a 300ms debounce,
and when route handlers were converted from `async def` to `def` (enabling FastAPI's thread
pool), two PUT requests could execute truly concurrently. The prior fix only narrowed which
column-touching code ran — it did not prevent two simultaneous PUT threads from racing
through the deactivate-then-insert lifecycle.

## Solution

Moved `auto_trigger_hunt_score_threshold` out of `AgenticWorkflowConfigTable` (versioned,
deactivation-lifecycle rows) and into `AppSettingsTable` (a flat key-value store with no
versioning or lifecycle transitions). The value now lives in a single stable row, immune to
the deactivation race.

**New helpers in `src/web/routes/workflow_config.py`:**

```python
_AUTO_TRIGGER_THRESHOLD_KEY = "AUTO_TRIGGER_HUNT_SCORE_THRESHOLD"

def _get_threshold_from_settings(db_session) -> float | None:
    row = db_session.query(AppSettingsTable).filter(
        AppSettingsTable.key == _AUTO_TRIGGER_THRESHOLD_KEY
    ).first()
    if row and row.value is not None:
        try:
            return float(row.value)
        except (TypeError, ValueError):
            pass
    return None

def _save_threshold_to_settings(db_session, value: float) -> None:
    row = db_session.query(AppSettingsTable).filter(
        AppSettingsTable.key == _AUTO_TRIGGER_THRESHOLD_KEY
    ).first()
    if row:
        row.value = str(value)
        row.updated_at = datetime.now()
    else:
        db_session.add(AppSettingsTable(
            key=_AUTO_TRIGGER_THRESHOLD_KEY,
            value=str(value),
            category="workflow",
        ))
```

**PATCH endpoint** (explicit Settings save) writes to `AppSettingsTable` before touching any
config row:

```python
_save_threshold_to_settings(db_session, value)
current_config = _active_workflow_config_query(db_session).with_for_update().first()
if current_config:
    current_config.auto_trigger_hunt_score_threshold = value
db_session.commit()
```

**GET endpoint** reads from `AppSettingsTable` first, with a lazy migration that seeds the
key on first load from the existing config row — so subsequent autosaves never fall through
to the hardcoded default:

```python
settings_threshold = _get_threshold_from_settings(db_session)
if settings_threshold is None:
    config_threshold = getattr(config, "auto_trigger_hunt_score_threshold", 60.0)
    _save_threshold_to_settings(db_session, config_threshold)
    db_session.commit()
    settings_threshold = config_threshold
legacy_dict["auto_trigger_hunt_score_threshold"] = settings_threshold
```

**PUT endpoint** (autosave) reads `AppSettingsTable` before falling back to the config row
or column default:

```python
_settings_threshold = _get_threshold_from_settings(db_session)
final_auto_trigger_hunt_score_threshold = (
    config_update.auto_trigger_hunt_score_threshold
    if config_update.auto_trigger_hunt_score_threshold is not None
    else (
        _settings_threshold if _settings_threshold is not None
        else (getattr(current_config, "auto_trigger_hunt_score_threshold", 60.0) if current_config else 60.0)
    )
)
```

All 4 secondary write paths (prompt save, rollback, bootstrap, reset-to-defaults) were
updated to call `_get_threshold_from_settings` before constructing new config rows, so the
column on `AgenticWorkflowConfigTable` is still populated correctly for compatibility.

## Why This Works

**The PostgreSQL race mechanism:** The default isolation level is READ COMMITTED. When
`_deactivate_active_workflow_configs` runs inside a PUT handler, it issues
`SELECT ... FOR UPDATE` to lock active config rows then marks them inactive. If two PUT
threads run concurrently, the second thread's `SELECT ... FOR UPDATE` blocks until the
first commits. Once released, the second thread re-evaluates the query under READ COMMITTED
— it now sees the rows the first thread already deactivated, so it finds nothing and
returns `None`. With `current_config = None`, the code fell back to the column default
`60.0`. The losing thread wrote a new row with threshold=60, which had the highest ID and
became the canonical active config. All subsequent versions copied that 60.0 forward.

**The lifecycle mismatch:** `AgenticWorkflowConfigTable` is a versioned audit log — every
config write deactivates old rows and inserts a new one. This lifecycle is designed for
preset and agent config history. Storing a scalar setting there meant every concurrent write
was a potential deactivation race.

**Why `AppSettingsTable` is immune:** `AppSettingsTable` rows are upserted in place, never
deactivated. Two concurrent writers both `UPDATE`-ing the same row serialize naturally at
the database row lock level. There is no tombstone-and-insert pattern, so `current_config`
can never be `None`.

## Prevention

**Match table lifecycle to value semantics.** Any scalar setting that must survive across
config versions is a poor fit for a table whose write path includes deactivate-then-insert.
Use `AppSettingsTable` (or an equivalent non-versioned store) for values that have a single
current state.

**Fallback chains that bottom out on a hardcoded default are a latent data-loss path.**
The pattern `value if value is not None else default` is safe in isolation, but if the
"value" source can disappear due to a concurrent write (as `current_config` could here),
the default becomes a silent data-loss path. Every link in a fallback chain must be stable
under concurrency, not just the happy path.

**Converting `async def` to `def` in FastAPI requires a concurrency audit.** This is not
a cosmetic change — it opts the handler into the thread pool, enabling true simultaneous
execution. Any deactivate-then-insert or read-modify-write pattern must be re-audited for
races even if it "worked" in async mode where cooperative scheduling reduced overlap.

**Write to the stable store first, then update derived locations.** The PATCH endpoint
pattern here — write to `AppSettingsTable`, then update the config row if one exists —
ensures that even if the config row write fails or races, the source of truth is already
consistent.

## Related Issues

- Commit `d0e622ae` — prior partial fix that isolated threshold from preset writes (did not fix the race)
- Commits `4e507f85`, `fa36e3ab` — this fix
- `docs/solutions/ui-bugs/agent-prompt-save-display-revert-AgentPrompts-20260202.md` — similar async race pattern in agent prompt save/display (different component, same general shape)
- `docs/solutions/workflow-issues/agent-prompt-state-refactor-stop-recurring-save-display-20260311.md` — recurring fix pattern in workflow config (pattern doc for multi-async mutation issues)
