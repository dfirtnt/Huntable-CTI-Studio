"""Regression test: sorting /articles by annotation_count must use real counts.

Runs against a real Postgres on purpose. The bug this guards: annotation_count
sort was routed through the JSON-stored threat_hunting_score approximation
(src/database/statements.py), so the SQL-level order had nothing to do with
how many annotations an article actually has. This pins the fix -- the
returned order must match a direct ``COUNT(article_annotations)`` query, both
ascending and descending, with no other filters active.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.async_manager import AsyncDatabaseManager  # noqa: E402
from src.database.models import (  # noqa: E402
    ArticleAnnotationTable,
    ArticleTable,
    Base,
    SourceTable,
)
from src.models.article import ArticleListFilter  # noqa: E402
from tests.utils.test_database_url import build_test_database_url  # noqa: E402

pytestmark = pytest.mark.integration

SCRATCH_DB = "cti_scratch_annotation_sort_test_" + os.getenv("PYTEST_XDIST_WORKER", "main")

_TABLES = (SourceTable, ArticleTable, ArticleAnnotationTable)


def _sync_base_url() -> str:
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

    with Session(engine) as seed:
        source = SourceTable(identifier="annot-sort-src", name="Annot Sort Source", url="https://example.test")
        seed.add(source)
        seed.flush()

        # article_id -> annotation count, deliberately not published/discovered
        # order so a passing test can't be an accident of the default sort.
        articles = {
            "low": ArticleTable(
                source_id=source.id,
                canonical_url="https://example.test/low",
                title="Low annotations",
                content="x" * 50,
                content_hash="hash-low",
                published_at=datetime(2026, 8, 1, 0, 0, 0),
            ),
            "high": ArticleTable(
                source_id=source.id,
                canonical_url="https://example.test/high",
                title="High annotations",
                content="x" * 50,
                content_hash="hash-high",
                published_at=datetime(2026, 8, 3, 0, 0, 0),
            ),
            "mid": ArticleTable(
                source_id=source.id,
                canonical_url="https://example.test/mid",
                title="Mid annotations",
                content="x" * 50,
                content_hash="hash-mid",
                published_at=datetime(2026, 8, 2, 0, 0, 0),
            ),
        }
        for article in articles.values():
            seed.add(article)
        seed.flush()

        counts = {"low": 0, "mid": 2, "high": 5}
        for key, count in counts.items():
            for i in range(count):
                seed.add(
                    ArticleAnnotationTable(
                        article_id=articles[key].id,
                        annotation_type="huntable",
                        selected_text=f"annotation {i}",
                        start_position=0,
                        end_position=10,
                    )
                )
        seed.commit()

        expected_ids = {key: article.id for key, article in articles.items()}

    engine.dispose()

    try:
        yield scratch_url.replace("postgresql://", "postgresql+asyncpg://", 1), expected_ids
    finally:
        _drop_scratch()


async def _direct_count_order(scratch_url: str, descending: bool) -> list[int]:
    """The independent oracle: order articles by a plain COUNT(article_annotations)."""
    sync_url = scratch_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    engine = create_engine(sync_url)
    try:
        count_col = func.count(ArticleAnnotationTable.id)
        stmt = (
            select(ArticleTable.id)
            .outerjoin(ArticleAnnotationTable, ArticleAnnotationTable.article_id == ArticleTable.id)
            .group_by(ArticleTable.id)
            .order_by(count_col.desc() if descending else count_col.asc())
        )
        with engine.connect() as conn:
            return [row[0] for row in conn.execute(stmt).all()]
    finally:
        engine.dispose()


async def test_annotation_count_sort_desc_matches_direct_count(scratch_db_url):
    scratch_url, expected_ids = scratch_db_url
    manager = AsyncDatabaseManager(database_url=scratch_url)
    try:
        oracle_order = await _direct_count_order(scratch_url, descending=True)

        articles = await manager.list_articles(
            article_filter=ArticleListFilter(sort_by="annotation_count", sort_order="desc"),
            load_content=False,
        )

        assert [a.id for a in articles] == oracle_order
        assert [a.id for a in articles] == [expected_ids["high"], expected_ids["mid"], expected_ids["low"]]
    finally:
        await manager.close()


async def test_annotation_count_sort_asc_matches_direct_count(scratch_db_url):
    scratch_url, expected_ids = scratch_db_url
    manager = AsyncDatabaseManager(database_url=scratch_url)
    try:
        oracle_order = await _direct_count_order(scratch_url, descending=False)

        articles = await manager.list_articles(
            article_filter=ArticleListFilter(sort_by="annotation_count", sort_order="asc"),
            load_content=False,
        )

        assert [a.id for a in articles] == oracle_order
        assert [a.id for a in articles] == [expected_ids["low"], expected_ids["mid"], expected_ids["high"]]
    finally:
        await manager.close()
