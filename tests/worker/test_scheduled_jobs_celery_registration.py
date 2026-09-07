"""Tests for static Celery Beat registration."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch


def _import_celery_app():
    """Import celery_app with optional task modules mocked out."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.test_agents": MagicMock(),
    }

    with patch.dict(sys.modules, mocks):
        return importlib.import_module("src.worker.celery_app")


def test_celery_uses_the_database_polling_scheduler_for_managed_jobs():
    """Persisted schedules must be refreshed by Beat instead of web-triggered restart."""
    mod = _import_celery_app()
    assert mod.celery_app.conf.beat_scheduler == "src.worker.scheduled_jobs_scheduler:DatabaseScheduledJobScheduler"
