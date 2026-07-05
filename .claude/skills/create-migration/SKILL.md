---
name: create-migration
description: Scaffold, apply, and verify a database schema migration for Huntable CTI Studio following the house pattern (standalone idempotent scripts/migrate_*.py, NOT Alembic). Use whenever the user asks to "create a migration", "add a column", "add a table", "migrate the schema", "write a migration script", or any schema change to the PostgreSQL database — even if they mention Alembic (this repo does not use Alembic migrations despite it being a dependency).
disable-model-invocation: true
---

# Create Migration

This repo does **not** use Alembic for migrations, even though `alembic` appears in
`pyproject.toml`. The house pattern is a standalone, idempotent Python script in
`scripts/migrate_add_<name>.py`, applied by hand against the live dev database.
The test database schema is generated directly from the ORM models, not from
migration scripts — which is why step 1 below matters most.

## Canonical example

Read `scripts/migrate_add_osdetection_fallback_enabled.py` before writing anything.
It is the reference implementation: docstring with Why / Adds / Idempotent / Usage
sections, `DATABASE_URL` from the environment, `postgresql+asyncpg://` →
`postgresql://` swap, an `information_schema` existence check so re-runs are
harmless, logging, and a proper exit code.

## Workflow

1. **Update the ORM model first.** `src/database/models.py` is a contract source of
   truth (see AGENTS.md). The test DB is built from these models by
   `scripts/init_test_schema.py` (`async_db_manager.create_tables()`), so a schema
   change that only exists in a migration script will silently diverge from every
   test run. If the change touches workflow configuration, also update
   `src/config/workflow_config_schema.py` and check whether the 9 quickstart presets
   in `config/presets/AgentConfigs/quickstart/` need the new field.

2. **Write `scripts/migrate_add_<name>.py`** following the canonical example.
   Non-negotiables, because operators re-run these scripts freely:
   - Idempotent: check `information_schema.columns` (or `to_regclass` for tables)
     and skip silently if already applied.
   - `DATABASE_URL` from env — never hardcode credentials.
   - Docstring explains *why* the change exists, not just what it adds.
   - Sensible column default so existing rows/installs keep prior behavior.

3. **Apply to the dev database.** The live DB runs in the `cti_postgres` container:
   `DATABASE_URL=... python scripts/migrate_add_<name>.py`
   Verify directly afterward:
   `docker exec cti_postgres psql -U cti_user -d cti_scraper -c "\d <table>"`

4. **Verify test-DB parity.** Run the tests nearest the changed model with
   `TEST_DATABASE_URL` (test DB on :5433, `.venv/bin/python -m pytest` directly —
   `run_tests.py --paths` deselects via markers). If the new column doesn't appear
   in test runs, the models.py change from step 1 is incomplete.

5. **Restart Python processes.** `src/` is bind-mounted but Python loads at process
   start: `docker restart cti_web` plus the Celery workers, or the app keeps
   running against the old schema expectations.

## Stop and ask the operator

- Any destructive change (DROP, type narrowing, NOT NULL without default on a
  populated table) — propose, don't apply.
- Anything touching eval ground-truth tables or `config/eval_articles_data/`.
