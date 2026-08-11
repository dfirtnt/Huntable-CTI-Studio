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


def migrate(apply: bool) -> tuple[int, int, int]:
    db = DatabaseManager()
    with db.get_session() as session:
        executions = (
            session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.config_snapshot_id.is_(None))
            .all()
        )
        eligible = [execution for execution in executions if snapshot_is_complete(execution.config_snapshot)]
        legacy = len(executions) - len(eligible)
        if apply:
            for execution in eligible:
                attach_snapshot(session, execution, execution.config_snapshot)
            session.commit()
        return len(executions), len(eligible), legacy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Backfill references; never deletes inline JSON.")
    args = parser.parse_args()
    total, eligible, legacy = migrate(args.apply)
    verb = "Backfilled" if args.apply else "Would backfill"
    print(f"{verb} {eligible} complete snapshots out of {total} legacy executions.")
    print(f"Retained {legacy} incomplete legacy snapshots without a reference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
