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
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.database.async_manager import async_db_manager

    await async_db_manager.create_tables()
    db_url = os.environ.get("TEST_DATABASE_URL")
    if db_url:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                # create_all does not ALTER existing tables; keep test DB in sync with models
                await conn.execute(
                    text(
                        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS "
                        "healing_exhausted BOOLEAN NOT NULL DEFAULT FALSE"
                    )
                )
                await conn.execute(
                    text(
                        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS "
                        "healing_attempts INTEGER NOT NULL DEFAULT 0"
                    )
                )
            async with engine.connect() as conn:
                for tbl in ("sources", "articles", "agentic_workflow_config"):
                    r = await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"})
                    if r.scalar() is None:
                        raise RuntimeError(f"Missing table after bootstrap: {tbl}")
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
