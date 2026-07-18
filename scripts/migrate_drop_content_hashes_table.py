#!/usr/bin/env python3
"""Migration: drop the legacy content_hashes table.

Why
---
As of commit 89d0a131 (2026-07-17), both DatabaseManager and AsyncDatabaseManager
dedup against articles.content_hash via a shared statement builder
(src/database/statements.py: build_existing_content_hashes_stmt); nothing reads
content_hashes anymore. The ledger held only 312 rows vs 6,406 articles because
only the sync bulk-create path ever wrote it -- it was never a complete dedup
source. All remaining writers/readers (ContentHashTable in models.py, the
create_articles_bulk insert, the delete_article cleanup, the schema-ensure PK
DDL, and scripts/backfill_image_ocr.py's collision check + upsert) were removed
alongside this migration.

Drops:
- content_hashes table

Idempotent: DROP TABLE IF EXISTS -- safe to re-run.

Deploy order matters
---------------------
Run this BEFORE (or immediately when) deploying the code change that removes
content_hashes cleanup from AsyncDatabaseManager.delete_article(). If the new
code deploys first and this migration lags, deleting one of the (up to 312)
legacy articles that still has a content_hashes row will hit a foreign-key
violation (content_hashes.article_id -> articles.id, no ON DELETE CASCADE) and
delete_article() will return False instead of True until this migration runs.

Usage
-----
    python scripts/migrate_drop_content_hashes_table.py
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
    """Drop the content_hashes table if it exists."""

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)

        with engine.connect() as conn:
            logger.info("Dropping content_hashes table...")
            conn.execute(text("DROP TABLE IF EXISTS content_hashes"))
            conn.commit()

            logger.info("Migration completed successfully")
            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
