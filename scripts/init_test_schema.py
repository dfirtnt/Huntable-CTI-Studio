#!/usr/bin/env python3
"""Initialize test database schema. Run with venv Python."""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault("APP_ENV", "test")


async def main():
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.database.async_manager import async_db_manager

    await async_db_manager.create_tables()
    db_url = os.environ.get("TEST_DATABASE_URL")
    if db_url:
        # ``create_all`` does not add columns to an existing table. Keep the
        # test database aligned with the execution-snapshot migration so API
        # and integration tests behave like a migrated deployment.
        from scripts.migrate_execution_snapshot_schema import apply_plan, build_plan

        sync_engine = create_engine(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            plan = build_plan(inspect(sync_engine))
            if plan.total():
                apply_plan(sync_engine, plan)
        finally:
            sync_engine.dispose()

        # ``create_all`` builds the unique index models.py declares on
        # ``version``, but a sequence is not a model-level object, so a freshly
        # bootstrapped test database has no ``agentic_workflow_config_version_seq``.
        # Allocation then silently takes its pre-migration ``max()+1`` fallback and
        # the concurrency tests skip instead of failing -- the race-free guarantee
        # goes unverified on a clean checkout, which is the divergence the
        # create-migration convention warns about. Apply it here for the same
        # reason the execution-snapshot migration is applied above.
        from scripts.migrate_workflow_config_version_unique import run_migration

        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = db_url
        try:
            if not run_migration():
                raise RuntimeError("Version-uniqueness migration failed during test bootstrap")
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                for tbl in ("sources", "articles", "agentic_workflow_config"):
                    r = await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"})
                    if r.scalar() is None:
                        raise RuntimeError(f"Missing table after bootstrap: {tbl}")
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
