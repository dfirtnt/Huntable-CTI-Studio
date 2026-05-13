"""Tests for sync_sigma_rules Celery task partial success."""

import importlib
import sys
from unittest.mock import MagicMock, patch


def _import_celery_app():
    """Import celery_app with all heavy dependencies mocked.

    Celery and its signals are explicitly mocked here so the behaviour is
    deterministic regardless of test-suite order (real celery may already be
    in sys.modules from an earlier test, which would bypass the conftest guard
    and expose the bind=True task as a live Celery task object rather than the
    raw function the tests expect).
    """
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mock_app = MagicMock()
    # task() must be a passthrough decorator so decorated functions remain
    # the real Python functions (not MagicMock return values).
    mock_app.task = lambda *a, **kw: lambda fn: fn

    mock_celery = MagicMock()
    mock_celery.Celery.return_value = mock_app

    mock_wpi = MagicMock()
    mock_wpi.connect = lambda fn: fn  # passthrough for @worker_process_init.connect

    mock_signals = MagicMock()
    mock_signals.worker_process_init = mock_wpi

    mocks = {
        "celery": mock_celery,
        "celery.schedules": MagicMock(),
        "celery.signals": mock_signals,
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
            # sync_sigma_rules uses bind=True; with the mocked task decorator it
            # remains the raw function, so we must supply a mock task instance as self.
            result = mod.sync_sigma_rules(MagicMock(), force_reindex=False)

        assert result["status"] == "success"
        assert result["rules_indexed"] == 100
