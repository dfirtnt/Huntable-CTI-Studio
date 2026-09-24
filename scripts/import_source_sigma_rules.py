#!/usr/bin/env python3
"""Backfill publisher-authored Sigma rules from stored article content.

The default is a read-only scan. ``--apply`` inserts queue rows and therefore
requires the source-provenance migration to have already been applied.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.models import ArticleTable  # noqa: E402
from src.services.source_sigma_import_service import (  # noqa: E402
    detect_license,
    import_source_sigma_rules,
    scan_sigma_rules_with_diagnostics,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run(*, apply: bool = False, article_id: int | None = None, repo_path: str | None = None) -> bool:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    session = sessionmaker(bind=create_engine(sync_url))()
    try:
        query = session.query(ArticleTable)
        if article_id is not None:
            query = query.filter(ArticleTable.id == article_id)
        articles = query.order_by(ArticleTable.id).all()
        article_count = 0
        candidate_count = 0
        imported = 0
        duplicates = 0
        rejected = 0
        destination = Path(repo_path or os.getenv("SIGMA_REPO_PATH") or "sigma-repo")
        if not destination.is_absolute():
            destination = (Path(__file__).resolve().parents[1] / destination).resolve()
        for article in articles:
            scan = scan_sigma_rules_with_diagnostics(article.content)
            candidates = scan.candidates
            if not candidates and not scan.rejections:
                continue
            article_count += 1
            candidate_count += len(candidates)
            if not apply:
                rejected += len(scan.rejections)
                licenses: dict[str, int] = {}
                for candidate in candidates:
                    license_id = detect_license(article.content, candidate).license_id or "NO-LICENSE"
                    licenses[license_id] = licenses.get(license_id, 0) + 1
                logger.info(
                    "article=%s candidates=%d rejected=%d licenses=%s",
                    article.id,
                    len(candidates),
                    len(scan.rejections),
                    licenses,
                )
                for rejection in scan.rejections:
                    logger.info(
                        "article=%s rejected_span=%d:%d reason=%s",
                        article.id,
                        rejection.start,
                        rejection.end,
                        rejection.reason,
                    )
                continue
            result = import_source_sigma_rules(session, article, destination, commit=False)
            imported += result.imported
            duplicates += result.duplicates
            rejected += result.rejected
        if apply:
            session.commit()
        logger.info(
            "articles=%d candidates=%d imported=%d duplicates=%d rejected=%d mode=%s",
            article_count,
            candidate_count,
            imported,
            duplicates,
            rejected,
            "apply" if apply else "dry-run",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.error("Source Sigma backfill failed: %s", exc)
        return False
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Insert queue rows; default is read-only.")
    parser.add_argument("--article-id", type=int, help="Limit scan/import to one article.")
    parser.add_argument("--repo-path", help="Destination rules repo used for license policy evaluation.")
    args = parser.parse_args()
    return 0 if run(apply=args.apply, article_id=args.article_id, repo_path=args.repo_path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
