"""
Seed eval articles from config/eval_articles_data into the database.

Used at web startup (after a fresh DB) and by scripts/seed_eval_articles_to_db.py
so eval articles are ingested and the regular workflow can process them.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SourceTable
from src.models.article import ArticleCreate
from src.utils.content import ContentCleaner

logger = logging.getLogger(__name__)

EVAL_SOURCE_IDENTIFIER = "eval_articles"
EVAL_SOURCE_NAME = "Eval Articles"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_or_create_eval_source(db_manager: DatabaseManager) -> int:
    """Get or create the eval_articles source; return source_id."""
    with db_manager.get_session() as session:
        source = session.query(SourceTable).filter(SourceTable.identifier == EVAL_SOURCE_IDENTIFIER).first()
        if source:
            return source.id
        # Insert directly so we don't depend on SourceCreate having check_frequency/lookback_days
        db_source = SourceTable(
            identifier=EVAL_SOURCE_IDENTIFIER,
            name=EVAL_SOURCE_NAME,
            url="https://config/eval_articles_data",
            rss_url=None,
            check_frequency=86400,
            lookback_days=365,
            active=False,
            config={},
        )
        session.add(db_source)
        session.commit()
        session.refresh(db_source)
        logger.info("Created eval_articles source id=%s", db_source.id)
        return db_source.id


def _load_articles_by_url(data_dir: Path) -> dict[str, dict]:
    """Load all articles from data_dir/*/articles.json; key by url (first wins)."""
    by_url: dict[str, dict] = {}
    if not data_dir.exists():
        return by_url
    for subdir in data_dir.iterdir():
        if not subdir.is_dir():
            continue
        articles_json = subdir / "articles.json"
        if not articles_json.exists():
            continue
        try:
            with open(articles_json) as f:
                articles = json.load(f)
        except Exception as e:
            logger.warning("Could not load %s: %s", articles_json, e)
            continue
        if not isinstance(articles, list):
            continue
        for entry in articles:
            url = entry.get("url")
            if not url or url in by_url:
                continue
            title = (entry.get("title") or "").strip() or "Untitled Article"
            content = entry.get("content") or ""
            by_url[url] = {"title": title, "content": content}
    return by_url


def run(project_root: Path | None = None) -> tuple[int, int]:
    """
    Seed eval articles from config/eval_articles_data into the DB.

    Returns:
        (created_count, error_count)
    """
    root = project_root or _project_root()
    data_dir = root / "config" / "eval_articles_data"
    data_dir_str = str(data_dir.resolve())
    exists = data_dir.exists()
    logger.info(
        "Eval articles seed: data_dir=%s exists=%s",
        data_dir_str,
        exists,
    )

    db_manager = DatabaseManager()
    source_id = _get_or_create_eval_source(db_manager)
    articles_by_url = _load_articles_by_url(data_dir)
    logger.info("Eval articles seed: loaded %d unique URL(s) from static files", len(articles_by_url))
    if not articles_by_url:
        return 0, 0

    with db_manager.get_session() as session:
        existing_urls = {
            row[0]
            for row in session.query(ArticleTable.canonical_url).filter(ArticleTable.source_id == source_id).all()
        }
    to_create = [url for url in articles_by_url if url not in existing_urls]
    if not to_create:
        logger.info(
            "All %d eval articles already in DB (source %s, id=%s)",
            len(articles_by_url),
            EVAL_SOURCE_NAME,
            source_id,
        )
        return 0, 0

    now = datetime.now(UTC)
    article_creates: list[ArticleCreate] = []
    for url in to_create:
        rec = articles_by_url[url]
        title = rec["title"]
        content = rec["content"]
        content_hash = ContentCleaner.calculate_content_hash(title, content)
        word_count = len(content.split()) if content else 0
        article_creates.append(
            ArticleCreate(
                source_id=source_id,
                canonical_url=url,
                title=title,
                published_at=now,
                authors=[],
                tags=[],
                summary=None,
                content=content,
                content_hash=content_hash,
                article_metadata={"word_count": word_count},
            )
        )

    created, errors = db_manager.create_articles_bulk(article_creates)
    if errors:
        for e in errors[:3]:
            logger.warning("Eval article seed error: %s", e)
        if len(errors) > 3:
            logger.warning("... and %d more eval article seed errors", len(errors) - 3)
    logger.info(
        "Seeded %d eval articles into DB (source %s, id=%s). Errors: %d",
        len(created),
        EVAL_SOURCE_NAME,
        source_id,
        len(errors),
    )
    return len(created), len(errors)
