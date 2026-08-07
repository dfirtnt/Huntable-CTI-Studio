"""Unit tests for dashboard administrative actions."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from src.web.routes.actions import api_rescore_all


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rescore_all_reprocesses_articles_with_existing_scores() -> None:
    articles = [
        SimpleNamespace(
            id=1,
            source_id=1,
            canonical_url="https://example.com/1",
            title="Already scored",
            content="article body",
            content_hash="hash-1",
            published_at=datetime(2026, 1, 1),
            article_metadata={"threat_hunting_score": 10},
        ),
        SimpleNamespace(
            id=2,
            source_id=1,
            canonical_url="https://example.com/2",
            title="Also already scored",
            content="article body",
            content_hash="hash-2",
            published_at=datetime(2026, 1, 2),
            article_metadata={"threat_hunting_score": 20},
        ),
    ]
    db = SimpleNamespace(
        list_articles=AsyncMock(return_value=articles),
        update_article=AsyncMock(),
    )
    processor = MagicMock()
    processor._enhance_metadata = AsyncMock(
        side_effect=[
            {"threat_hunting_score": 70},
            {"threat_hunting_score": 80},
        ]
    )

    with (
        patch("src.web.routes.actions.async_db_manager", db),
        patch("src.core.processor.ContentProcessor", return_value=processor),
    ):
        background_tasks = BackgroundTasks()
        result = await api_rescore_all(background_tasks)
        await background_tasks()

    assert result["processed"] == 0
    assert result["total"] == 2
    assert "Rescoring started for 2 articles" in result["message"]
    assert processor._enhance_metadata.await_count == 2
    assert db.update_article.await_count == 2
    assert articles[0].article_metadata["threat_hunting_score"] == 70
    assert articles[1].article_metadata["threat_hunting_score"] == 80
