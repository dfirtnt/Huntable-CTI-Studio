#!/usr/bin/env python3
"""Migration: add osdetection_fallback_enabled column to agentic_workflow_config.

Why
---
A UI toggle was added to the workflow config page allowing the OS Detection agent
to fall back from SEC-BERT classification to an LLM call when the classifier
confidence is below the configured threshold. The column defaults to FALSE so
existing installs keep their prior behavior (no fallback) until explicitly enabled.

Adds:
- osdetection_fallback_enabled: BOOLEAN NOT NULL DEFAULT FALSE on agentic_workflow_config

Idempotent: skips silently if the column already exists.

Usage
-----
    python scripts/migrate_add_osdetection_fallback_enabled.py
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add osdetection_fallback_enabled column to agentic_workflow_config table."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)

        with engine.connect() as conn:
            check_query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'agentic_workflow_config'
                AND column_name = 'osdetection_fallback_enabled'
            """)
            result = conn.execute(check_query)
            if result.fetchone():
                logger.info("Column osdetection_fallback_enabled already exists, skipping migration")
                return True

            logger.info("Adding osdetection_fallback_enabled column to agentic_workflow_config table...")
            alter_query = text("""
                ALTER TABLE agentic_workflow_config
                ADD COLUMN osdetection_fallback_enabled BOOLEAN NOT NULL DEFAULT FALSE
            """)
            conn.execute(alter_query)
            conn.commit()

            logger.info("Migration completed successfully")
            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
