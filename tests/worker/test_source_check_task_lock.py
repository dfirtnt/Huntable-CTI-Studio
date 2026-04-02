"""Tests for preventing overlapping source-check runs from starving maintenance tasks."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch


def _import_celery_app():
    """Import celery_app with task modules mocked out."""
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


def test_acquire_redis_lock_returns_token_when_set_succeeds():
    mod = _import_celery_app()
    client = MagicMock()
    client.set.return_value = True

    redis_module = MagicMock()
    redis_module.from_url.return_value = client

    with patch.dict(sys.modules, {"redis": redis_module}):
        with patch.object(mod, "redis_url", "redis://redis:6379/0"):
            token = mod._acquire_redis_lock("test-lock", 60)

    assert token
    client.set.assert_called_once()
    client.close.assert_called_once()


def test_acquire_redis_lock_returns_empty_string_when_lock_is_held():
    mod = _import_celery_app()
    client = MagicMock()
    client.set.return_value = False

    redis_module = MagicMock()
    redis_module.from_url.return_value = client

    with patch.dict(sys.modules, {"redis": redis_module}):
        with patch.object(mod, "redis_url", "redis://redis:6379/0"):
            token = mod._acquire_redis_lock("test-lock", 60)

    assert token == ""
    client.close.assert_called_once()


def test_release_redis_lock_deletes_only_matching_owner():
    mod = _import_celery_app()
    client = MagicMock()
    client.get.return_value = "owner-token"

    redis_module = MagicMock()
    redis_module.from_url.return_value = client

    with patch.dict(sys.modules, {"redis": redis_module}):
        with patch.object(mod, "redis_url", "redis://redis:6379/0"):
            mod._release_redis_lock("test-lock", "owner-token")

    client.delete.assert_called_once_with("test-lock")
    client.close.assert_called_once()


def test_check_all_sources_skips_when_lock_is_held():
    mod = _import_celery_app()
    fake_self = MagicMock()

    with patch.object(mod, "_acquire_redis_lock", return_value="") as acquire_mock:
        with patch.object(mod, "_release_redis_lock") as release_mock:
            with patch("asyncio.run") as asyncio_run:
                task = mod.check_all_sources
                result = task.run() if hasattr(task, "run") else task(fake_self)

    assert result["status"] == "skipped"
    assert "already in progress" in result["message"]
    acquire_mock.assert_called_once()
    release_mock.assert_not_called()
    asyncio_run.assert_not_called()
