#!/usr/bin/env python3
"""Migration: add atom precompute fields to sigma_rules table.

Why
---
The sigma novelty comparison was re-computing DNF atom sets and surface scores
on every call. At corpus scale this made novelty checks CPU-bound. These columns
cache the deterministic outputs of the parse so comparisons become a simple DB
read instead of a full re-parse.

Adds (all nullable, idempotent):
- canonical_class: TEXT    -- resolved telemetry class, e.g. "windows.process_creation"; indexed
- positive_atoms:  JSONB   -- sorted list of positive atom identity strings
- negative_atoms:  JSONB   -- sorted list of negative atom identity strings
- surface_score:   INTEGER -- DNF branch count (complexity proxy)

Ordering
--------
Run after migrate_sigma_canonical_fields.py (depends on canonical_json existing).
Run before or alongside migrate_sigma_to_canonical.py -- both scripts process
the sigma_rules table independently.

Idempotent: each column and index is checked before creation -- safe to re-run.

Usage
-----
    python scripts/migrate_sigma_atom_precompute.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from sqlalchemy import create_engine, inspect, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add atom precompute fields to sigma_rules table if they don't exist."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            inspector = inspect(engine)
            existing_columns = [col["name"] for col in inspector.get_columns("sigma_rules")]

            for col_name, col_type, col_comment in [
                ("canonical_class", "TEXT", "Resolved telemetry class from sigma_similarity"),
                ("positive_atoms", "JSONB", "Precomputed positive atom identity strings (sorted)"),
                ("negative_atoms", "JSONB", "Precomputed negative atom identity strings (sorted)"),
                ("surface_score", "INTEGER", "DNF branch count"),
            ]:
                if col_name not in existing_columns:
                    logger.info("Adding %s column...", col_name)
                    conn.execute(text(f"ALTER TABLE sigma_rules ADD COLUMN {col_name} {col_type};"))
                    logger.info("✅ Added %s column", col_name)
                else:
                    logger.info("✅ %s column already exists", col_name)

            existing_indexes = [idx["name"] for idx in inspector.get_indexes("sigma_rules")]
            if "idx_sigma_rules_canonical_class" not in existing_indexes:
                logger.info("Creating index on canonical_class...")
                conn.execute(
                    text("CREATE INDEX idx_sigma_rules_canonical_class ON sigma_rules(canonical_class);")
                )
                logger.info("✅ Created index on canonical_class")
            else:
                logger.info("✅ Index on canonical_class already exists")

            conn.commit()
        logger.info("✅ Migration completed successfully")
        return True
    except Exception as e:
        logger.error("❌ Migration failed: %s", e)
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
