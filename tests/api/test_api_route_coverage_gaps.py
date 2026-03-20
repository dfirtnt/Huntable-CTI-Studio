"""Additional API coverage for route modules with low endpoint test coverage."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


@pytest.mark.api
class TestHealthRouteCoverage:
    @pytest.mark.asyncio
    async def test_api_health_returns_connected_payload(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        from src.web.routes import health as health_routes

        monkeypatch.setattr(
            health_routes.async_db_manager,
            "get_database_stats",
            AsyncMock(return_value={"total_sources": 2, "total_articles": 8}),
        )

        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"]["status"] == "connected"
        assert data["database"]["sources"] == 2
        assert data["database"]["articles"] == 8

    @pytest.mark.asyncio
    async def test_health_returns_503_when_database_unavailable(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        from src.web.routes import health as health_routes

        monkeypatch.setattr(
            health_routes.async_db_manager,
            "get_database_stats",
            AsyncMock(side_effect=RuntimeError("db down")),
        )

        response = await async_client.get("/health")
        assert response.status_code == 503
        assert response.json()["detail"] == "Service unhealthy"


@pytest.mark.api
class TestSearchRouteCoverage:
    @pytest.mark.asyncio
    async def test_search_articles_handler_returns_paginated_results(self, monkeypatch: pytest.MonkeyPatch):
        from src.web.routes import search as search_routes

        articles = [
            SimpleNamespace(
                id=1,
                title="Emotet campaign",
                content="The latest Emotet activity.",
                source_id=10,
                published_at=datetime(2026, 3, 1, 12, 0, 0),
                canonical_url="https://example.com/1",
                article_metadata={"threat_hunting_score": 7},
            ),
            SimpleNamespace(
                id=2,
                title="Other malware",
                content="No emotet mention here",
                source_id=11,
                published_at=datetime(2026, 3, 2, 12, 0, 0),
                canonical_url="https://example.com/2",
                article_metadata={"threat_hunting_score": 3},
            ),
        ]
        monkeypatch.setattr(search_routes.async_db_manager, "list_articles", AsyncMock(return_value=articles))

        data = await search_routes.api_search_articles(q="emotet", limit=1, offset=0)
        assert data["query"] == "emotet"
        assert data["total_results"] >= 1
        assert len(data["articles"]) <= 1
        assert "pagination" in data

    @pytest.mark.asyncio
    async def test_semantic_search_rejects_missing_query(self, async_client: httpx.AsyncClient):
        response = await async_client.post("/api/search/semantic", json={})
        assert response.status_code == 400
        assert "Query is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_semantic_search_success(self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
        import src.services.rag_service as rag_service_module

        rag = MagicMock()
        rag.semantic_search = AsyncMock(return_value={"results": [{"id": 42}], "count": 1})
        monkeypatch.setattr(rag_service_module, "get_rag_service", lambda: rag)

        response = await async_client.post(
            "/api/search/semantic",
            json={"query": "cobalt strike", "top_k": 5, "threshold": 0.6},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["id"] == 42


@pytest.mark.api
class TestTaskRouteCoverage:
    @pytest.mark.asyncio
    async def test_task_status_returns_pending_shape(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        import celery

        class FakeResult:
            status = "PENDING"
            info = {"progress": 0}

            def ready(self):
                return False

            def successful(self):
                return False

            def failed(self):
                return False

        class FakeCelery:
            def __init__(self, *_args, **_kwargs):
                pass

            def config_from_object(self, *_args, **_kwargs):
                return None

            def AsyncResult(self, _task_id):  # noqa: N802
                return FakeResult()

        monkeypatch.setattr(celery, "Celery", FakeCelery)

        response = await async_client.get("/api/tasks/task-123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-123"
        assert data["status"] == "PENDING"
        assert data["ready"] is False

    @pytest.mark.asyncio
    async def test_jobs_queues_returns_queue_lengths(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        import redis

        class FakeRedisClient:
            def llen(self, _name):
                return 3

        monkeypatch.setattr(redis, "from_url", lambda *_args, **_kwargs: FakeRedisClient())

        response = await async_client.get("/api/jobs/queues")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["queues"]["default"] == 3

    @pytest.mark.asyncio
    async def test_jobs_history_returns_sorted_tasks(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        import redis

        older = json.dumps({"status": "SUCCESS", "result": "ok", "date_done": "2026-03-01T00:00:00"})
        newer = json.dumps({"status": "SUCCESS", "result": "ok", "date_done": "2026-03-02T00:00:00"})

        class FakeRedisClient:
            def keys(self, _pattern):
                return ["celery-task-meta-a", "celery-task-meta-b"]

            def get(self, key):
                if key.endswith("a"):
                    return older
                return newer

        monkeypatch.setattr(redis, "from_url", lambda *_args, **_kwargs: FakeRedisClient())

        response = await async_client.get("/api/jobs/history?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["recent_tasks"]) == 2
        assert data["recent_tasks"][0]["task_id"] == "b"
        assert data["recent_tasks"][1]["task_id"] == "a"


@pytest.mark.api
class TestEmbeddingRouteCoverage:
    @pytest.mark.asyncio
    async def test_embedding_stats_returns_coverage(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        import src.services.rag_service as rag_service_module

        rag = MagicMock()
        rag.get_embedding_coverage = AsyncMock(
            return_value={
                "embedding_coverage_percent": 88.5,
                "pending_embeddings": 2,
                "sigma_corpus": {
                    "total_sigma_rules": 3100,
                    "sigma_rules_with_rag_embedding": 3100,
                    "sigma_embedding_coverage_percent": 100.0,
                    "sigma_rules_pending_rag_embedding": 0,
                },
            }
        )
        monkeypatch.setattr(rag_service_module, "get_rag_service", lambda: rag)

        response = await async_client.get("/api/embeddings/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["embedding_coverage_percent"] == 88.5
        assert data["pending_embeddings"] == 2
        assert data["sigma_corpus"]["total_sigma_rules"] == 3100
        assert data["sigma_corpus"]["sigma_rules_with_rag_embedding"] == 3100

    @pytest.mark.asyncio
    async def test_embedding_update_starts_task(self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
        import celery

        import src.services.rag_service as rag_service_module

        class FakeCelery:
            def __init__(self, *_args, **_kwargs):
                pass

            def config_from_object(self, *_args, **_kwargs):
                return None

            def send_task(self, *_args, **_kwargs):
                return SimpleNamespace(id="task-embed-1")

        rag = MagicMock()
        rag.get_embedding_coverage = AsyncMock(
            return_value={"pending_embeddings": 12, "embedding_coverage_percent": 40}
        )

        monkeypatch.setattr(celery, "Celery", FakeCelery)
        monkeypatch.setattr(rag_service_module, "get_rag_service", lambda: rag)

        response = await async_client.post("/api/embeddings/update", json={"batch_size": 25})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] == "task-embed-1"
        assert data["batch_size"] == 25

    @pytest.mark.asyncio
    async def test_embed_article_returns_already_embedded(
        self, async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ):
        from src.web.routes import embeddings as embedding_routes

        article = SimpleNamespace(embedding=[0.1, 0.2], embedded_at="2026-03-10T10:00:00")
        monkeypatch.setattr(embedding_routes.async_db_manager, "get_article", AsyncMock(return_value=article))

        response = await async_client.post("/api/articles/123/embed")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_embedded"
