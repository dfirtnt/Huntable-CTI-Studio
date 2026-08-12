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
