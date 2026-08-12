"""Tests for the database-polled Celery Beat schedule refresh."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

from src.worker.scheduled_jobs_scheduler import DatabaseScheduledJobScheduler


class _Entry:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _scheduler():
    scheduler = object.__new__(DatabaseScheduledJobScheduler)
    scheduler.schedule = {"check-all-sources-every-30min": object()}
    scheduler._heap = object()
    scheduler._last_database_refresh = 0.0
    scheduler.Entry = _Entry
    scheduler.app = SimpleNamespace()
    return scheduler


def test_refresh_replaces_only_managed_entries(monkeypatch):
    """A persisted edit must update managed jobs without removing static jobs."""
    scheduler = _scheduler()
    monkeypatch.setattr(
        "src.worker.scheduled_jobs_scheduler.ScheduledJobsService.get_periodic_jobs",
        lambda self: [
            {
                "registered_name": "cleanup-old-data-daily",
                "enabled": True,
                "cron": "15 1 * * *",
                "queue": "maintenance",
            },
            {
                "registered_name": "embed-new-articles-daily",
                "enabled": False,
                "cron": "0 15 * * *",
                "queue": "default",
            },
        ],
    )

    scheduler._refresh_database_schedule(force=True)

    assert "check-all-sources-every-30min" in scheduler.schedule
    assert "cleanup-old-data-daily" in scheduler.schedule
    assert "embed-new-articles-daily" not in scheduler.schedule
    entry = scheduler.schedule["cleanup-old-data-daily"]
    assert entry.task == "src.worker.celery_app.cleanup_old_data"
    assert entry.options == {"queue": "maintenance"}
    assert scheduler._heap is None


def test_refresh_keeps_last_known_schedule_when_database_read_fails(monkeypatch):
    """A transient database failure cannot erase the live periodic schedule."""
    scheduler = _scheduler()
    scheduler.schedule["cleanup-old-data-daily"] = object()
    monkeypatch.setattr(
        "src.worker.scheduled_jobs_scheduler.ScheduledJobsService.get_periodic_jobs",
        lambda self: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    scheduler._refresh_database_schedule(force=True)

    assert "cleanup-old-data-daily" in scheduler.schedule
