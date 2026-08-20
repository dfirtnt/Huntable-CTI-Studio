#!/usr/bin/env python3
"""Migration: drop the ``sigma_evaluations`` table (2026-08-19 Sigma eval decommission).

Why
---
The Sigma eval scored generated Sigma rules against hand-authored ground truth,
reporting atom-level precision/recall. Operator review concluded the metric is
not defensible: precision is computed as ``fp = actual_atoms - expected_atoms``,
so any correct detection the ground-truth author did not happen to write down
scores identically to a hallucination. The benchmark therefore measures
resemblance to one analyst's rule set rather than detection quality, and is
capped at -- and penalizes exceeding -- that analyst's recall of their own
domain.

Every part of the system with a defensible ground truth already duplicated the
extractor evals (``subagent_evaluations``, Eval1/Eval2), and rule validity is
already enforced independently by ``SigmaGenerationService._validate_all_rules``
plus its Phase 3 repair loop. The remaining signal was the indefensible part, so
the subsystem was removed rather than expanded.

The table is dropped rather than retained because ``sigma_evaluations`` holds a
FK to ``agentic_workflow_executions`` with no ``ondelete`` clause, and
``data_retention_service._EXECUTION_REFERENCE_TABLES`` used the ORM model to
keep referenced executions from being purged. Retaining the rows while removing
the model would leave the retention job -- shared with article pruning and the
extractor evals -- to hit a FK violation on the first aged execution it tried to
purge.

Idempotent: the DROP is guarded by a ``to_regclass`` existence check, so this is
safe to re-run.

Usage
-----
    python scripts/migrate_drop_sigma_evaluations.py
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLE_TO_DROP = "sigma_evaluations"


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
            table_exists = conn.execute(
                text("SELECT to_regclass(:t)"), {"t": f"public.{TABLE_TO_DROP}"}
            ).scalar()
            if table_exists:
                row_count = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_TO_DROP}")).scalar()
                logger.info(f"Dropping {TABLE_TO_DROP} table ({row_count} row(s))")
                conn.execute(text(f"DROP TABLE {TABLE_TO_DROP} CASCADE"))
            else:
                logger.info(f"{TABLE_TO_DROP} table already absent, skipping")

            conn.commit()
            logger.info("Migration completed")
            return True
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
