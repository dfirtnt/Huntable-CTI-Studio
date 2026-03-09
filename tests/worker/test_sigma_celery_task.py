"""Tests for sync_sigma_rules Celery task partial success."""

import importlib
import sys
from unittest.mock import MagicMock, patch


def _import_celery_app():
    """Import celery_app with all heavy dependencies mocked."""
    # Remove cached module so we get a fresh import
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    # Patch modules that celery_app.py imports at module level
    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }

    with patch.dict(sys.modules, mocks):
        return importlib.import_module("src.worker.celery_app")


class TestSyncSigmaRulesTask:
    def test_returns_success_with_partial_embeddings(self):
        """Task should succeed when metadata works but embeddings have errors."""
        mock_db_cls = MagicMock()
        mock_session = MagicMock()
        mock_db_cls.return_value.get_session.return_value = mock_session

        mock_svc_cls = MagicMock()
        mock_svc = MagicMock()
        mock_svc.clone_or_pull_repository.return_value = {"success": True, "action": "pulled"}
        mock_svc.index_rules.return_value = {
            "metadata_indexed": 100,
            "metadata_skipped": 0,
            "metadata_errors": 0,
            "embeddings_indexed": 0,
            "embeddings_skipped": 100,
            "embeddings_errors": 0,
            "embedding_error": "Model not available",
        }
        mock_svc_cls.return_value = mock_svc

        mod = _import_celery_app()

        # sync_sigma_rules uses bind=True; Celery passes the task instance as self.
        # Call with kwargs only — do not pass a mock as first arg (causes "multiple values for force_reindex").
        with patch.dict(
            sys.modules,
            {
                "src.database.manager": MagicMock(DatabaseManager=mock_db_cls),
                "src.services.sigma_sync_service": MagicMock(SigmaSyncService=mock_svc_cls),
            },
        ):
            result = mod.sync_sigma_rules(force_reindex=False)

        assert result["status"] == "success"
        assert result["rules_indexed"] == 100
