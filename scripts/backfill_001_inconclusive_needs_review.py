#!/usr/bin/env python3
"""
Backfill (todo 001, C1+C2): relabel legacy "inconclusive" SigmaQueue rows.

Before the evidence columns existed, the novelty comparator collapsed
"evaluated N candidates, found 0 behavioral matches" into max_similarity=0.0
with empty similarity_scores -- indistinguishable from a genuinely-scored 0.0.
~86% of the queue is this false-novel state.

This script relabels rows matching that legacy *inconclusive signature*:

    status = 'pending'
    AND max_similarity = 0.0
    AND similarity_scores is empty ([] / null / None)
    AND behavioral_matches_found IS NULL   (idempotency: untouched legacy rows)

to:

    status                 = 'needs_review'
    max_similarity         = NULL          (UI shows "-", not a fake 0.0%)
    behavioral_matches_found  = 0           (matches the workflow's new write;
                                             also stops the C1 recompute guard
                                             from thrashing the row back to 0.0)
    total_candidates_evaluated = NULL       (genuinely unknown for legacy rows)

A genuinely-scored low-similarity rule has NON-empty similarity_scores, so it
is excluded -- the heuristic targets only the inconclusive signature.

SAFETY: dry-run by default. ``--apply`` is required to write. Before any write
it snapshots every affected row to output/backfill_001_rollback_<ts>.json, and
``--rollback <file>`` restores exactly from such a snapshot.

Usage:
    python3 scripts/backfill_001_inconclusive_needs_review.py            # dry-run
    python3 scripts/backfill_001_inconclusive_needs_review.py --apply     # write
    python3 scripts/backfill_001_inconclusive_needs_review.py --rollback output/backfill_001_rollback_YYYYMMDD_HHMMSS.json
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleQueueTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _is_empty_scores(value) -> bool:
    """True when similarity_scores carries no entries (None / [] / 'null')."""
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    if isinstance(value, str):
        return value.strip() in ("", "[]", "null")
    return False


def _select_candidates(session):
    """Legacy inconclusive signature. Coarse filter in SQL, exact check in Python
    (similarity_scores is JSONB; emptiness is clearest in Python)."""
    rows = (
        session.query(SigmaRuleQueueTable)
        .filter(
            SigmaRuleQueueTable.status == "pending",
            SigmaRuleQueueTable.max_similarity == 0.0,
            SigmaRuleQueueTable.behavioral_matches_found.is_(None),
        )
        .order_by(SigmaRuleQueueTable.id)
        .all()
    )
    return [r for r in rows if _is_empty_scores(r.similarity_scores)]


def backfill(apply: bool) -> None:
    db = DatabaseManager()
    session = db.get_session()
    try:
        candidates = _select_candidates(session)
        logger.info("Matched %d legacy inconclusive rows.", len(candidates))
        if not candidates:
            logger.info("Nothing to do (idempotent: already relabeled or none present).")
            return

        snapshot = [
            {
                "id": r.id,
                "status": r.status,
                "max_similarity": r.max_similarity,
                "behavioral_matches_found": r.behavioral_matches_found,
                "total_candidates_evaluated": r.total_candidates_evaluated,
            }
            for r in candidates
        ]

        if not apply:
            logger.info("DRY-RUN. Re-run with --apply to write. Sample (up to 10):")
            for s in snapshot[:10]:
                logger.info("  queue #%s status=%s max_sim=%s", s["id"], s["status"], s["max_similarity"])
            logger.info("DRY-RUN: %d rows WOULD be relabeled to needs_review.", len(snapshot))
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rollback_path = OUTPUT_DIR / f"backfill_001_rollback_{ts}.json"
        rollback_path.write_text(json.dumps(snapshot, indent=2))
        logger.info("Rollback snapshot written: %s", rollback_path)

        for r in candidates:
            r.status = "needs_review"
            r.max_similarity = None
            r.behavioral_matches_found = 0
            r.total_candidates_evaluated = None
        session.commit()
        logger.info("Relabeled %d rows -> needs_review. Rollback: %s", len(candidates), rollback_path)
    except Exception:
        session.rollback()
        logger.exception("Backfill failed; transaction rolled back.")
        raise
    finally:
        session.close()


def rollback(snapshot_file: str) -> None:
    data = json.loads(Path(snapshot_file).read_text())
    db = DatabaseManager()
    session = db.get_session()
    try:
        restored = 0
        for s in data:
            row = session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == s["id"]).first()
            if row is None:
                logger.warning("queue #%s no longer exists; skipping.", s["id"])
                continue
            row.status = s["status"]
            row.max_similarity = s["max_similarity"]
            row.behavioral_matches_found = s["behavioral_matches_found"]
            row.total_candidates_evaluated = s["total_candidates_evaluated"]
            restored += 1
        session.commit()
        logger.info("Restored %d rows from %s", restored, snapshot_file)
    except Exception:
        session.rollback()
        logger.exception("Rollback failed; transaction rolled back.")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--rollback", metavar="SNAPSHOT_JSON", help="Restore rows from a rollback snapshot file")
    args = parser.parse_args()
    if args.rollback:
        rollback(args.rollback)
    else:
        backfill(apply=args.apply)
