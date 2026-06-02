"""Tests for the SigmaSim index-customer-repo cadence Celery task.

The task keeps the dedup corpus in sync with the customer's deployed Sigma rules.
It must: skip cleanly when another run holds the lock, skip when the repo path is
missing (fail open — never crash the beat), and otherwise index metadata +
embeddings with the `cust-` rule_id prefix and always release the lock.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch


def _import_celery_app():
    """Import celery_app with task submodules mocked out (mirrors the lock tests)."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }
    with patch.dict(sys.modules, mocks):
        return importlib.import_module("src.worker.celery_app")


def test_skips_when_lock_is_held():
    mod = _import_celery_app()
    with patch.object(mod, "_acquire_redis_lock", return_value="") as acquire_mock:
        with patch.object(mod, "_release_redis_lock") as release_mock:
            task = mod.index_customer_repo
            result = task.run() if hasattr(task, "run") else task(MagicMock())

    assert result["status"] == "skipped"
    assert "in progress" in result["message"]
    acquire_mock.assert_called_once()
    release_mock.assert_not_called()  # never acquired → nothing to release


def test_skips_when_repo_path_missing():
    mod = _import_celery_app()
    pr_service = MagicMock()
    pr_service.repo_path.exists.return_value = False
    sync_service = MagicMock()

    with patch.object(mod, "_acquire_redis_lock", return_value="tok"):
        with patch.object(mod, "_release_redis_lock") as release_mock:
            with patch("src.services.sigma_pr_service.SigmaPRService", return_value=pr_service):
                with patch("src.services.sigma_sync_service.SigmaSyncService", return_value=sync_service):
                    task = mod.index_customer_repo
                    result = task.run() if hasattr(task, "run") else task(MagicMock())

    assert result["status"] == "skipped"
    assert "not found" in result["message"]
    sync_service.index_metadata.assert_not_called()
    release_mock.assert_called_once()  # fail open, but always release


def test_indexes_with_cust_prefix_and_releases_lock():
    mod = _import_celery_app()
    pr_service = MagicMock()
    pr_service.repo_path.exists.return_value = True

    sync_service = MagicMock()
    sync_service.index_metadata.return_value = {"metadata_indexed": 18, "skipped": 0, "errors": 0}
    sync_service.index_embeddings.return_value = {"embeddings_indexed": 18, "skipped": 0, "errors": 0}

    with patch.object(mod, "_acquire_redis_lock", return_value="tok"):
        with patch.object(mod, "_release_redis_lock") as release_mock:
            with patch("src.services.sigma_pr_service.SigmaPRService", return_value=pr_service):
                with patch("src.services.sigma_sync_service.SigmaSyncService", return_value=sync_service):
                    with patch("src.database.manager.DatabaseManager") as db_manager:
                        db_manager.return_value.get_session.return_value = MagicMock()
                        task = mod.index_customer_repo
                        result = task.run() if hasattr(task, "run") else task(MagicMock())

    assert result["status"] == "success"
    assert result["metadata"]["metadata_indexed"] == 18
    # Both index phases must run against the customer namespace.
    assert sync_service.index_metadata.call_args.kwargs["rule_id_prefix"] == "cust-"
    assert sync_service.index_embeddings.call_args.kwargs["rule_id_prefix"] == "cust-"
    # force_reindex must be False so a no-new-rules run is near-free (skip existing).
    assert sync_service.index_metadata.call_args.kwargs["force_reindex"] is False
    release_mock.assert_called_once()
