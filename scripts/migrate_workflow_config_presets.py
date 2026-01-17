#!/usr/bin/env python3
"""
Migration script to create workflow_config_presets table.

This table stores workflow configuration presets (thresholds, agent models,
QA toggles, prompts, etc.) for the workflow #config page.
"""

import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from src.database.models import Base, WorkflowConfigPresetTable
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create workflow_config_presets table if it doesn't exist."""

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

        # Create table using SQLAlchemy metadata
        logger.info("Creating workflow_config_presets table...")
        Base.metadata.create_all(
            engine,
            tables=[
                WorkflowConfigPresetTable.__table__
            ]
        )

        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
