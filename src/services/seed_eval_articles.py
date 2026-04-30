"""
Seed eval articles from config/eval_articles_data into the database.

Used at web startup (after a fresh DB) and by scripts/seed_eval_articles_to_db.py
so eval articles are ingested and the regular workflow can process them.

Also exposes cleanup_stale_eval_results() which removes subagent_evaluations rows
whose article_url is no longer listed in eval_articles.yaml for that subagent.
Call it after run() to keep the eval UI tables clean when the eval set changes.
"""

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SourceTable, SubagentEvaluationTable
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


def run(project_root: Path | None = None) -> tuple[int, int, str]:
    """
    Seed eval articles from config/eval_articles_data into the DB.

    Returns:
        (created_count, error_count, reason) where reason is
        "no_config_data" | "already_present" | "" (when created or errors)
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
        return 0, 0, "no_config_data"

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
        return 0, 0, "already_present"

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
    return len(created), len(errors), ""


def _load_active_yaml_pairs(project_root: Path) -> dict[str, set[str]]:
    """Return {subagent_name: {url, ...}} from eval_articles.yaml."""
    yaml_path = project_root / "config" / "eval_articles.yaml"
    if not yaml_path.exists():
        logger.warning("eval_articles.yaml not found at %s; skipping stale cleanup", yaml_path)
        return {}
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f) or {}
    result: dict[str, set[str]] = defaultdict(set)
    for subagent, articles in cfg.get("subagents", {}).items():
        if not isinstance(articles, list):
            continue
        for entry in articles:
            if entry and entry.get("url"):
                result[subagent].add(entry["url"])
    return dict(result)


def cleanup_stale_eval_results(project_root: Path | None = None) -> int:
    """
    Delete subagent_evaluations rows whose article_url is no longer in eval_articles.yaml.

    This keeps the eval UI tables clean when articles are removed from or moved
    between eval sets.  Safe to call repeatedly -- no-op when nothing is stale.

    Returns the number of rows deleted.
    """
    root = project_root or _project_root()
    active_pairs = _load_active_yaml_pairs(root)
    if not active_pairs:
        return 0

    db_manager = DatabaseManager()
    total_deleted = 0

    with db_manager.get_session() as session:
        for subagent, active_urls in active_pairs.items():
            stale = (
                session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.subagent_name == subagent,
                    SubagentEvaluationTable.article_url.notin_(active_urls),
                )
                .all()
            )
            if not stale:
                continue
            for row in stale:
                logger.info(
                    "Removing stale eval result: subagent=%s url=%s id=%s",
                    subagent,
                    row.article_url,
                    row.id,
                )
                session.delete(row)
            total_deleted += len(stale)

        # Also catch rows for subagent names not in the YAML at all
        known_subagents = list(active_pairs.keys())
        orphan_subagents = (
            session.query(SubagentEvaluationTable)
            .filter(SubagentEvaluationTable.subagent_name.notin_(known_subagents))
            .all()
        )
        for row in orphan_subagents:
            logger.info(
                "Removing orphan eval result (unknown subagent): subagent=%s url=%s id=%s",
                row.subagent_name,
                row.article_url,
                row.id,
            )
            session.delete(row)
        total_deleted += len(orphan_subagents)

        if total_deleted:
            session.commit()
            logger.info("Cleaned up %d stale subagent_evaluations row(s)", total_deleted)
        else:
            logger.info("Eval results cleanup: nothing stale found")

    return total_deleted
