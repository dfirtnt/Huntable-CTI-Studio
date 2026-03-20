"""Smoke checks for DB-backed embedding stats, lexical article search, and optional Sigma RAG.

Skips cleanly when ``TEST_DATABASE_URL`` is unreachable (no test containers). Semantic Sigma
search is ``slow``-marked and excluded from the default smoke marker expression.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.smoke


async def _smoke_db_manager():
    """Return ``AsyncDatabaseManager`` if the test DB answers within a few seconds."""
    try:
        from src.database.async_manager import AsyncDatabaseManager
    except ImportError:
        return None

    mgr = AsyncDatabaseManager()
    try:
        async with asyncio.timeout(5):
            async with mgr.get_session() as session:
                await session.execute(text("SELECT 1"))
    except Exception:
        return None
    return mgr


@pytest.mark.asyncio
async def test_article_and_sigma_embedding_stats_readable():
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("Test database not reachable (start test Postgres or ignore for stateless smoke)")

    art = await mgr.get_article_embedding_stats()
    assert "total_articles" in art
    assert "embedded_count" in art
    assert "embedding_coverage_percent" in art
    assert "pending_embeddings" in art
    assert int(art["total_articles"]) >= 0

    sig = await mgr.get_sigma_rule_embedding_stats()
    assert sig["total_sigma_rules"] >= 0
    assert sig["sigma_rules_with_rag_embedding"] >= 0
    assert 0.0 <= float(sig["sigma_embedding_coverage_percent"]) <= 100.0
    assert sig["sigma_rules_pending_rag_embedding"] >= 0


@pytest.mark.asyncio
async def test_lexical_article_search_returns_list():
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("Test database not reachable")

    for term in ("the", "malware", "windows", "attack"):
        hits = await mgr.search_articles_by_lexical_terms([term], limit=3)
        assert isinstance(hits, list)
        if hits:
            assert "id" in hits[0]
            break


@pytest.mark.asyncio
async def test_sigma_rule_queue_table_readable():
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("Test database not reachable")

    async with mgr.get_session() as session:
        r = await session.execute(text("SELECT COUNT(*)::bigint AS n FROM sigma_rule_queue"))
        row = r.mappings().first()
    assert row is not None
    assert int(row["n"]) >= 0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sigma_semantic_search_when_corpus_has_vectors():
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("Test database not reachable")

    sig = await mgr.get_sigma_rule_embedding_stats()
    if sig["sigma_rules_with_rag_embedding"] == 0:
        pytest.skip("No Sigma rows with RAG embeddings in test DB")

    from src.services.rag_service import RAGService

    svc = RAGService()
    rules = await svc.find_similar_sigma_rules("powershell execution", top_k=3, threshold=0.99)
    assert isinstance(rules, list)
