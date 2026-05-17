---
title: "Sources Table Duplicate Rows — Missing UNIQUE Constraint + Silent Exception Swallowing"
date: "2026-05-16"
category: database-issues
module: source_sync
problem_type: database_issue
component: database
severity: high
symptoms:
  - "sources table contained ~80 rows when only ~41 unique sources were expected"
  - "39 identifier values each had two DB rows, all duplicates sharing a single created_at timestamp (2026-05-03 19:43:22 UTC)"
  - "/sources page displayed ~2x the expected source cards (e.g., Dark Reading appeared twice)"
  - "MCP list_sources returned 'No sources found' (active_only=true masked the issue — misleading signal)"
root_cause: missing_validation
resolution_type: code_fix
related_components:
  - service_object
  - background_job
tags:
  - duplicate-rows
  - upsert
  - on-conflict
  - silent-exception
  - schema-drift
  - unique-constraint
  - sqlalchemy
  - postgresql
  - source-sync
---

# Sources Table Duplicate Rows — Missing UNIQUE Constraint + Silent Exception Swallowing

## Problem

The `sources` PostgreSQL table silently accumulated 39 duplicate rows — one extra copy per configured source identifier — because a silent `except: return []` in `list_sources()` made a `sync-sources` run treat every YAML-defined source as new, and a plain `INSERT` in `create_source()` had no conflict guard. A missing `UNIQUE` constraint on `sources.identifier` (despite `unique=True` in the ORM model) let PostgreSQL accept all 39 duplicates without error.

## Symptoms

- The `/sources` page displayed approximately 2× the expected source cards; same name appeared in two cards (e.g., Dark Reading ×2)
- `curl /api/sources | python3 -c "import json,sys; from collections import Counter; data=json.load(sys.stdin); print(Counter(s['identifier'] for s in data['sources']))"` showed 39 identifiers each with count 2
- `SELECT id, identifier, created_at FROM sources ORDER BY created_at` in psql showed all 39 duplicates sharing `created_at = 2026-05-03 19:43:22` — a single batch event
- `\d sources` revealed only `sources_pkey` — no `UNIQUE` constraint on `identifier`, confirming the ORM model and DB schema had drifted

## What Didn't Work

- **MCP `list_sources` tool** returned "No sources found" (its `active_only=true` default masked the symptom and pointed in the wrong direction)
- **Assuming `unique=True` in the ORM implies a DB constraint** — SQLAlchemy's column declaration does not retroactively modify an existing table; no migration had applied the DDL
- **Checking FK constraints via `information_schema.referential_constraints`** returned 0 rows — FK constraints also did not exist in the DB, revealing broader schema-vs-model drift beyond just the UNIQUE constraint

## Solution

Three coordinated changes: a transactional live-data repair, an idempotent upsert replacing the blind INSERT, and two defensive changes in the sync path.

### Step 1 — Live data repair (run first; use ROLLBACK to preview)

```sql
BEGIN;

-- Identify originals (created before the duplication event)
CREATE TEMP TABLE _orig AS
  SELECT id, identifier FROM sources
  WHERE created_at < '2026-05-03'
    AND identifier IN (SELECT identifier FROM sources GROUP BY identifier HAVING COUNT(*) > 1);

-- Identify duplicates (created in the May 3 batch)
CREATE TEMP TABLE _dup AS
  SELECT id, identifier FROM sources
  WHERE created_at >= '2026-05-03'
    AND identifier IN (SELECT identifier FROM sources GROUP BY identifier HAVING COUNT(*) > 1);

-- Re-home articles from duplicates to originals (skip canonical_url conflicts)
UPDATE articles a
SET source_id = o.id
FROM _dup d JOIN _orig o ON o.identifier = d.identifier
WHERE a.source_id = d.id
  AND NOT EXISTS (
    SELECT 1 FROM articles a2
    WHERE a2.source_id = o.id AND a2.canonical_url = a.canonical_url
  );

-- Re-home source_checks
UPDATE source_checks sc
SET source_id = o.id
FROM _dup d JOIN _orig o ON o.identifier = d.identifier
WHERE sc.source_id = d.id;

-- Delete remaining articles on duplicates (canonical_url conflicts with original)
DELETE FROM articles WHERE source_id IN (SELECT id FROM _dup);

-- Delete the 39 duplicate source rows
DELETE FROM sources WHERE id IN (SELECT id FROM _dup);

-- Add the missing constraint now that duplicates are gone
ALTER TABLE sources ADD CONSTRAINT sources_identifier_key UNIQUE (identifier);

-- Verify: should show 41 sources and 0 duplicate identifiers
SELECT 'sources remaining' AS check, COUNT(*) FROM sources
UNION ALL
SELECT 'duplicate identifiers', COUNT(*) FROM (
  SELECT identifier FROM sources GROUP BY identifier HAVING COUNT(*) > 1
) x;

-- Replace ROLLBACK with COMMIT when satisfied
ROLLBACK;
```

**Actual impact (dry-run confirmed):** 172 articles re-homed, 862 source_checks re-homed, 0 rows dropped (no canonical_url conflicts existed).

> **Key discrimination:** Use `created_at < '2026-05-03'` — not `MIN(id)` — to identify originals. For `datadog_security_labs` the duplicate was assigned a lower ID (37) than the original (40) because it filled a sequence gap, making MIN(id) unreliable.

### Step 2 — `src/database/async_manager.py`: replace blind INSERT with upsert in `create_source()`

