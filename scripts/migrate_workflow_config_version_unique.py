#!/usr/bin/env python3
"""Migration: make agentic_workflow_config.version genuinely unique.

Why
---
`src/database/models.py` has always declared `version = Column(..., unique=True)`,
but this database was created before that attribute existed, so the unique index
was never built. Nothing rejected a collision, and `_next_workflow_config_version()`
allocated numbers with an unguarded `SELECT max(version) + 1`. Two concurrent
writers read the same maximum and both committed it.

Measured on 2026-08-22: 8,152 rows, 7,967 distinct versions -- 164 version numbers
were shared by two or more rows, the worst by five. The UI presents version as the
config's identity ("Version: 7967") and `configVersionSearch` looks configs up by
it, so that identity was ambiguous.

What this does
--------------
1. Renumbers the losers of each collision. For every duplicated version the row
   with the lowest `id` keeps the number it has always been addressed by; the
   later rows are moved above the current maximum and their original number is
   recorded in `description` so the history stays readable. `id` never changes,
   so `sigma_evaluations.workflow_config_id` and
   `subagent_evaluations.workflow_config_id` -- which reference `id`, not
   `version` -- are untouched.
2. Creates the UNIQUE index the model has always declared.
3. Creates a sequence seeded above the current maximum and owned by the column,
   so allocation is atomic. A sequence cannot hand the same number to two callers
   regardless of transaction timing, which removes the race rather than guarding
   it: the advisory lock added in 77506e68 stays as defence in depth.

Idempotent: skips any step whose result is already in place.

Usage
-----
    python scripts/migrate_workflow_config_version_unique.py
    # or, against the running stack:
    docker exec cti_web python scripts/migrate_workflow_config_version_unique.py
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLE = "agentic_workflow_config"
INDEX_NAME = "uq_agentic_workflow_config_version"
SEQUENCE_NAME = "agentic_workflow_config_version_seq"


def _resolve_database_url() -> str | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


def _renumber_duplicate_versions(conn) -> int:
    """Give every colliding row after the first a fresh version above the maximum."""
    duplicates = conn.execute(
        text(f"""
            SELECT id, version
            FROM (
                SELECT id, version,
                       row_number() OVER (PARTITION BY version ORDER BY id) AS position
                FROM {TABLE}
            ) ranked
            WHERE position > 1
            ORDER BY id
        """)
    ).fetchall()

    if not duplicates:
        logger.info("No duplicate version numbers to renumber")
        return 0

    next_version = int(conn.execute(text(f"SELECT COALESCE(max(version), 0) FROM {TABLE}")).scalar() or 0) + 1
    logger.info("Renumbering %d duplicate rows, starting at version %d", len(duplicates), next_version)

    for row_id, old_version in duplicates:
        conn.execute(
            text(f"""
                UPDATE {TABLE}
                SET version = :new_version,
                    description = COALESCE(description || ' ', '')
                                  || '[renumbered from duplicate version ' || :old_version || ']'
                WHERE id = :row_id
            """),
            {"new_version": next_version, "old_version": old_version, "row_id": row_id},
        )
        next_version += 1

    return len(duplicates)


def run_migration() -> bool:
    database_url = _resolve_database_url()
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            before = conn.execute(text(f"SELECT count(*), count(DISTINCT version) FROM {TABLE}")).fetchone()
            logger.info("Before: %d rows, %d distinct versions", before[0], before[1])

            renumbered = _renumber_duplicate_versions(conn)

            index_exists = conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE tablename = :t AND indexname = :i"),
                {"t": TABLE, "i": INDEX_NAME},
            ).fetchone()
            if index_exists:
                logger.info("Unique index %s already exists", INDEX_NAME)
            else:
                logger.info("Creating unique index %s", INDEX_NAME)
                conn.execute(text(f"CREATE UNIQUE INDEX {INDEX_NAME} ON {TABLE} (version)"))

            sequence_exists = conn.execute(
                text("SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = :s"),
                {"s": SEQUENCE_NAME},
            ).fetchone()
            if sequence_exists:
                logger.info("Sequence %s already exists", SEQUENCE_NAME)
            else:
                logger.info("Creating sequence %s", SEQUENCE_NAME)
                conn.execute(text(f"CREATE SEQUENCE {SEQUENCE_NAME} OWNED BY {TABLE}.version"))

            # Seed (or re-seed) above the current maximum. Safe to repeat: setval to
            # the live maximum is exactly where a fresh sequence would need to be.
            max_version = int(conn.execute(text(f"SELECT COALESCE(max(version), 0) FROM {TABLE}")).scalar() or 0)
            conn.execute(
                text("SELECT setval(:s, :v, true)"),
                {"s": SEQUENCE_NAME, "v": max(max_version, 1)},
            )
            logger.info("Sequence %s seeded at %d", SEQUENCE_NAME, max_version)

            conn.commit()

            after = conn.execute(text(f"SELECT count(*), count(DISTINCT version) FROM {TABLE}")).fetchone()
            logger.info("After: %d rows, %d distinct versions (renumbered %d)", after[0], after[1], renumbered)
            if after[0] != after[1]:
                logger.error("Version numbers are still not unique -- migration did not converge")
                return False

            logger.info("Migration completed successfully")
            return True

    except Exception as exc:
        logger.error("Migration failed: %s", exc, exc_info=True)
        return False


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
