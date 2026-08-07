"""Integration test: create_articles_bulk tolerates a canonical_url conflict
without dropping the rest of the batch (Todoist 6h67phF365m9xWW3).

Regression context: the CLI collect path (src/cli/commands/collect.py) used to
throw psycopg2.errors.UniqueViolation on uq_articles_canonical_url when a
re-fetched article's canonical_url already existed with a different
content_hash. Because create_articles_bulk flushed each row on the same
session, that one flush failure poisoned the transaction and aborted the
entire batch -- genuinely-new articles in the same call were lost too.

Note: uq_articles_canonical_url is now declared in src/database/models.py
(ArticleTable.__table_args__), so fresh deployments and a freshly-built test
schema enforce it table-wide. This shared test DB, however, is persistent and
never reset between runs, and has accumulated duplicate canonical_urls from
other tests -- so the idempotent schema-ensure DDL in create_tables() cannot
add the table-wide unique index here (it fails on the existing duplicates and
is skipped). This test therefore keeps a partial unique index scoped to its
own throwaway source: it reproduces the exact UniqueViolation Postgres raises
in production without depending on a table-wide index the shared test DB
cannot host.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

if not os.getenv("TEST_DATABASE_URL"):
    pytest.skip("TEST_DATABASE_URL not set; requires a live test Postgres DB", allow_module_level=True)

from src.database.manager import DatabaseManager  # noqa: E402
from src.database.models import ArticleTable, SourceTable  # noqa: E402
from src.models.article import ArticleCreate  # noqa: E402


def test_create_articles_bulk_tolerates_canonical_url_conflict():
    db = DatabaseManager()
    uid = uuid.uuid4().hex[:8]

    with db.get_session() as session:
        source = SourceTable(
            identifier=f"test-bulk-resilience-{uid}",
            name="Test Bulk Resilience Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            check_frequency=3600,
            lookback_days=180,
            active=True,
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id

        colliding_url = f"https://example.com/bulk-resilience-{uid}"
        existing_article = ArticleTable(
            source_id=source_id,
            canonical_url=colliding_url,
            title="Pre-existing article",
            content="Pre-existing content",
            published_at=datetime.now(UTC),
            content_hash=f"existing-hash-{uid}",
        )
        session.add(existing_article)
        session.commit()

    # Enforce canonical_url uniqueness the same way production does
    # (uq_articles_canonical_url), scoped to this test's source only.
    index_name = f"test_uq_canonical_url_{source_id}"
    with db.engine.begin() as conn:
        conn.execute(
            text(f"CREATE UNIQUE INDEX {index_name} ON articles (canonical_url) WHERE source_id = {source_id}")
        )

    try:
        before = ArticleCreate(
            title="Genuinely new article (before the conflict)",
            canonical_url=f"https://example.com/bulk-resilience-before-{uid}",
            content="Brand new content, before",
            source_id=source_id,
            published_at=datetime.now(UTC),
            content_hash=f"unique-hash-before-{uid}",
        )
        conflicting = ArticleCreate(
            title="Conflicting article",
            canonical_url=colliding_url,
            content="Different content, same URL",
            source_id=source_id,
            published_at=datetime.now(UTC),
            content_hash=f"conflicting-hash-{uid}",
        )
        after = ArticleCreate(
            title="Genuinely new article (after the conflict)",
            canonical_url=f"https://example.com/bulk-resilience-after-{uid}",
            content="Brand new content, after",
            source_id=source_id,
            published_at=datetime.now(UTC),
            content_hash=f"unique-hash-after-{uid}",
        )

        # Conflict sits in the middle so both the article processed before it
        # and the one processed after it must survive commit.
        created_articles, errors = db.create_articles_bulk([before, conflicting, after])

        created_urls = {a.canonical_url for a in created_articles}
        assert created_urls == {before.canonical_url, after.canonical_url}
        assert len(created_articles) == 2
        assert any("canonical_url" in e.lower() for e in errors)
    finally:
        with db.engine.begin() as conn:
            conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
