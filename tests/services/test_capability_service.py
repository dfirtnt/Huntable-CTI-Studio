"""Tests for CapabilityService."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.capability_service import CapabilityService


@pytest.fixture
def capability_service():
    return CapabilityService()


class TestCapabilityService:
    def test_compute_returns_all_capability_keys(self, capability_service):
        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        expected_keys = {
            "article_retrieval",
            "sigma_metadata_indexing",
            "sigma_embedding_indexing",
            "sigma_retrieval",
            "sigma_customer_repo_indexed",
            "sigma_novelty_comparison",
            "llm_generation",
        }
        assert set(result.keys()) == expected_keys

    def test_each_capability_has_enabled_and_reason(self, capability_service):
        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        for key, cap in result.items():
            assert "enabled" in cap, f"{key} missing 'enabled'"
            assert "reason" in cap, f"{key} missing 'reason'"
            assert isinstance(cap["enabled"], bool), f"{key} 'enabled' not bool"

    @patch("src.services.capability_service.os.getenv")
    def test_llm_generation_enabled_with_openai_key(self, mock_getenv, capability_service):
        def getenv_side_effect(key, default=""):
            if key == "OPENAI_API_KEY":
                return "sk-test-key"
            return default

        mock_getenv.side_effect = getenv_side_effect

        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        assert result["llm_generation"]["enabled"] is True

    @patch("src.services.capability_service.os.getenv", return_value="")
    def test_llm_generation_disabled_without_keys(self, mock_getenv, capability_service):
        with patch.object(capability_service, "_get_db_session", return_value=MagicMock()):
            result = capability_service.compute_capabilities()

        assert result["llm_generation"]["enabled"] is False

    def test_sigma_retrieval_disabled_when_no_embedded_rules(self, capability_service):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 0

        with patch.object(capability_service, "_get_db_session", return_value=mock_session):
            result = capability_service.compute_capabilities()

        assert result["sigma_retrieval"]["enabled"] is False
        assert "action" in result["sigma_retrieval"]

    def test_sigma_retrieval_enabled_when_embedded_rules_exist(self, capability_service):
        mock_session = MagicMock()
        # sigma_retrieval: count; sigma_customer_repo_indexed: scalar; sigma_novelty: count
        mock_session.query.return_value.filter.return_value.count.side_effect = [100, 100]
        mock_session.query.return_value.filter.return_value.scalar.return_value = 0

        with patch.object(capability_service, "_get_db_session", return_value=mock_session):
            result = capability_service.compute_capabilities()

        assert result["sigma_retrieval"]["enabled"] is True
        assert result["sigma_customer_repo_indexed"]["enabled"] is False
