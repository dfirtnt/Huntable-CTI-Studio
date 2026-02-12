#!/usr/bin/env python3
"""
Dump eval article snapshots from the database into static JSON files.

Reads config/eval_articles.yaml, resolves each URL to an article in the DB,
and writes config/eval_articles_data/{subagent}/articles.json with
url, title, content, optional filtered_content, and expected_count.

Run when the DB contains the eval articles (e.g. before rehydration); then
commit the generated JSON files so evals work after rehydration.

Usage:
    python3 scripts/dump_eval_articles_static.py [--no-filter]
    # With venv:
    .venv/bin/python scripts/dump_eval_articles_static.py

Options:
    --no-filter    Do not compute filtered_content (faster; evals can use content).
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import yaml

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager  # noqa: E402
from src.database.models import ArticleTable  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CONFIG_EVAL_ARTICLES = project_root / "config" / "eval_articles.yaml"
DATA_DIR = project_root / "config" / "eval_articles_data"


def _resolve_articles_by_urls(db_session, urls: list[str]) -> dict[str, int]:
    """Resolve URLs to article IDs (same contract as evaluation_api.resolve_articles_by_urls)."""
    if not urls:
        return {}
    result: dict[str, int] = {}
    localhost_ids: list[int] = []
    localhost_url_to_id: dict[str, int] = {}
    external_urls: list[str] = []
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.netloc in ("127.0.0.1:8001", "localhost:8001", "127.0.0.1", "localhost"):
            match = re.match(r"/articles/(\d+)", parsed.path)
            if match:
                aid = int(match.group(1))
                localhost_ids.append(aid)
                localhost_url_to_id[url] = aid
        else:
            external_urls.append(url)

    if localhost_ids:
        found = db_session.query(ArticleTable.id).filter(ArticleTable.id.in_(localhost_ids)).all()
        found_ids = {r[0] for r in found}
        for url, aid in localhost_url_to_id.items():
            if aid in found_ids:
                result[url] = aid

    if external_urls:
        rows = (
            db_session.query(ArticleTable.canonical_url, ArticleTable.id)
            .filter(ArticleTable.canonical_url.in_(external_urls))
            .all()
        )
        for canonical_url, aid in rows:
            result[canonical_url] = aid

        missing = [u for u in external_urls if u not in result]
        for url in missing:
            parsed = urlparse(url)
            normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            if normalized == url:
                continue
            article = db_session.query(ArticleTable).filter(ArticleTable.canonical_url.like(f"{normalized}%")).first()
            if article:
                result[url] = article.id

    return result


def get_filtered_content(article: ArticleTable, junk_filter_threshold: float = 0.8) -> str:
    """Apply junk filter to article content."""
    from src.utils.content_filter import ContentFilter

    content_filter = ContentFilter()
    hunt_score = article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0
    filter_result = content_filter.filter_content(
        article.content, min_confidence=junk_filter_threshold, hunt_score=hunt_score, article_id=article.id
    )
    return filter_result.filtered_content or article.content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump eval articles from DB to static JSON for rehydration-safe evals."
    )
    parser.add_argument("--no-filter", action="store_true", help="Do not compute filtered_content")
    args = parser.parse_args()

    if not CONFIG_EVAL_ARTICLES.exists():
        logger.error("Config not found: %s", CONFIG_EVAL_ARTICLES)
        sys.exit(1)

    with open(CONFIG_EVAL_ARTICLES) as f:
        config = yaml.safe_load(f) or {}
    subagents = config.get("subagents", {})
    if not subagents:
        logger.warning("No subagents in config")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    try:
        for subagent_key, articles_def in subagents.items():
            if not isinstance(articles_def, list) or not articles_def:
                continue
            urls = [a.get("url") for a in articles_def if a.get("url")]
            if not urls:
                continue
            url_to_expected = {a["url"]: a.get("expected_count", 0) for a in articles_def if a.get("url")}
            url_to_id = _resolve_articles_by_urls(db_session, urls)
            out_articles: list[dict] = []
            for url in urls:
                article_id = url_to_id.get(url)
                if not article_id:
                    logger.warning("Article not found for URL: %s", url[:60])
                    continue
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not article:
                    continue
                entry: dict = {
                    "url": url,
                    "title": article.title or "",
                    "content": article.content or "",
                    "expected_count": url_to_expected.get(url, 0),
                }
                if not args.no_filter:
                    try:
                        entry["filtered_content"] = get_filtered_content(article)
                    except Exception as e:
                        logger.warning("Filter failed for article %s: %s", article_id, e)
                        entry["filtered_content"] = article.content or ""
                out_articles.append(entry)

            subdir = DATA_DIR / subagent_key
            subdir.mkdir(parents=True, exist_ok=True)
            out_path = subdir / "articles.json"
            with open(out_path, "w") as f:
                json.dump(out_articles, f, indent=2)
            logger.info("Wrote %d articles to %s", len(out_articles), out_path)
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
