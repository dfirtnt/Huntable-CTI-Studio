"""Tests for SigmaSyncService.index_embeddings() — embedding phase only."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_sync_service import SigmaSyncService


@pytest.fixture
def sync_service(tmp_path):
    return SigmaSyncService(repo_path=str(tmp_path))


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.no_autoflush = MagicMock()
    session.no_autoflush.__enter__ = MagicMock(return_value=None)
    session.no_autoflush.__exit__ = MagicMock(return_value=False)
    return session


class TestIndexEmbeddings:
    @patch("src.services.embedding_service.EmbeddingService")
    def test_generates_embeddings_for_rules_without_them(self, mock_emb_cls, sync_service, mock_db_session):
        """Should generate embeddings for rules where embedding IS NULL."""
        mock_rule = MagicMock()
        mock_rule.rule_id = "test-rule-1"
        mock_rule.embedding = None
        mock_rule.title = "Test Rule"
        mock_rule.description = "Test description"
        mock_rule.tags = ["attack.execution"]
        mock_rule.logsource = {"category": "process_creation", "product": "windows"}
        mock_rule.detection = {"selection": {"CommandLine|contains": "test"}, "condition": "selection"}

        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_rule]

        mock_emb_instance = MagicMock()
        # Batched path: 5 texts per rule (full + title, description, tags, signature)
        mock_emb_instance.generate_embeddings_batch.return_value = [[0.1] * 768] * 5
        mock_emb_cls.return_value = mock_emb_instance

        result = sync_service.index_embeddings(mock_db_session)

        assert result["embeddings_indexed"] >= 1
        assert mock_emb_instance.generate_embeddings_batch.called

    @patch("src.services.embedding_service.EmbeddingService")
    def test_result_has_expected_keys(self, mock_emb_cls, sync_service, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        mock_emb_cls.return_value = MagicMock()

        result = sync_service.index_embeddings(mock_db_session)

        assert "embeddings_indexed" in result
        assert "skipped" in result
        assert "errors" in result

    @patch("src.services.embedding_service.EmbeddingService")
    def test_skips_rules_with_existing_embeddings(self, mock_emb_cls, sync_service, mock_db_session):
        """When force_reindex=False, rules with embeddings should be skipped."""
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        mock_emb_cls.return_value = MagicMock()

        result = sync_service.index_embeddings(mock_db_session, force_reindex=False)
        assert result["embeddings_indexed"] == 0

    def test_handles_embedding_service_failure_gracefully(self, sync_service, mock_db_session):
        """If EmbeddingService cannot load (when we need it), return error result instead of raising."""
        mock_rule = MagicMock()
        mock_rule.rule_id = "test-rule-1"
        mock_rule.title = "Test"
        mock_rule.description = "Desc"
        mock_rule.tags = []
        mock_rule.logsource = {}
        mock_rule.detection = {}
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_rule]

        with patch(
            "src.services.embedding_service.EmbeddingService",
            side_effect=RuntimeError("Model not available"),
        ):
            result = sync_service.index_embeddings(mock_db_session)

        assert result["embeddings_indexed"] == 0
        assert result["errors"] > 0 or "error" in result
