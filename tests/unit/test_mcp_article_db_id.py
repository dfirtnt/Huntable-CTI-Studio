"""Unit tests for MCP article ID resolution from search rows."""

import pytest

from src.huntable_mcp.tools.articles import _article_db_id


@pytest.mark.unit
def test_article_db_id_prefers_article_id_for_chunk_rows():
    """Chunk-level RAG uses article_id; id may be a chunk id."""
    assert _article_db_id({"article_id": 4242, "id": 99}) == 4242


@pytest.mark.unit
def test_article_db_id_falls_back_to_id_for_lexical_rows():
    assert _article_db_id({"id": 100, "title": "x"}) == 100


@pytest.mark.unit
def test_article_db_id_none_when_empty():
    assert _article_db_id({}) is None
