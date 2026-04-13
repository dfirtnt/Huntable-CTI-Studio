"""Tests for Celery worker fork safety.

Regression coverage for the os_detection connection-pool corruption bug:
concurrent eval submissions shared parent PostgreSQL sockets across forked
Celery children, producing "lost synchronization with server" errors.

The fix is a worker_process_init signal handler that disposes inherited
SQLAlchemy engines and clears DatabaseManager's engine cache after fork.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _import_celery_app():
    """Import src.worker.celery_app with heavy task modules mocked out."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }

    with patch.dict(sys.modules, mocks), patch.dict("os.environ", {"APP_ENV": "test"}, clear=False):
        return importlib.import_module("src.worker.celery_app")


class TestForkSafetyHandlerRegistered:
    """The worker_process_init handler must be registered."""

    def test_reset_handler_is_exposed(self):
        mod = _import_celery_app()
        # Handler is module-level and imported by Celery's signal dispatcher.
        assert hasattr(mod, "reset_db_connections_on_fork")
        assert callable(mod.reset_db_connections_on_fork)

    def test_reset_handler_connected_to_worker_process_init(self):
        from celery.signals import worker_process_init

        mod = _import_celery_app()
        # Celery signals store (lookup_key, weakref_or_func) tuples in .receivers;
        # resolve each receiver and look for our callback by name.
        connected_names = []
        for _key, recv_ref in worker_process_init.receivers:
            recv = recv_ref() if callable(recv_ref) and not hasattr(recv_ref, "__name__") else recv_ref
            name = getattr(recv, "__name__", "")
            connected_names.append(name)
        assert "reset_db_connections_on_fork" in connected_names, (
            f"reset_db_connections_on_fork must be connected to worker_process_init; connected: {connected_names}"
        )
        # Reference the imported module so the fixture's autodiscovery stays meaningful.
        assert mod is not None


class TestForkSafetyBehavior:
    """The handler must dispose all cached sync engines and empty the cache."""

    def test_handler_disposes_and_clears_engine_cache(self):
        mod = _import_celery_app()
        from src.database.manager import DatabaseManager

        engine_a = MagicMock()
        engine_b = MagicMock()
        session_a = MagicMock()

        DatabaseManager._engine_cache["key-a"] = engine_a
        DatabaseManager._engine_cache["key-b"] = engine_b
        DatabaseManager._session_cache["key-a"] = session_a
        try:
            mod.reset_db_connections_on_fork()
            engine_a.dispose.assert_called_once()
            engine_b.dispose.assert_called_once()
            assert DatabaseManager._engine_cache == {}
            assert DatabaseManager._session_cache == {}
        finally:
            DatabaseManager._engine_cache.clear()
            DatabaseManager._session_cache.clear()

    def test_handler_tolerates_dispose_failures(self):
        mod = _import_celery_app()
        from src.database.manager import DatabaseManager

        bad_engine = MagicMock()
        bad_engine.dispose.side_effect = RuntimeError("socket already closed")
        good_engine = MagicMock()

        DatabaseManager._engine_cache["bad"] = bad_engine
        DatabaseManager._engine_cache["good"] = good_engine
        try:
            # Must not raise even if one engine can't dispose cleanly.
            mod.reset_db_connections_on_fork()
            good_engine.dispose.assert_called_once()
            assert DatabaseManager._engine_cache == {}
        finally:
            DatabaseManager._engine_cache.clear()
            DatabaseManager._session_cache.clear()
