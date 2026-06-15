#!/usr/bin/env python3
"""Migration: create sigma_evaluations table.

Why
---
The end-to-end Sigma rule eval needs per-article tracking of expected vs
generated Sigma rules, scored at logsource and detection-atom granularity
(precision/recall). This table backs the Sigma eval results API/UI and is the
Sigma analog of subagent_evaluations.

Creates:
- sigma_evaluations table (see src/database/models.py: SigmaEvaluationTable)

Idempotent: SQLAlchemy create_all with checkfirst -- safe to re-run. New installs
get the table automatically via Base.metadata.create_all at startup; this script
is for migrating existing databases.

Usage
-----
    python scripts/migrate_sigma_evaluation_table.py
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine

from src.database.models import Base, SigmaEvaluationTable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create sigma_evaluations table if it doesn't exist."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)
        logger.info("Creating sigma_evaluations table...")
        Base.metadata.create_all(engine, tables=[SigmaEvaluationTable.__table__])
        logger.info("Migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
