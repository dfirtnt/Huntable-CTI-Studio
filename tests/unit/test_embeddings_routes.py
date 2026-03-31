"""Unit tests for embedding route helpers."""

from unittest.mock import AsyncMock

import pytest

from src.web.routes import embeddings as embedding_routes

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_embedding_coverage_stats_merges_article_and_sigma_stats(monkeypatch: pytest.MonkeyPatch):
    """The route helper should return one payload composed from both DB stat calls."""
    monkeypatch.setattr(
        embedding_routes.async_db_manager,
        "get_article_embedding_stats",
        AsyncMock(
            return_value={
                "total_articles": 25,
                "embedded_count": 20,
                "embedding_coverage_percent": 80.0,
                "pending_embeddings": 5,
                "source_stats": [],
            }
        ),
    )
    monkeypatch.setattr(
        embedding_routes.async_db_manager,
        "get_sigma_rule_embedding_stats",
        AsyncMock(
            return_value={
                "total_sigma_rules": 200,
                "sigma_rules_with_rag_embedding": 150,
                "sigma_embedding_coverage_percent": 75.0,
                "sigma_rules_pending_rag_embedding": 50,
            }
        ),
    )

    result = await embedding_routes._get_embedding_coverage_stats()

    assert result["total_articles"] == 25
    assert result["embedded_count"] == 20
    assert result["pending_embeddings"] == 5
    assert result["sigma_corpus"]["total_sigma_rules"] == 200
    assert result["sigma_corpus"]["sigma_rules_pending_rag_embedding"] == 50


@pytest.mark.asyncio
async def test_api_embedding_stats_uses_db_only_stats(monkeypatch: pytest.MonkeyPatch):
    """The stats endpoint should return the helper payload directly."""
    expected = {
        "total_articles": 10,
        "embedded_count": 8,
        "embedding_coverage_percent": 80.0,
        "pending_embeddings": 2,
        "sigma_corpus": {
            "total_sigma_rules": 5,
            "sigma_rules_with_rag_embedding": 4,
            "sigma_embedding_coverage_percent": 80.0,
            "sigma_rules_pending_rag_embedding": 1,
        },
    }
    monkeypatch.setattr(
        embedding_routes,
        "_get_embedding_coverage_stats",
        AsyncMock(return_value=expected),
    )

    result = await embedding_routes.api_embedding_stats()

    assert result == expected
