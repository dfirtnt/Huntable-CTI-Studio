"""DB smoke: embedding stats, lexical search, sigma_rule_queue; optional slow Sigma semantic."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from src.database.async_manager import AsyncDatabaseManager

pytestmark = pytest.mark.smoke


async def _smoke_db_manager():
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
        pytest.skip("test database unreachable")

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


@pytest.mark.asyncio
async def test_get_sigma_rule_by_id_returns_none_for_unknown_uuid():
    """get_sigma_rule_by_id must return None (not raise) for an unknown UUID."""
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("test database unreachable")

    result = await mgr.get_sigma_rule_by_id("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.asyncio
async def test_get_sigma_rule_by_id_returns_dict_for_existing_rule():
    """get_sigma_rule_by_id returns a dict with required keys for a real rule."""
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("test database unreachable")

    from sqlalchemy import text as sa_text

    async with mgr.get_session() as session:
        row = await session.execute(
            sa_text("SELECT rule_id FROM sigma_rules ORDER BY id LIMIT 1")
        )
        first = row.scalar_one_or_none()

    if first is None:
        pytest.skip("sigma_rules table is empty")

    result = await mgr.get_sigma_rule_by_id(first)

    assert result is not None
    assert result["rule_id"] == first
    for key in ("title", "level", "status", "tags", "file_path", "raw_yaml"):
        assert key in result


@pytest.mark.asyncio
async def test_get_sigma_rule_by_id_raw_yaml_populated_after_ingest():
    """Verify raw_yaml is non-null after sigma index-metadata --force."""
    mgr = await _smoke_db_manager()
    if mgr is None:
        pytest.skip("test database unreachable")

    from sqlalchemy import text as sa_text
    from sqlalchemy.exc import ProgrammingError

    try:
        async with mgr.get_session() as session:
            row = await session.execute(
                sa_text("SELECT rule_id FROM sigma_rules WHERE raw_yaml IS NOT NULL LIMIT 1")
            )
            rule_id = row.scalar_one_or_none()
    except ProgrammingError:
        pytest.skip("raw_yaml column not yet in this DB — run scripts/migrate_sigma_raw_yaml.py")

    if rule_id is None:
        pytest.skip("No sigma_rules rows have raw_yaml yet — run sigma index-metadata --force")

    result = await mgr.get_sigma_rule_by_id(rule_id)
    assert result["raw_yaml"] is not None
    assert len(result["raw_yaml"]) > 10


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
