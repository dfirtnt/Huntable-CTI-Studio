#!/usr/bin/env python3
"""Migration: drop confirmed-dead dormant subsystems (2026-08-10 audit).

Why
---
A system-health review (Todoist 6h77r89HmgXhXhxV) found 8 tables/subsystems
either always empty or dormant for months. Investigation classified each as
deprecated-by-design (zero write path anywhere in the codebase, confirmed by
grep + import trace) versus genuinely unwired. This migration removes the
confirmed-dead ones plus finishes an earlier incomplete cleanup:

- ``sources.healing_exhausted`` / ``sources.healing_attempts`` / ``healing_events``:
  dropped from ``models.py`` in commit 4aae21e3 (2026-05-02) and a drop migration
  was written, but that migration script was deleted in a later "purge stale
  scripts" pass (e48b9246, 2026-05-06) before it was ever run against prod. The
  columns and table have been live-orphaned since. Also removes the 7
  ``SOURCE_HEALING_*`` app_settings keys (including a leaked-looking
  ``SOURCE_HEALING_API_KEY`` holding the literal string ``'X-API-Key'``).
- ``chat_logs``: the ``/chat`` RAG Search UI was fully removed (``deprecate/rag-chat``
  branch); zero code references outside the ORM model.
- ``simhash_buckets``: dedup moved onto ``articles.simhash`` / ``articles.simhash_bucket``
  columns; the table has never had an INSERT path.
- ``article_sigma_matches``: only write path was ``SigmaMatchingService.store_match``,
  called solely from the legacy manual ``/generate-sigma`` endpoint's now-removed
  persistence step and a CLI ``--save`` flag; the live autonomous workflow never
  wrote to it.
- ``eval_runs`` / ``eval_preset_snapshots``: scaffolded for a Langfuse-experiment-backed
  eval-run tracker that was never implemented (Langfuse itself is used elsewhere,
  this specific pair of tables never got a writer).
- ``agent_evaluations``: superseded by ``subagent_evaluations`` / ``sigma_evaluations``.
  Backed an orphaned ``/evaluations`` page tree (unreachable from nav) that has been
  removed in the same change; the table itself never had a writer.
- ``url_tracking``: HTTP conditional-GET (etag/last-modified) caching was scaffolded
  (schema + retention policy) but the fetch/scraper code was never wired to populate it.
- ``observable_model_metrics`` / ``observable_evaluation_failures``: a complete,
  working pipeline (``src/services/observable_evaluation/``) behind a live API
  router, but with no UI trigger anywhere -- built, never operationalized. Removed
  per operator decision alongside the rest of this pass.

Idempotent: every DROP is guarded by an existence check via information_schema /
to_regclass, and app_settings deletes are plain DELETE ... WHERE key IN (...) --
safe to re-run.

Ordering
--------
No FK dependencies between the dropped objects and anything retained. Order
within this script does not matter, but columns are dropped before their
parent table in the (unrelated) case where both exist.

Usage
-----
    python scripts/migrate_drop_dormant_subsystems.py
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLES_TO_DROP = (
    "healing_events",
    "chat_logs",
    "simhash_buckets",
    "article_sigma_matches",
    "eval_runs",
    "eval_preset_snapshots",
    "agent_evaluations",
    "url_tracking",
    "observable_model_metrics",
    "observable_evaluation_failures",
)

SOURCES_COLUMNS_TO_DROP = ("healing_exhausted", "healing_attempts")

SOURCE_HEALING_SETTINGS_KEYS = (
    "SOURCE_HEALING_ENABLED",
    "SOURCE_HEALING_THRESHOLD",
    "SOURCE_HEALING_MAX_ATTEMPTS",
    "SOURCE_HEALING_PROVIDER",
    "SOURCE_HEALING_MODEL",
    "SOURCE_HEALING_CHECK_INTERVAL",
    "SOURCE_HEALING_API_KEY",
)


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
            for column in SOURCES_COLUMNS_TO_DROP:
                exists = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'sources' AND column_name = :col"
                    ),
                    {"col": column},
                ).fetchone()
                if exists:
                    logger.info(f"Dropping sources.{column}")
                    conn.execute(text(f"ALTER TABLE sources DROP COLUMN {column}"))
                else:
                    logger.info(f"sources.{column} already absent, skipping")

            for table in TABLES_TO_DROP:
                table_exists = conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}).scalar()
                if table_exists:
                    logger.info(f"Dropping {table} table")
                    conn.execute(text(f"DROP TABLE {table} CASCADE"))
                else:
                    logger.info(f"{table} table already absent, skipping")

            result = conn.execute(
                text("DELETE FROM app_settings WHERE key = ANY(:keys)"),
                {"keys": list(SOURCE_HEALING_SETTINGS_KEYS)},
            )
            logger.info(f"Deleted {result.rowcount} SOURCE_HEALING_* app_settings row(s)")

            conn.commit()
            logger.info("Migration completed")
            return True
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
