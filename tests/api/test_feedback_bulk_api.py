"""API tests for the bulk chunk-feedback route.

The Junk Filter Tuning modal used to call the single-chunk route once per chunk
while rendering -- 150 requests on article 7216, 1,250 after a full analysis,
nearly all returning ``feedback: null`` because chunk feedback is rare.
``GET /api/feedback/chunk-classification/{article_id}`` serves the same
information in one round trip.

The only genuinely new logic is the reduction: the query returns every feedback
row for the article newest-first, and the handler keeps the first row per chunk
so the result matches what the single-chunk route (``ORDER BY created_at DESC
LIMIT 1``) would have returned for each chunk individually. These tests pin that
equivalence, because a reduction that silently kept the *oldest* row would still
look correct on any article whose chunks were reviewed only once.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.web.routes.feedback import api_get_article_chunk_feedback

pytestmark = pytest.mark.api


def _row(chunk_id: int, *, created_at: datetime, is_correct: bool = True, comment: str = ""):
    """A stand-in for ChunkClassificationFeedbackTable with the fields the route reads."""
    return SimpleNamespace(
        article_id=1,
        chunk_id=chunk_id,
        created_at=created_at,
        is_correct=is_correct,
        user_classification="Huntable",
        comment=comment,
        model_classification="Huntable",
        model_confidence=0.75,
    )


def _session_returning(rows):
    """Patch async_db_manager.get_session to yield a session returning `rows`."""
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)

    class Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return Ctx()


@pytest.mark.asyncio
async def test_returns_feedback_keyed_by_chunk_id(monkeypatch):
    rows = [
        _row(0, created_at=datetime(2026, 6, 3, 18, 54, 11)),
        _row(7, created_at=datetime(2026, 6, 3, 18, 54, 29), is_correct=False),
    ]
    monkeypatch.setattr("src.database.async_manager.async_db_manager.get_session", lambda: _session_returning(rows))

    response = await api_get_article_chunk_feedback(1)

    assert response["success"] is True
    assert set(response["feedback"]) == {"0", "7"}
    assert response["feedback"]["0"]["is_correct"] is True
    assert response["feedback"]["7"]["is_correct"] is False
    assert response["feedback"]["7"]["model_confidence"] == 0.75


@pytest.mark.asyncio
async def test_newest_row_wins_per_chunk(monkeypatch):
    """A re-reviewed chunk must report its latest verdict, matching the single-chunk route.

    Rows arrive newest-first, so the first hit per chunk is the newest. Keeping
    the last would invert the verdict on any chunk reviewed more than once -- and
    would still pass on singly-reviewed data, which is why this case exists.
    """
    rows = [
        _row(3, created_at=datetime(2026, 8, 1, 12, 0, 0), is_correct=False, comment="newest"),
        _row(3, created_at=datetime(2026, 7, 1, 12, 0, 0), is_correct=True, comment="older"),
        _row(3, created_at=datetime(2026, 6, 1, 12, 0, 0), is_correct=True, comment="oldest"),
    ]
    monkeypatch.setattr("src.database.async_manager.async_db_manager.get_session", lambda: _session_returning(rows))

    response = await api_get_article_chunk_feedback(1)

    assert list(response["feedback"]) == ["3"], "one entry per chunk, not one per row"
    assert response["feedback"]["3"]["comment"] == "newest"
    assert response["feedback"]["3"]["is_correct"] is False


@pytest.mark.asyncio
async def test_article_with_no_feedback_returns_an_empty_map(monkeypatch):
    """Absent, not null: the client iterates the map, so an empty map is the useful shape."""
    monkeypatch.setattr("src.database.async_manager.async_db_manager.get_session", lambda: _session_returning([]))

    response = await api_get_article_chunk_feedback(1)

    assert response == {"success": True, "feedback": {}}


@pytest.mark.asyncio
async def test_chunks_without_feedback_are_simply_absent(monkeypatch):
    """No placeholder entries -- a missing key is how the client knows there is nothing to show."""
    rows = [_row(2, created_at=datetime(2026, 6, 3, 18, 54, 11))]
    monkeypatch.setattr("src.database.async_manager.async_db_manager.get_session", lambda: _session_returning(rows))

    response = await api_get_article_chunk_feedback(1)

    assert set(response["feedback"]) == {"2"}
    assert "0" not in response["feedback"]


@pytest.mark.asyncio
async def test_payload_shape_matches_the_single_chunk_route(monkeypatch):
    """Both routes feed the same client-side renderer, so their entry shape must agree."""
    rows = [_row(0, created_at=datetime(2026, 6, 3, 18, 54, 11))]
    monkeypatch.setattr("src.database.async_manager.async_db_manager.get_session", lambda: _session_returning(rows))

    entry = (await api_get_article_chunk_feedback(1))["feedback"]["0"]

    assert set(entry) == {
        "timestamp",
        "is_correct",
        "user_classification",
        "comment",
        "model_classification",
        "model_confidence",
    }
