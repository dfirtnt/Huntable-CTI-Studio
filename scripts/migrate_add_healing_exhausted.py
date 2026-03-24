#!/usr/bin/env python3
"""
Migration script to add healing_exhausted column to sources table.

This column tracks whether a source has exhausted all AI auto-healing attempts
and needs manual user attention.
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
    """Add healing_exhausted column to sources table."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Convert asyncpg to psycopg2 for SQLAlchemy
    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        # Create engine
        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'sources'
                AND column_name = 'healing_exhausted'
            """)
            result = conn.execute(check_query)
            if result.fetchone():
                logger.info("Column healing_exhausted already exists, skipping migration")
                return True

            # Add column with default value
            logger.info("Adding healing_exhausted column to sources table...")
            alter_query = text("""
                ALTER TABLE sources
                ADD COLUMN healing_exhausted BOOLEAN NOT NULL DEFAULT FALSE
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
