#!/usr/bin/env python3
"""
Migration script to fix pgvector B-tree index bug.

PostgreSQL B-tree indexes have a 2704-byte row limit. Vector(768) is ~3088 bytes,
so index=True on Vector columns creates an invalid B-tree that causes
ProgramLimitExceeded on INSERT/UPDATE.

This script:
1. Drops B-tree indexes on Vector(768) columns (sigma_rules, articles, article_annotations)
2. Creates pgvector HNSW indexes using vector_cosine_ops (for cosine similarity)

Run after schema exists. Safe to run multiple times (idempotent).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine, inspect, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Table.column -> index name SQLAlchemy creates (ix_<tablename>_<column>)
VECTOR_COLUMNS = [
    ("sigma_rules", "embedding", "ix_sigma_rules_embedding"),
    ("articles", "embedding", "ix_articles_embedding"),
    ("article_annotations", "embedding", "ix_article_annotations_embedding"),
]


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
            for table, column, btree_index_name in VECTOR_COLUMNS:
                try:
                    inspector = inspect(engine)
                    indexes = inspector.get_indexes(table)
                    index_names = [idx["name"] for idx in indexes]
                except Exception:
                    logger.info("Table %s does not exist, skipping", table)
                    continue

                hnsw_index_name = f"ix_{table}_{column}_hnsw"

                # Drop B-tree index if it exists
                if btree_index_name in index_names:
                    logger.info("Dropping B-tree index %s on %s.%s", btree_index_name, table, column)
                    conn.execute(text(f'DROP INDEX IF EXISTS "{btree_index_name}"'))
                    conn.commit()
                    logger.info("  Dropped %s", btree_index_name)
                    # Must create HNSW after drop
                    need_hnsw = True
                elif hnsw_index_name in index_names:
                    logger.info("  HNSW index already exists, skipping %s", table)
                    need_hnsw = False
                else:
                    need_hnsw = True

                if need_hnsw:
                    logger.info("Creating HNSW index on %s.%s", table, column)
                    conn.execute(
                        text(
                            f'CREATE INDEX IF NOT EXISTS "{hnsw_index_name}" '
                            f'ON "{table}" USING hnsw ("{column}" vector_cosine_ops)'
                        )
                    )
                    conn.commit()
                    logger.info("  Created %s", hnsw_index_name)

        logger.info("Migration completed successfully")
        return True

    except Exception as e:
        logger.error("Migration failed: %s", e)
        import traceback

        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
