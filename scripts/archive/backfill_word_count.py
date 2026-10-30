#!/usr/bin/env python3
"""
Backfill articles.word_count for rows left at the column default of 0.

Root cause (see AGENTS.md-adjacent memory / commit history on
src/services/deduplication.py): create_article_with_deduplication built the
ArticleTable insert without a word_count key, so every article ingested
through the async Celery pipeline got word_count=0 even though its content
was fully populated. That insert path is now fixed; this script backfills
the rows created before the fix by recomputing word_count from the stored
(already-cleaned) content column, matching src/core/processor.py's method
exactly: len(content.split()).

Eval-articles rows (source identifier == EVAL_SOURCE_IDENTIFIER) are always
skipped -- those rows are protected against mutation.

Usage:
    python3 scripts/backfill_word_count.py --dry-run
    python3 scripts/backfill_word_count.py --limit 50 --dry-run
    python3 scripts/backfill_word_count.py
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SourceTable
from src.models.source import EVAL_SOURCE_IDENTIFIER

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def backfill(dry_run: bool = False, limit: int | None = None) -> None:
    db = DatabaseManager()
    session = db.get_session()
    try:
        query = (
            session.query(ArticleTable)
            .join(SourceTable, ArticleTable.source_id == SourceTable.id)
            .filter(ArticleTable.word_count == 0)
            .filter(SourceTable.identifier != EVAL_SOURCE_IDENTIFIER)
            .order_by(ArticleTable.id)
        )
        if limit:
            query = query.limit(limit)

        rows = query.all()
        logger.info(f"Found {len(rows)} candidate rows (word_count=0, non-eval)")

        updated = 0
        skipped_still_zero = 0
        pending = 0

        for row in rows:
            new_word_count = len((row.content or "").split())
            if new_word_count == 0:
                skipped_still_zero += 1
                continue

            if not dry_run:
                row.word_count = new_word_count
                session.add(row)
                pending += 1
                if pending >= BATCH_SIZE:
                    session.commit()
                    pending = 0

            updated += 1

        if not dry_run and pending:
            session.commit()

        logger.info(
            f"{'[DRY RUN] Would update' if dry_run else 'Updated'}={updated}, "
            f"skipped_still_zero(no real content)={skipped_still_zero}"
        )

    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to process")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run, limit=args.limit)
