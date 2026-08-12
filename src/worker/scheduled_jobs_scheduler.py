"""Celery Beat scheduler that refreshes UI-managed jobs from the database."""

from __future__ import annotations

import logging
import time
from typing import Any

from celery.beat import Scheduler
from celery.schedules import crontab

from src.services.scheduled_jobs_service import (
    SCHEDULED_JOB_DEFINITIONS,
    SCHEDULED_JOBS_POLL_INTERVAL_SECONDS,
    ScheduledJobsService,
    cron_expression_to_kwargs,
)

logger = logging.getLogger(__name__)


class DatabaseScheduledJobScheduler(Scheduler):
    """Keep the UI-managed periodic entries synchronized with persisted config.

    Static entries registered by :mod:`src.worker.celery_app` remain owned by the
    normal Celery configuration. Only the documented scheduled-job entries are
    replaced during a refresh.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_database_refresh = 0.0

    def setup_schedule(self) -> None:
        super().setup_schedule()
        self._refresh_database_schedule(force=True)

    def tick(self, *args: Any, **kwargs: Any) -> float:
        self._refresh_database_schedule()
        return super().tick(*args, **kwargs)

    def _refresh_database_schedule(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_database_refresh < SCHEDULED_JOBS_POLL_INTERVAL_SECONDS:
            return
        self._last_database_refresh = now

        try:
            jobs = ScheduledJobsService().get_periodic_jobs()
            desired = {job["registered_name"]: job for job in jobs if job["enabled"]}
            managed_names = {definition.registered_name for definition in SCHEDULED_JOB_DEFINITIONS}

            for name in managed_names - set(desired):
                self.schedule.pop(name, None)
            for name, job in desired.items():
                self.schedule[name] = self.Entry(
                    name=name,
                    task=next(
                        definition.task_name
                        for definition in SCHEDULED_JOB_DEFINITIONS
                        if definition.registered_name == name
                    ),
                    schedule=crontab(**cron_expression_to_kwargs(job["cron"])),
                    options={"queue": job["queue"]},
                    app=self.app,
                )
            self._heap = None
        except Exception:  # noqa: BLE001
            # Preserve the last known-good in-memory schedule if the database is
            # temporarily unavailable; the next poll retries the refresh.
            logger.exception("Could not refresh UI-managed Celery Beat schedules from the database")
