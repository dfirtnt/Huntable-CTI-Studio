#!/usr/bin/env python3
"""
Update expected_count for a specific article in SubagentEvaluationTable records.

Usage:
    python scripts/update_article_expected_count.py --article-id 1484 --expected-count 2 --subagent cmdline
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import SubagentEvaluationTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def update_article_expected_count(article_id: int, expected_count: int, subagent_name: str = "cmdline"):
    """
    Update expected_count for all SubagentEvaluationTable records matching article_id and subagent_name.
    Recalculates score = actual_count - expected_count for completed records.
    """
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        # Find all eval records for this article and subagent
        eval_records = (
            db_session.query(SubagentEvaluationTable)
            .filter(
                SubagentEvaluationTable.article_id == article_id, SubagentEvaluationTable.subagent_name == subagent_name
            )
            .all()
        )

        if not eval_records:
            logger.warning(f"No SubagentEvaluation records found for article_id={article_id}, subagent={subagent_name}")
            return 0

        updated_count = 0
        for record in eval_records:
            old_expected = record.expected_count
            record.expected_count = expected_count

            # Recalculate score if actual_count is set
            if record.actual_count is not None:
                record.score = record.actual_count - expected_count
                logger.info(
                    f"Updated record {record.id}: "
                    f"expected_count {old_expected} -> {expected_count}, "
                    f"actual_count={record.actual_count}, "
                    f"score={record.score}"
                )
            else:
                logger.info(
                    f"Updated record {record.id}: "
                    f"expected_count {old_expected} -> {expected_count} "
                    f"(actual_count not set yet)"
                )

            updated_count += 1

        db_session.commit()
        logger.info(f"✅ Updated {updated_count} SubagentEvaluation record(s) for article {article_id}")
        return updated_count

    except Exception as e:
        logger.error(f"Error updating expected_count: {e}", exc_info=True)
        db_session.rollback()
        raise
    finally:
        db_session.close()


def main():
    parser = argparse.ArgumentParser(description="Update expected_count for article evaluation records")
    parser.add_argument("--article-id", type=int, required=True, help="Article ID to update")
    parser.add_argument("--expected-count", type=int, required=True, help="New expected_count value")
    parser.add_argument("--subagent", type=str, default="cmdline", help="Subagent name (default: cmdline)")

    args = parser.parse_args()

    try:
        count = update_article_expected_count(
            article_id=args.article_id, expected_count=args.expected_count, subagent_name=args.subagent
        )
        sys.exit(0 if count > 0 else 1)
    except Exception as e:
        logger.error(f"Failed to update expected_count: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
