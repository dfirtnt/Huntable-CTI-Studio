#!/usr/bin/env python3
"""
Bulk update expected_count for process_lineage (proctree) evaluations from config/eval_articles.yaml.
Updates all SubagentEvaluationTable records and recalculates scores.

Usage:
    python3 scripts/update_proctree_expected_counts.py
"""

import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SubagentEvaluationTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def resolve_article_id_from_url(url: str, db_session) -> int:
    """Resolve article ID from URL."""
    # Handle localhost/article ID URLs
    parsed = urlparse(url)
    if parsed.netloc in ("127.0.0.1:8001", "localhost:8001", "127.0.0.1", "localhost"):
        match = re.match(r"/articles/(\d+)", parsed.path)
        if match:
            article_id = int(match.group(1))
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if article:
                return article.id

    # Try exact match on canonical_url
    article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url == url).first()
    if article:
        return article.id

    # Try partial match (normalize URL)
    from urllib.parse import urlunparse

    parsed = urlparse(url)
    normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url.like(f"{normalized_url}%")).first()
    if article:
        return article.id

    return None


def update_proctree_expected_counts():
    """Update all process_lineage expected counts from YAML config.
    Also deletes eval records for articles no longer in the config.
    """
    config_path = project_root / "config" / "eval_articles.yaml"

    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 0

    with open(config_path) as f:
        config = yaml.safe_load(f)

    process_lineage_articles = config.get("subagents", {}).get("process_lineage", [])

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    total_updated = 0
    total_deleted = 0

    try:
        # Build set of URLs from config
        config_urls = set()
        for article_def in process_lineage_articles:
            url = article_def.get("url")
            if url:
                config_urls.add(url)

        # Get all existing eval records for process_lineage
        all_eval_records = (
            db_session.query(SubagentEvaluationTable)
            .filter(SubagentEvaluationTable.subagent_name == "process_lineage")
            .all()
        )

        # Track which records we've updated
        updated_record_ids = set()

        # Update records that are in config
        for article_def in process_lineage_articles:
            url = article_def.get("url")
            expected_count = article_def.get("expected_count")

            if not url:
                logger.warning(f"Skipping entry without URL: {article_def}")
                continue

            if expected_count is None:
                logger.warning(f"Skipping entry without expected_count: {url}")
                continue

            # Resolve article ID
            article_id = resolve_article_id_from_url(url, db_session)

            if article_id is None:
                logger.warning(f"Could not resolve article ID for URL: {url}")
                # Try updating by URL directly
                eval_records = (
                    db_session.query(SubagentEvaluationTable)
                    .filter(
                        SubagentEvaluationTable.article_url == url,
                        SubagentEvaluationTable.subagent_name == "process_lineage",
                    )
                    .all()
                )
            else:
                # Update by article_id
                eval_records = (
                    db_session.query(SubagentEvaluationTable)
                    .filter(
                        SubagentEvaluationTable.article_id == article_id,
                        SubagentEvaluationTable.subagent_name == "process_lineage",
                    )
                    .all()
                )

            if not eval_records:
                logger.info(f"No eval records found for URL: {url} (article_id: {article_id})")
                continue

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

                updated_record_ids.add(record.id)
                total_updated += 1

        # Delete records that are no longer in config
        for record in all_eval_records:
            if record.id not in updated_record_ids and record.article_url not in config_urls:
                logger.info(
                    f"Deleting eval record {record.id} for article {record.article_id} (URL: {record.article_url}) - no longer in config"
                )
                db_session.delete(record)
                total_deleted += 1

        db_session.commit()
        logger.info(f"✅ Updated {total_updated} SubagentEvaluation record(s) for process_lineage")
        if total_deleted > 0:
            logger.info(f"✅ Deleted {total_deleted} SubagentEvaluation record(s) no longer in config")
        return total_updated + total_deleted

    except Exception as e:
        logger.error(f"Error updating expected counts: {e}", exc_info=True)
        db_session.rollback()
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    try:
        count = update_proctree_expected_counts()
        sys.exit(0 if count > 0 else 1)
    except Exception as e:
        logger.error(f"Failed to update expected counts: {e}")
        sys.exit(1)
