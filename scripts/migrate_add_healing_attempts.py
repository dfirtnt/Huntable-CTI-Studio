#!/usr/bin/env python3
"""Migration: add healing_attempts column to sources table."""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'sources' AND column_name = 'healing_attempts'"
            ))
            if result.fetchone():
                logger.info("Column healing_attempts already exists, skipping")
                return True

            logger.info("Adding healing_attempts column to sources table...")
            conn.execute(text(
                "ALTER TABLE sources ADD COLUMN healing_attempts INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
            logger.info("Migration completed successfully")
            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
