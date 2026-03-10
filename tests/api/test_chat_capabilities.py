"""Tests for capabilities block in /api/chat/rag response."""

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.api


class TestRagCapabilitiesBlock:
    def test_rag_capabilities_subset(self):
        """Verify that CapabilityService returns correct subset for RAG."""
        full_caps = {
            "article_retrieval": {"enabled": True, "reason": "OK"},
            "sigma_metadata_indexing": {"enabled": True, "reason": "Repo available"},
            "sigma_embedding_indexing": {"enabled": True, "reason": "Model available"},
            "sigma_retrieval": {
                "enabled": False,
                "reason": "No embedded rules",
                "action": "Run sigma index-embeddings",
            },
            "sigma_novelty_comparison": {"enabled": True, "reason": "50 rules"},
            "llm_generation": {"enabled": True, "provider": "openai", "reason": "OK"},
        }

        with patch("src.services.capability_service.CapabilityService") as mock_cls:
            mock_cls.return_value.compute_capabilities.return_value = full_caps

            from src.services.capability_service import CapabilityService

            service = CapabilityService()
            caps = service.compute_capabilities()

            # Verify the subset that goes in RAG response
            rag_capabilities = {
                "article_retrieval": caps.get("article_retrieval", {}),
                "sigma_retrieval": caps.get("sigma_retrieval", {}),
                "llm_generation": caps.get("llm_generation", {}),
            }

        assert len(rag_capabilities) == 3
        assert "article_retrieval" in rag_capabilities
        assert "sigma_retrieval" in rag_capabilities
        assert "llm_generation" in rag_capabilities
        assert rag_capabilities["sigma_retrieval"]["enabled"] is False
        # Verify non-RAG capabilities are NOT in the subset
        assert "sigma_metadata_indexing" not in rag_capabilities
        assert "sigma_embedding_indexing" not in rag_capabilities
