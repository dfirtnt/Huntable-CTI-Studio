#!/usr/bin/env python3
"""Migration: create subagent_evaluations table.

Why
---
The extractor eval workflow needed per-article, per-subagent tracking of expected
vs actual observable counts (e.g. "expected 3 cmdlines, got 2"). This table backs
the /eval UI results page and the cmdline extractor tuning pipeline. It was
introduced alongside the subagent evaluation scripts in scripts/evaluate_cmdline_extractor.py.

Creates:
- subagent_evaluations table (see src/database/models.py: SubagentEvaluationTable)

Idempotent: SQLAlchemy create_all with checkfirst -- safe to re-run.

Usage
-----
    python scripts/migrate_subagent_evaluation_table.py
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine

from src.database.models import Base, SubagentEvaluationTable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create subagent_evaluations table if it doesn't exist."""

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
        # This will create table if it doesn't exist
        logger.info("Creating subagent_evaluations table...")
        Base.metadata.create_all(engine, tables=[SubagentEvaluationTable.__table__])

        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
