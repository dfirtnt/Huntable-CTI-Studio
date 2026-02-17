#!/usr/bin/env python3
"""
Migration script to create rag_presets table.

This table stores RAG chat presets (provider, model, max_results, similarity_threshold)
for the Threat Intelligence Chat feature.
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine

from src.database.models import Base, RagPresetTable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create rag_presets table if it doesn't exist."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Convert asyncpg to psycopg2 for SQLAlchemy
    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)
        logger.info("Creating rag_presets table...")
        Base.metadata.create_all(
            engine,
            tables=[RagPresetTable.__table__],
        )
        logger.info("Migration completed successfully")
        return True
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
