#!/usr/bin/env python3
"""Migration: add raw_yaml column to sigma_rules table.

Why
---
The sigma indexer was updated to preserve the original YAML source from the
SigmaHQ repo alongside the parsed fields. Storing raw_yaml enables rule
diff/debugging without needing the SigmaHQ repo checked out locally, and is
used by the MCP sigma tool to return source YAML to callers. The smoke test
in tests/smoke/test_mcp_rag_smoke.py skips with a warning if this column is absent.

Adds:
- raw_yaml TEXT (nullable) -- original YAML text from the SigmaHQ repo file

After running, re-index to populate the column for existing rules:
    ./run_cli.sh sigma index-metadata --force

Idempotent: skips if the column already exists.

Usage
-----
    python scripts/migrate_sigma_raw_yaml.py
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration() -> bool:
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

            if "raw_yaml" not in existing_columns:
                logger.info("Adding raw_yaml column to sigma_rules...")
                conn.execute(
                    text("""
                    ALTER TABLE sigma_rules
                    ADD COLUMN raw_yaml TEXT;
                """)
                )
                logger.info("✅ Added raw_yaml column")
            else:
                logger.info("✅ raw_yaml column already exists")

            conn.commit()

        logger.info("✅ Migration completed successfully")
        logger.info(
            "Next step: re-run `./run_cli.sh sigma index-metadata --force` "
            "to populate raw_yaml for all existing rules."
        )
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
