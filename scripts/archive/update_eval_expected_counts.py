#!/usr/bin/env python3
"""
Bulk update expected_count for any subagent evaluation from config/eval_articles.yaml.
Updates all SubagentEvaluationTable records and recalculates scores.

Usage:
    python3 scripts/update_eval_expected_counts.py --subagent process_lineage
    python3 scripts/update_eval_expected_counts.py --subagent cmdline
"""

import argparse
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SubagentEvaluationTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def resolve_article_id_from_url(url: str, db_session) -> int:
    """Resolve article ID from URL."""
    parsed = urlparse(url)
    if parsed.netloc in ("127.0.0.1:8001", "localhost:8001", "127.0.0.1", "localhost"):
        match = re.match(r"/articles/(\d+)", parsed.path)
        if match:
            article_id = int(match.group(1))
            article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if article:
                return article.id

    article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url == url).first()
    if article:
        return article.id

    from urllib.parse import urlunparse

    parsed = urlparse(url)
    normalized_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url.like(f"{normalized_url}%")).first()
    if article:
        return article.id

    return None


def update_expected_counts(subagent_name: str) -> int:
    """Update all expected counts for *subagent_name* from YAML config.
    Also deletes eval records for articles no longer in the config.
    """
    config_path = project_root / "config" / "eval_articles.yaml"

    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return 0

    with open(config_path) as f:
        config = yaml.safe_load(f)

    subagent_articles = config.get("subagents", {}).get(subagent_name, [])
    if not subagent_articles:
        logger.warning(f"No entries found for subagent '{subagent_name}' in {config_path}")
        return 0

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    total_updated = 0
    total_deleted = 0

    try:
        config_urls = {a["url"] for a in subagent_articles if a and a.get("url")}

        all_eval_records = (
            db_session.query(SubagentEvaluationTable)
            .filter(SubagentEvaluationTable.subagent_name == subagent_name)
            .all()
        )

        updated_record_ids: set[int] = set()

        for article_def in subagent_articles:
            url = article_def.get("url")
            expected_count = article_def.get("expected_count")

            if not url:
                logger.warning(f"Skipping entry without URL: {article_def}")
                continue

            if expected_count is None:
                logger.warning(f"Skipping entry without expected_count: {url}")
                continue

            article_id = resolve_article_id_from_url(url, db_session)

            if article_id is None:
                logger.warning(f"Could not resolve article ID for URL: {url}")
                eval_records = (
                    db_session.query(SubagentEvaluationTable)
                    .filter(
                        SubagentEvaluationTable.article_url == url,
                        SubagentEvaluationTable.subagent_name == subagent_name,
                    )
                    .all()
                )
            else:
                eval_records = (
                    db_session.query(SubagentEvaluationTable)
                    .filter(
                        SubagentEvaluationTable.article_id == article_id,
                        SubagentEvaluationTable.subagent_name == subagent_name,
                    )
                    .all()
                )

            if not eval_records:
                logger.info(f"No eval records found for URL: {url} (article_id: {article_id})")
                continue

            for record in eval_records:
                old_expected = record.expected_count
                record.expected_count = expected_count

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

        for record in all_eval_records:
            if record.id not in updated_record_ids and record.article_url not in config_urls:
                logger.info(
                    f"Deleting eval record {record.id} for article {record.article_id} "
                    f"(URL: {record.article_url}) - no longer in config"
                )
                db_session.delete(record)
                total_deleted += 1

        db_session.commit()
        logger.info(f"✅ Updated {total_updated} SubagentEvaluation record(s) for {subagent_name}")
        if total_deleted > 0:
            logger.info(f"✅ Deleted {total_deleted} SubagentEvaluation record(s) no longer in config")
        return total_updated + total_deleted

    except Exception as e:
        logger.error(f"Error updating expected counts: {e}", exc_info=True)
        db_session.rollback()
        raise
    finally:
        db_session.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk update SubagentEvaluation expected_count from eval_articles.yaml"
    )
    parser.add_argument(
        "--subagent",
        required=True,
        help="Subagent name to update (e.g. process_lineage, cmdline, hunt_queries)",
    )
    args = parser.parse_args()

    try:
        count = update_expected_counts(args.subagent)
        sys.exit(0 if count >= 0 else 1)
    except Exception as e:
        logger.error(f"Failed to update expected counts: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
