#!/usr/bin/env python3
"""Migration: create workflow_config_presets table.

Why
---
The workflow config UI gained a presets system allowing named snapshots of the
full configuration (thresholds, agent models, QA toggles, prompts) to be saved,
restored, and shared. Without this table the app will fail to load the #config
page's preset list and the apply/save preset endpoints will 500.

Creates:
- workflow_config_presets table (see src/database/models.py: WorkflowConfigPresetTable)

Idempotent: SQLAlchemy create_all with checkfirst -- safe to re-run.

Usage
-----
    python scripts/migrate_workflow_config_presets.py
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine

from src.database.models import Base, WorkflowConfigPresetTable

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
        Base.metadata.create_all(engine, tables=[WorkflowConfigPresetTable.__table__])

        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
