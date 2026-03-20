import pytest


@pytest.mark.api
class TestEmbeddingsStatsContract:
    @pytest.mark.asyncio
    async def test_stats_includes_sigma_corpus_shape(self, async_client):
        response = await async_client.get("/api/embeddings/stats")
        assert response.status_code == 200
        data = response.json()
        assert "embedding_coverage_percent" in data
        assert "sigma_corpus" in data
        sc = data["sigma_corpus"]
        assert "total_sigma_rules" in sc
        assert "sigma_rules_with_rag_embedding" in sc
        assert "sigma_embedding_coverage_percent" in sc
        assert "sigma_rules_pending_rag_embedding" in sc
        assert int(sc["total_sigma_rules"]) >= 0
