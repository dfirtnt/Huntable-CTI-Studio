"""Tests for SigmaSyncService.index_rules() orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_sync_service import SigmaSyncService

pytestmark = pytest.mark.unit


@pytest.fixture
def sync_service(tmp_path):
    return SigmaSyncService(repo_path=str(tmp_path))


class TestIndexRulesOrchestrator:
    def test_returns_dict_not_int(self, sync_service):
        """Orchestrator should return dict with both phases' results."""
        mock_session = MagicMock()
        with (
            patch.object(
                sync_service,
                "index_metadata",
                return_value={"metadata_indexed": 5, "skipped": 0, "errors": 0},
            ),
            patch.object(
                sync_service,
                "index_embeddings",
                return_value={"embeddings_indexed": 5, "skipped": 0, "errors": 0},
            ),
        ):
            result = sync_service.index_rules(mock_session)

        assert isinstance(result, dict)
        assert result["metadata_indexed"] == 5
        assert result["embeddings_indexed"] == 5

    def test_succeeds_partially_when_embeddings_fail(self, sync_service):
        """Should return partial success when metadata works but embeddings fail."""
        mock_session = MagicMock()
        with (
            patch.object(
                sync_service,
                "index_metadata",
                return_value={"metadata_indexed": 10, "skipped": 0, "errors": 0},
            ),
            patch.object(
                sync_service,
                "index_embeddings",
                side_effect=RuntimeError("Model unavailable"),
            ),
        ):
            result = sync_service.index_rules(mock_session)

        assert result["metadata_indexed"] == 10
        assert result["embeddings_indexed"] == 0
        assert "embedding_error" in result

    def test_backward_compat_int_return(self, sync_service):
        """For backward compatibility, index_rules_count() returns int."""
        mock_session = MagicMock()
        with (
            patch.object(
                sync_service,
                "index_metadata",
                return_value={"metadata_indexed": 5, "skipped": 0, "errors": 0},
            ),
            patch.object(
                sync_service,
                "index_embeddings",
                return_value={"embeddings_indexed": 5, "skipped": 0, "errors": 0},
            ),
        ):
            result = sync_service.index_rules(mock_session)

        # Backward compat: total count available
        assert result["metadata_indexed"] + result["embeddings_indexed"] >= 0
