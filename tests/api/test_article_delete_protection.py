"""Eval articles must not be deletable through the article API.

Ground-truth eval articles (source identifier ``eval_articles``) are protected:
the single-delete route rejects them with 403, and the bulk-delete route skips
them and reports a ``protected_count``. See src/models/source.is_eval_source and
the guards in src/web/routes/articles.py.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.web.routes.articles import api_bulk_action, delete_article


class _FakeRequest:
    """Minimal stand-in for a Starlette Request exposing an async json() body."""

    def __init__(self, body: dict):
        self._body = body

    async def json(self) -> dict:
        return self._body


def _manager(*, is_eval, delete_ok=True, article=SimpleNamespace(id=1)) -> MagicMock:
    mgr = MagicMock()
    mgr.get_article = AsyncMock(return_value=article)
    mgr.is_eval_article = AsyncMock(side_effect=is_eval) if callable(is_eval) else AsyncMock(return_value=is_eval)
    mgr.delete_article = AsyncMock(return_value=delete_ok)
    return mgr


# ---------------------------------------------------------------------------
# Route-handler behavior (mocked manager, no DB)
# ---------------------------------------------------------------------------


@pytest.mark.api
async def test_single_delete_blocks_eval_article():
    mgr = _manager(is_eval=True)
    with patch("src.web.routes.articles.async_db_manager", mgr):
        with pytest.raises(HTTPException) as exc_info:
            await delete_article(1)
    assert exc_info.value.status_code == 403
    mgr.delete_article.assert_not_awaited()


@pytest.mark.api
async def test_single_delete_allows_normal_article():
    mgr = _manager(is_eval=False)
    with patch("src.web.routes.articles.async_db_manager", mgr):
        result = await delete_article(1)
    assert result["success"] is True
    mgr.delete_article.assert_awaited_once_with(1)


@pytest.mark.api
async def test_bulk_delete_skips_eval_and_reports_protected_count():
    # id 2 is an eval article; 1 and 3 are normal.
    mgr = _manager(is_eval=lambda aid: aid == 2)
    with patch("src.web.routes.articles.async_db_manager", mgr):
        result = await api_bulk_action(_FakeRequest({"action": "delete", "article_ids": [1, 2, 3]}))

    assert result["processed_count"] == 2
    assert result["protected_count"] == 1
    deleted_ids = [call.args[0] for call in mgr.delete_article.await_args_list]
    assert deleted_ids == [1, 3]


# ---------------------------------------------------------------------------
# Discriminator against a real database (proves the article->source join)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_is_eval_article_resolves_source_identifier(test_database_session):
    """is_eval_article maps article -> source -> identifier against a real DB."""
    from sqlalchemy import select as sa_select

    from src.database.async_manager import async_db_manager
    from src.database.models import ArticleTable, SourceTable

    session = test_database_session
    created: list = []

    # Reuse the seeded eval source if present; the identifier is unique.
    eval_source = (
        (await session.execute(sa_select(SourceTable).where(SourceTable.identifier == "eval_articles")))
        .scalars()
        .first()
    )
    if eval_source is None:
        eval_source = SourceTable(identifier="eval_articles", name="Eval Articles", url="https://example.invalid/eval")
        session.add(eval_source)
        await session.flush()
        created.append(eval_source)

    # Query-or-create so a prior interrupted run's leftover self-heals.
    normal_source = (
        (await session.execute(sa_select(SourceTable).where(SourceTable.identifier == "test-delete-guard-normal")))
        .scalars()
        .first()
    )
    if normal_source is None:
        normal_source = SourceTable(
            identifier="test-delete-guard-normal", name="Delete Guard Normal", url="https://example.invalid/normal"
        )
        session.add(normal_source)
        await session.flush()
    # Always remove the test-only normal source at the end (it is never seeded).
    created.append(normal_source)

    now = datetime.now()  # published_at is a timezone-naive column
    eval_article = ArticleTable(
        source_id=eval_source.id,
        canonical_url="https://example.invalid/eval/article-1",
        title="protected eval article",
        published_at=now,
        content="ground truth",
        content_hash="evalguard_test_hash_eval_1",
    )
    normal_article = ArticleTable(
        source_id=normal_source.id,
        canonical_url="https://example.invalid/normal/article-1",
        title="deletable normal article",
        published_at=now,
        content="regular",
        content_hash="evalguard_test_hash_normal_1",
    )
    session.add_all([eval_article, normal_article])
    await session.commit()
    created.extend([eval_article, normal_article])
    eval_id, normal_id = eval_article.id, normal_article.id

    try:
        assert await async_db_manager.is_eval_article(eval_id) is True
        assert await async_db_manager.is_eval_article(normal_id) is False
        # Unknown ids are not treated as eval (guard refuses only explicit True).
        assert await async_db_manager.is_eval_article(-1) is False
    finally:
        for obj in reversed(created):
            await session.delete(obj)
        await session.commit()
