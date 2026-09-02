"""Regression test for the duplicate-article path of AsyncDatabaseManager.create_article.

Runs against a real Postgres on purpose. The bug it guards is an expired-attribute
lazy load: with ``expire_on_commit=True`` the ``session.commit()`` that persists the
refreshed threat-hunting metadata expires every attribute on the existing ORM row,
and the following synchronous ``_db_article_to_model()`` read of ``.content`` issues
an implicit SELECT from non-async context -- ``greenlet_spawn has not been called;
can't call await_only() here``. Neither a mocked session nor SQLite reproduces that:
the mock never expires anything and the error is specific to SQLAlchemy's asyncio
greenlet bridge.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.async_manager import AsyncDatabaseManager  # noqa: E402
from src.database.models import (  # noqa: E402
    AgenticWorkflowConfigTable,
    ArticleTable,
    Base,
    SourceTable,
)
from src.models.article import ArticleCreate  # noqa: E402
from tests.utils.test_database_url import build_test_database_url  # noqa: E402

pytestmark = pytest.mark.integration

# Worker-scoped so a parallel run cannot have two workers dropping and creating the
# same database underneath each other.
SCRATCH_DB = "cti_scratch_async_dup_test_" + os.getenv("PYTEST_XDIST_WORKER", "main")

# create_article touches articles (+ its source FK) and reads the active workflow
# config for the auto-trigger threshold.
_TABLES = (SourceTable, ArticleTable, AgenticWorkflowConfigTable)

_URL = "https://example.test/simcenter-nastran"
_CONTENT = "Siemens Simcenter Nastran advisory body text.\n" * 20


def _sync_base_url() -> str:
    """Base URL using the sync driver.

    build_test_database_url returns TEST_DATABASE_URL verbatim when it is set,
    ignoring asyncpg=False -- and the harness sets it to the +asyncpg form.
    """
    return build_test_database_url(asyncpg=False).replace("+asyncpg", "")


def _admin_engine():
    return create_engine(_sync_base_url(), isolation_level="AUTOCOMMIT")


def _drop_scratch() -> None:
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture()
def scratch_db_url() -> str:
    _drop_scratch()
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    admin.dispose()

    scratch_url = _sync_base_url().rsplit("/", 1)[0] + f"/{SCRATCH_DB}"
    engine = create_engine(scratch_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(engine, tables=[model.__table__ for model in _TABLES])

    # Seed the FK parent through the ORM so every server/Python-side column default
    # (check_frequency, config, ...) is applied.
    with Session(engine) as seed:
        seed.add(SourceTable(identifier="dup-src", name="Dup Source", url="https://example.test"))
        seed.commit()
    engine.dispose()

    try:
        yield scratch_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    finally:
        _drop_scratch()


def _article(metadata: dict) -> ArticleCreate:
    return ArticleCreate(
        source_id=1,
        canonical_url=_URL,
        title="Siemens Simcenter Nastran",
        content=_CONTENT,
        published_at=datetime(2026, 8, 19, 12, 0, 0),
        article_metadata=metadata,
    )


async def test_duplicate_article_with_hunt_score_returns_model(scratch_db_url):
    """Re-ingesting a known article with a threat_hunting_score returns the article.

    This is the path a scheduled scrape takes on every re-visit of an article it has
    already stored. Before the fix it raised greenlet_spawn inside
    ``_db_article_to_model`` and create_article swallowed it into a ``None`` return,
    so the scrape silently dropped the article and logged an error.
    """
    manager = AsyncDatabaseManager(database_url=scratch_db_url)
    try:
        first = await manager.create_article(_article({"threat_hunting_score": 10, "word_count": 120}))
        assert first is not None, "initial insert failed"

        duplicate = await manager.create_article(_article({"threat_hunting_score": 42, "word_count": 120}))

        assert duplicate is not None, "duplicate path returned None (greenlet_spawn regression)"
        assert duplicate.id == first.id
        # Every field below is read off the post-commit ORM row; each one is an
        # expired attribute that must already be loaded.
        assert duplicate.content == _CONTENT
        assert duplicate.title == "Siemens Simcenter Nastran"
        assert duplicate.canonical_url == _URL
        assert duplicate.article_metadata["threat_hunting_score"] == 42
    finally:
        await manager.close()