```python
# Before (blind INSERT — duplicates accepted by a constraint-free table):
db_source = SourceTable(identifier=source_data.identifier, ...)
session.add(db_source)
await session.commit()

# After (idempotent upsert):
from sqlalchemy.dialects.postgresql import insert as pg_insert

now = datetime.now()
values = {
    "identifier": source_data.identifier,
    "name": source_data.name,
    "url": source_data.url,
    "rss_url": source_data.rss_url,
    "check_frequency": source_data.config.check_frequency if source_data.config else 14400,
    "lookback_days": source_data.config.lookback_days if source_data.config else 180,
    "active": source_data.active,
    "config": source_data.config.model_dump(exclude_none=True) if source_data.config else {},
    "consecutive_failures": 0,
    "total_articles": 0,
    "average_response_time": 0.0,
    "created_at": now,
    "updated_at": now,
}

stmt = (
    pg_insert(SourceTable)
    .values(**values)
    .on_conflict_do_update(
        index_elements=["identifier"],
        set_={"name": values["name"], "url": values["url"],
              "rss_url": values["rss_url"], "active": values["active"],
              "config": values["config"], "updated_at": values["updated_at"]},
    )
    .returning(SourceTable)
)
result = await session.execute(stmt)
await session.commit()
db_source = result.scalar_one()
```

### Step 3 — `src/database/async_manager.py`: remove silent exception swallowing in `list_sources()`

```python
# Before (exception consumed; callers cannot distinguish failure from empty results):
    except Exception as e:
        logger.error(f"Failed to list sources: {e}")
        return []

# After: remove the entire try/except — exceptions propagate.
# All web route callers (sources.py, dashboard.py, analytics.py, pages.py)
# already wrap list_sources() in their own try/except blocks.
```

### Step 4 — `src/services/source_sync.py`: add empty-result warning guard in `_sync_to_db()`

```python
existing_sources = await self.db_manager.list_sources()

# Guard against a DB failure that returns an empty list when sources exist.
if not existing_sources and source_configs and not new_only:
    logger.warning(
        "list_sources() returned 0 rows but %d source configs are loaded — "
        "verifying DB is reachable before proceeding with creates",
        len(source_configs),
    )

existing_by_identifier = {src.identifier: src for src in existing_sources}
```

## Why This Works

Three independent conditions aligned to produce the bug; each fix addresses one:

1. **Missing DB constraint** — The table was created before `unique=True` was added to the ORM model, and the project has no Alembic migrations to apply DDL changes. PostgreSQL never received the `ALTER TABLE ... ADD CONSTRAINT` statement and silently accepted all 39 duplicate inserts. `sources_identifier_key` closes this permanently.

2. **Silent exception swallowing** — `list_sources()` caught all exceptions and returned `[]`. A transient DB error during `sync-sources` produced a structurally valid-looking empty list. The caller had no way to distinguish "zero configured sources" from "DB query failed" — it built `existing_by_identifier = {}` and treated every YAML source as new. Removing the handler lets exceptions propagate so callers fail fast rather than proceed with corrupt state.

3. **Non-idempotent insert** — With `existing_by_identifier` empty, the sync loop found no existing entry for any identifier and called `create_source()` for all 39. The plain `session.add()` had no conflict guard, so all 39 were inserted as fresh rows. PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` makes `create_source()` safe to call even when the row already exists.

The warning guard in `_sync_to_db()` adds a diagnostic signal without blocking: if `list_sources()` returns 0 rows when YAML configs are loaded, a warning is logged before the loop runs — catching the problematic state while remaining compatible with legitimate empty-DB startup scenarios.

## Prevention

**1. Enforce DB constraints independently of ORM declarations**

`unique=True` and `ForeignKey(...)` in SQLAlchemy do not retroactively modify an existing table. For projects without Alembic, add a startup assertion:

```python
async def assert_schema_constraints(engine):
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = 'sources_identifier_key' "
            "AND table_name = 'sources'"
        ))
        if not result.fetchone():
            raise RuntimeError(
                "DB schema missing sources_identifier_key — run the repair migration"
            )
```

**2. Default to upsert for all seed/sync write paths**

Any job that reads a config/YAML source and writes to a DB table should use `INSERT ... ON CONFLICT DO UPDATE` (or `DO NOTHING`) as the default, not a plain `INSERT`. This makes the operation safe to run multiple times:

```python
# Sync-path pattern:
stmt = (
    pg_insert(MyTable)
    .values(**values)
    .on_conflict_do_update(index_elements=["identifier"], set_={...})
    .returning(MyTable)
)
```

**3. Treat `except Exception: return []` as a code smell in query methods**

A function that swallows all exceptions and returns a valid-looking empty value prevents callers from distinguishing failure from empty results. Prefer:
- Let the exception propagate (callers that need resilience add their own handlers)
- Raise a typed exception so callers can match specifically: `raise SourceListError(...) from e`

**4. Validate zero-result sync inputs before writing**

Any sync that builds a lookup dict from a DB query and conditionally skips inserts should validate before writing:

```python
existing_sources = await self.db_manager.list_sources()
if not existing_sources and source_configs and not new_only:
    # Log warning or raise — don't silently proceed with creates
    logger.warning("Zero existing sources with %d config entries — aborting", len(source_configs))
    return
```

## Related Issues

- Related: `docs/solutions/database-issues/auto-threshold-reset-race-condition-2026-05-06.md` — different mechanism (concurrent writes vs. schema gap) but shares the pattern of silent data corruption when invariants aren't enforced at the DB layer
- Commits `e087c28c` ("fix(db): add PK migrations and limit(1) guards for duplicate-safe source lookups") and `6cfd2f25` ("fix(sources): deduplicate list_sources via SQLAlchemy unique()") document prior partial mitigations applied before this root-cause fix
