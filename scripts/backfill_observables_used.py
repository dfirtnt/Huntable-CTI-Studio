#!/usr/bin/env python3
"""
Backfill observables_used for pending SigmaQueue rules that are missing it.

Iterates all SigmaQueueTable rows with status='pending' where rule_metadata
lacks observables_used, fetches the linked extraction_result, runs the
inference logic from sigma_generation_service, and updates rule_metadata.

Usage:
    python3 scripts/backfill_observables_used.py [--dry-run] [--limit N]
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.models import AgenticWorkflowExecutionTable, SigmaQueueTable
from src.database.db_manager import DatabaseManager
from src.services.sigma_generation_service import _infer_observables_used

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def backfill(dry_run: bool = False, limit: int | None = None) -> None:
    db = DatabaseManager()
    session = db.get_session()
    try:
        query = (
            session.query(SigmaQueueTable)
            .filter(SigmaQueueTable.status == "pending")
            .order_by(SigmaQueueTable.id)
        )
        if limit:
            query = query.limit(limit)

        rows = query.all()
        logger.info(f"Found {len(rows)} pending rules to check")

        updated = 0
        skipped_already_set = 0
        skipped_no_exec = 0
        skipped_no_match = 0

        for row in rows:
            meta = row.rule_metadata or {}
            if meta.get("observables_used") is not None:
                skipped_already_set += 1
                continue

            # Fetch linked execution to get extraction_result
            exec_row = (
                session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == row.execution_id)
                .first()
            )
            if not exec_row or not exec_row.extraction_result:
                skipped_no_exec += 1
                continue

            extraction_result = exec_row.extraction_result
            if isinstance(extraction_result, str):
                try:
                    extraction_result = json.loads(extraction_result)
                except Exception:
                    skipped_no_exec += 1
                    continue

            rule_yaml = meta.get("detection") and json.dumps({"detection": meta["detection"]})
            if not rule_yaml:
                skipped_no_exec += 1
                continue

            # Build minimal YAML for inference (detection block only)
            import yaml
            try:
                rule_yaml_str = yaml.dump({"detection": meta["detection"]}, default_flow_style=False)
            except Exception:
                skipped_no_exec += 1
                continue

            matched = _infer_observables_used(rule_yaml_str, extraction_result)
            if matched is None:
                skipped_no_match += 1
                continue

            if not dry_run:
                meta["observables_used"] = matched
                meta["observables_used_inferred"] = True
                row.rule_metadata = meta
                session.add(row)

            updated += 1
            logger.info(
                f"{'[DRY RUN] Would update' if dry_run else 'Updated'} "
                f"rule {row.id} (exec {row.execution_id}): observables_used={matched}"
            )

        if not dry_run:
            session.commit()
            logger.info(f"Committed {updated} updates")

        logger.info(
            f"Done. Updated={updated}, already_set={skipped_already_set}, "
            f"no_exec={skipped_no_exec}, no_match={skipped_no_match}"
        )

    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to process")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run, limit=args.limit)
