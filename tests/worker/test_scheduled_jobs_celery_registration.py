"""Tests for configurable scheduled job registration in Celery beat."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _import_celery_app():
    """Import celery_app with optional task modules mocked out."""
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


def test_setup_periodic_tasks_uses_configured_job_state():
    """Beat registration should skip disabled jobs and honor configured cron expressions."""
    mod = _import_celery_app()
    mod.cleanup_old_data = SimpleNamespace(s=lambda: "cleanup")
    mod.embed_new_articles = SimpleNamespace(s=lambda: "embed")
    mod.sync_sigma_rules = SimpleNamespace(s=lambda: "sigma")
    mod.update_provider_model_catalogs = SimpleNamespace(s=lambda: "catalog")

    sender = MagicMock()
    mod.register_configurable_periodic_tasks(
        sender,
        [
            {
                "id": "cleanup_old_data",
                "registered_name": "cleanup-old-data-daily",
                "enabled": False,
                "cron": "15 1 * * *",
            },
            {
                "id": "embed_new_articles",
                "registered_name": "embed-new-articles-daily",
                "enabled": True,
                "cron": "30 14 * * *",
            },
            {
                "id": "sync_sigma_rules",
                "registered_name": "sync-sigma-rules-weekly",
                "enabled": True,
                "cron": "0 4 * * 0",
            },
            {
                "id": "update_provider_model_catalogs",
                "registered_name": "update-provider-model-catalogs-daily",
                "enabled": True,
                "cron": "45 5 * * *",
            },
        ],
        crontab_factory=lambda **kwargs: kwargs,
    )

    calls = sender.add_periodic_task.call_args_list
    names = [call.kwargs["name"] for call in calls]
    assert "cleanup-old-data-daily" not in names
    assert "embed-new-articles-daily" in names
    assert "sync-sigma-rules-weekly" in names
    assert "update-provider-model-catalogs-daily" in names

    embed_call = next(call for call in calls if call.kwargs["name"] == "embed-new-articles-daily")
    assert embed_call.args[0] == {
        "minute": "30",
        "hour": "14",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "*",
    }
