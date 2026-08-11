#!/usr/bin/env python3
"""Backfill immutable execution-snapshot references without deleting legacy JSON.

Report-only by default. ``--apply`` creates content-addressed rows for complete
legacy snapshots and sets ``config_snapshot_id``; it deliberately leaves the
inline JSON intact so rollback is possible until a separately approved purge.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable
from src.services.execution_snapshot_store import attach_snapshot
from src.services.workflow_config_snapshot import snapshot_is_complete


def migrate(apply: bool, batch_size: int = 100) -> tuple[int, int, int]:
    """Backfill in bounded batches so JSONB-heavy execution tables stay safe."""
    db = DatabaseManager()
    with db.get_session() as session:
        pending = session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.config_snapshot_id.is_(None)
        )
        total = pending.count()
        eligible = 0
        legacy = 0
        last_id = 0

        while True:
            executions = (
                session.query(AgenticWorkflowExecutionTable)
                .filter(
                    AgenticWorkflowExecutionTable.config_snapshot_id.is_(None),
                    AgenticWorkflowExecutionTable.id > last_id,
                )
                .order_by(AgenticWorkflowExecutionTable.id)
                .limit(batch_size)
                .all()
            )
            if not executions:
                break
            last_id = executions[-1].id

            for execution in executions:
                if not snapshot_is_complete(execution.config_snapshot):
                    legacy += 1
                    continue
                eligible += 1
                if apply:
                    attach_snapshot(session, execution, execution.config_snapshot)
            if apply:
                session.commit()
                session.expire_all()

        return total, eligible, legacy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Backfill references; never deletes inline JSON.")
    parser.add_argument("--batch-size", type=int, default=100, help="Rows loaded per batch (default: 100).")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    total, eligible, legacy = migrate(args.apply, args.batch_size)
    verb = "Backfilled" if args.apply else "Would backfill"
    print(f"{verb} {eligible} complete snapshots out of {total} legacy executions.")
    print(f"Retained {legacy} incomplete legacy snapshots without a reference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
