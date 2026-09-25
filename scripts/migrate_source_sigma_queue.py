#!/usr/bin/env python3
"""Add source-provided Sigma provenance columns and backfill existing rows.

Default mode is a read-only schema/data report. Pass ``--apply`` to execute the
transactional migration. Applying this script is an operator-approved deployment
step; application startup never silently performs it.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_SQL = """
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS rule_origin VARCHAR(50);
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_rule_id VARCHAR(255);
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_content_sha256 VARCHAR(64);
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_extraction_start INTEGER;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_extraction_end INTEGER;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS declared_license VARCHAR(100);
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS license_evidence TEXT;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS license_evidence_start INTEGER;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS license_evidence_end INTEGER;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS attribution TEXT;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_permission_granted_by VARCHAR(255);
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_permission_basis TEXT;
ALTER TABLE sigma_rule_queue ADD COLUMN IF NOT EXISTS source_permission_granted_at TIMESTAMP;
UPDATE sigma_rule_queue SET rule_origin = 'generated' WHERE rule_origin IS NULL;
ALTER TABLE sigma_rule_queue ALTER COLUMN rule_origin SET DEFAULT 'generated';
ALTER TABLE sigma_rule_queue ALTER COLUMN rule_origin SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_sigma_rule_queue_rule_origin ON sigma_rule_queue (rule_origin);
CREATE INDEX IF NOT EXISTS ix_sigma_rule_queue_source_content_sha256 ON sigma_rule_queue (source_content_sha256);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sigma_queue_source_url_rule_id
  ON sigma_rule_queue (source_url, source_rule_id)
  WHERE rule_origin = 'source_provided' AND source_rule_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sigma_queue_source_content_sha256
  ON sigma_rule_queue (source_content_sha256)
  WHERE rule_origin = 'source_provided' AND source_content_sha256 IS NOT NULL;
"""


def run_migration(database_url: str, *, apply: bool = False) -> bool:
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema=current_schema() AND table_name='sigma_rule_queue'"
                    )
                )
            }
            existing_rows = conn.execute(text("SELECT count(*) FROM sigma_rule_queue")).scalar_one()
            missing = [
                name
                for name in (
                    "rule_origin",
                    "source_url",
                    "source_rule_id",
                    "source_content_sha256",
                    "declared_license",
                    "attribution",
                )
                if name not in columns
            ]
            logger.info("sigma_rule_queue rows=%d; missing core columns=%s", existing_rows, missing or "none")
            if not apply:
                logger.info("Dry-run only — no schema or rows changed. Re-run with --apply to commit.")
                return True
            conn.rollback()
            with conn.begin():
                for statement in MIGRATION_SQL.split(";"):
                    if statement.strip():
                        conn.execute(text(statement))
            logger.info("Migration applied; existing rows are rule_origin=generated.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Migration failed: %s", exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the migration; default is dry-run.")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return 1
    return 0 if run_migration(database_url, apply=args.apply) else 1


if __name__ == "__main__":
    raise SystemExit(main())
