"""Unit tests for the get_queue_rule MCP tool."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.workflow import register

pytestmark = pytest.mark.unit


def _make_tool_fn(db_mock):
    """Register workflow tools with a mock db and return the get_queue_rule callable."""
    mcp = FastMCP("test-workflow")
    register(mcp, db_mock)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    return tools["get_queue_rule"].fn


def _make_db(row):
    """Build a minimal async db mock whose session returns the given row (or None)."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def _get_session():
        yield mock_session

    db = MagicMock()
    db.get_session = _get_session
    return db


def _make_row(
    queue_id=264,
    status="pending",
    rule_yaml="title: Test Rule\ndetection:\n  condition: selection",
    rule_metadata=None,
    similarity_scores=None,
    max_similarity=0.42,
    review_notes=None,
    reviewed_by=None,
    reviewed_at=None,
    pr_url=None,
    created_at=None,
    article_title="KongTuke RAT advisory",
    article_id=2069,
):
    row = MagicMock()
    row.id = queue_id
    row.status = status
    row.rule_yaml = rule_yaml
    row.rule_metadata = rule_metadata or {"title": "Test Rule"}
    row.similarity_scores = similarity_scores
    row.max_similarity = max_similarity
    row.review_notes = review_notes
    row.reviewed_by = reviewed_by
    row.reviewed_at = reviewed_at
    row.pr_url = pr_url
    row.created_at = created_at or datetime(2026, 4, 9, 0, 0, 0)
    row.article_title = article_title
    row.article_id = article_id
    return row


class TestGetQueueRuleFound:
    @pytest.mark.asyncio
    async def test_returns_yaml_block(self):
        row = _make_row()
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "title: Test Rule" in result
        assert "```yaml" in result

    @pytest.mark.asyncio
    async def test_returns_queue_id_and_status(self):
        row = _make_row(queue_id=264, status="pending")
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "Queue #264" in result
        assert "PENDING" in result

    @pytest.mark.asyncio
    async def test_returns_article_info(self):
        row = _make_row(article_id=2069, article_title="KongTuke RAT advisory")
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "2069" in result
        assert "KongTuke RAT advisory" in result

    @pytest.mark.asyncio
    async def test_returns_max_similarity(self):
        row = _make_row(max_similarity=0.8765)
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "0.8765" in result

    @pytest.mark.asyncio
    async def test_formats_similarity_scores(self):
        scores = [
            {"rule_id": "abc-123", "title": "Existing Rule A", "similarity": 0.91},
            {"rule_id": "def-456", "title": "Existing Rule B", "similarity": 0.72},
        ]
        row = _make_row(similarity_scores=scores)
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "Existing Rule A" in result
        assert "0.9100" in result

    @pytest.mark.asyncio
    async def test_no_similarity_scores_shows_placeholder(self):
        row = _make_row(similarity_scores=None)
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "none computed" in result

    @pytest.mark.asyncio
    async def test_reviewer_notes_included_when_present(self):
        row = _make_row(
            review_notes="Rejected: too generic",
            reviewed_by="andrew",
            reviewed_at=datetime(2026, 4, 10, 12, 0, 0),
            status="rejected",
        )
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "Rejected: too generic" in result
        assert "andrew" in result

    @pytest.mark.asyncio
    async def test_no_reviewer_notes_section_omitted(self):
        row = _make_row(review_notes=None, reviewed_by=None)
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "Reviewer Notes" not in result

    @pytest.mark.asyncio
    async def test_pr_url_included_when_present(self):
        row = _make_row(pr_url="https://github.com/SigmaHQ/sigma/pull/999")
        fn = _make_tool_fn(_make_db(row))
        result = await fn(queue_number=264)
        assert "https://github.com/SigmaHQ/sigma/pull/999" in result


class TestGetQueueRuleNotFound:
    @pytest.mark.asyncio
    async def test_returns_not_found_message(self):
        fn = _make_tool_fn(_make_db(None))
        result = await fn(queue_number=9999)
        assert "No queue item found" in result
        assert "9999" in result


class TestGetQueueRuleError:
    @pytest.mark.asyncio
    async def test_returns_error_string_on_exception(self):
        db = MagicMock()

        @asynccontextmanager
        async def _bad_session():
            raise RuntimeError("DB connection failed")
            yield  # noqa: unreachable

        db.get_session = _bad_session
        fn = _make_tool_fn(db)
        result = await fn(queue_number=264)
        assert "Error" in result
        assert "264" in result
