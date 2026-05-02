#!/usr/bin/env python3
"""Migration: drop healing_exhausted, healing_attempts columns and healing_events table.

The auto-healing feature was removed; these schema objects are no longer referenced.
Idempotent: each DROP is guarded by an existence check.
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration() -> bool:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            for column in ("healing_exhausted", "healing_attempts"):
                exists = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'sources' AND column_name = :col"
                    ),
                    {"col": column},
                ).fetchone()
                if exists:
                    logger.info(f"Dropping sources.{column}")
                    conn.execute(text(f"ALTER TABLE sources DROP COLUMN {column}"))
                else:
                    logger.info(f"sources.{column} already absent, skipping")

            table_exists = conn.execute(
                text("SELECT to_regclass('public.healing_events')")
            ).scalar()
            if table_exists:
                logger.info("Dropping healing_events table")
                conn.execute(text("DROP TABLE healing_events"))
            else:
                logger.info("healing_events table already absent, skipping")

            conn.commit()
            logger.info("Migration completed")
            return True
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
