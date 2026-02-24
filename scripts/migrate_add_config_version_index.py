#!/usr/bin/env python3
"""
Migration script to add an index on agentic_workflow_config.version for fast
ORDER BY version DESC in config versions list API.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add index on agentic_workflow_config.version if missing."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'agentic_workflow_config' AND indexname = 'ix_agentic_workflow_config_version'
            """)
            )
            if result.fetchone():
                logger.info("Index ix_agentic_workflow_config_version already exists, skipping")
                return True

            logger.info("Creating index ix_agentic_workflow_config_version on agentic_workflow_config(version)...")
            conn.execute(
                text("""
                CREATE INDEX IF NOT EXISTS ix_agentic_workflow_config_version
                ON agentic_workflow_config (version DESC)
            """)
            )
            conn.commit()
            logger.info("Migration completed successfully")
            return True
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
