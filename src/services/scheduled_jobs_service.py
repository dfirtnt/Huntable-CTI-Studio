"""Persistence and validation for configurable scheduled Celery jobs."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from celery.schedules import crontab

from src.database.manager import DatabaseManager
from src.database.models import AppSettingsTable

logger = logging.getLogger(__name__)

SCHEDULED_JOBS_SETTING_KEY = "SCHEDULED_JOBS_CONFIG"
SCHEDULED_JOBS_TIMEZONE = "UTC"
SCHEDULER_CONTAINER_NAME = os.getenv("SCHEDULER_CONTAINER_NAME", "cti_scheduler")


class ScheduledJobsConfigError(ValueError):
    """Raised when a scheduled job payload is invalid."""


class SchedulerReloadError(RuntimeError):
    """Raised when the scheduler process could not be reloaded."""


@dataclass(frozen=True)
class ScheduledJobDefinition:
    """Static metadata for a configurable scheduled job."""

    job_id: str
    label: str
    description: str
    task_name: str
    registered_name: str
    default_cron: str
    queue: str
    default_enabled: bool = True


SCHEDULED_JOB_DEFINITIONS: tuple[ScheduledJobDefinition, ...] = (
    ScheduledJobDefinition(
        job_id="cleanup_old_data",
        label="Cleanup Old Data",
        description="Prune aged operational records from the database.",
        task_name="src.worker.celery_app.cleanup_old_data",
        registered_name="cleanup-old-data-daily",
        default_cron="0 2 * * *",
        queue="maintenance",
    ),
    ScheduledJobDefinition(
        job_id="embed_new_articles",
        label="Embed New Articles",
        description="Queue embeddings for articles that do not have them yet.",
        task_name="src.worker.celery_app.embed_new_articles",
        registered_name="embed-new-articles-daily",
        default_cron="0 15 * * *",
        queue="default",
    ),
    ScheduledJobDefinition(
        job_id="sync_sigma_rules",
        label="Sync Sigma Rules",
        description="Pull SigmaHQ updates and refresh indexed rules.",
        task_name="src.worker.celery_app.sync_sigma_rules",
        registered_name="sync-sigma-rules-weekly",
        default_cron="0 4 * * 0",
        queue="maintenance",
    ),
    ScheduledJobDefinition(
        job_id="update_provider_model_catalogs",
        label="Update Provider Model Catalogs",
        description="Refresh the curated provider model catalog JSON.",
        task_name="src.worker.celery_app.update_provider_model_catalogs",
        registered_name="update-provider-model-catalogs-daily",
        default_cron="0 4 * * *",
        queue="maintenance",
    ),
)

SCHEDULED_JOB_MAP = {job.job_id: job for job in SCHEDULED_JOB_DEFINITIONS}


def _normalize_cron_expression(expression: str) -> str:
    normalized = " ".join(str(expression or "").split())
    if len(normalized.split(" ")) != 5:
        raise ScheduledJobsConfigError("Cron expression must contain exactly 5 fields.")
    return normalized


def cron_expression_to_kwargs(expression: str) -> dict[str, str]:
    """Return Celery crontab kwargs for a standard 5-field cron expression."""
    minute, hour, day_of_month, month_of_year, day_of_week = _normalize_cron_expression(expression).split(" ")
    return {
        "minute": minute,
        "hour": hour,
        "day_of_month": day_of_month,
        "month_of_year": month_of_year,
        "day_of_week": day_of_week,
    }


def validate_cron_expression(expression: str) -> str:
    """Validate a 5-field cron expression using Celery's crontab parser."""
    normalized = _normalize_cron_expression(expression)
    try:
        crontab(**cron_expression_to_kwargs(normalized))
    except Exception as exc:  # noqa: BLE001
        raise ScheduledJobsConfigError(f"Invalid cron expression '{normalized}': {exc}") from exc
    return normalized


def default_scheduled_job_config() -> dict[str, dict[str, Any]]:
    """Return the default runtime config for all managed scheduled jobs."""
    return {
        job.job_id: {
            "enabled": job.default_enabled,
            "cron": job.default_cron,
        }
        for job in SCHEDULED_JOB_DEFINITIONS
    }


def normalize_scheduled_job_config(
    raw_jobs: dict[str, Any] | None,
    *,
    allow_unknown: bool = False,
) -> dict[str, dict[str, Any]]:
    """Merge stored job config with defaults and validate every entry."""
    raw_jobs = raw_jobs or {}
    unknown_jobs = sorted(set(raw_jobs.keys()) - set(SCHEDULED_JOB_MAP.keys()))
    if unknown_jobs and not allow_unknown:
        raise ScheduledJobsConfigError(f"Unknown scheduled job ids: {', '.join(unknown_jobs)}")
    if unknown_jobs:
        raw_jobs = {job_id: payload for job_id, payload in raw_jobs.items() if job_id in SCHEDULED_JOB_MAP}

    merged = default_scheduled_job_config()
    for job_id, payload in raw_jobs.items():
        payload = payload or {}
        enabled = payload.get("enabled", merged[job_id]["enabled"])
        if not isinstance(enabled, bool):
            raise ScheduledJobsConfigError(f"Scheduled job '{job_id}' must use a boolean 'enabled' value.")
        cron_value = validate_cron_expression(payload.get("cron", merged[job_id]["cron"]))
        merged[job_id] = {"enabled": enabled, "cron": cron_value}

    return merged


def serialize_scheduled_jobs_state(job_config: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build the API/UI payload for the scheduled jobs settings panel."""
    normalized = normalize_scheduled_job_config(job_config)
    jobs = []
    for definition in SCHEDULED_JOB_DEFINITIONS:
        config = normalized[definition.job_id]
        jobs.append(
            {
                "id": definition.job_id,
                "label": definition.label,
                "description": definition.description,
                "task_name": definition.task_name,
                "registered_name": definition.registered_name,
                "queue": definition.queue,
                "timezone": SCHEDULED_JOBS_TIMEZONE,
                "default_cron": definition.default_cron,
                "cron": config["cron"],
                "enabled": config["enabled"],
            }
        )
    return {
        "timezone": SCHEDULED_JOBS_TIMEZONE,
        "jobs": jobs,
    }


class ScheduledJobsService:
    """Read, validate, persist, and apply scheduled job settings."""

    def __init__(self, scheduler_container: str = SCHEDULER_CONTAINER_NAME):
        self.scheduler_container = scheduler_container

    def _load_config_sync(self) -> dict[str, dict[str, Any]]:
        """Load the stored config via the synchronous DB manager for Celery beat startup."""
        manager = DatabaseManager()
        with manager.get_session() as session:
            row = session.query(AppSettingsTable).filter(AppSettingsTable.key == SCHEDULED_JOBS_SETTING_KEY).first()
            if not row or not row.value:
                return default_scheduled_job_config()
            try:
                payload = json.loads(row.value)
            except json.JSONDecodeError:
                logger.warning("Invalid %s JSON found in app settings; using defaults.", SCHEDULED_JOBS_SETTING_KEY)
                return default_scheduled_job_config()
            return normalize_scheduled_job_config((payload or {}).get("jobs"), allow_unknown=True)

    async def _load_config_async(self) -> dict[str, dict[str, Any]]:
        """Load the stored config from the async DB manager for the web API."""
        from sqlalchemy import select

        from src.database.async_manager import async_db_manager

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                select(AppSettingsTable).where(AppSettingsTable.key == SCHEDULED_JOBS_SETTING_KEY)
            )
            row = result.scalar_one_or_none()
            if not row or not row.value:
                return default_scheduled_job_config()
            try:
                payload = json.loads(row.value)
            except json.JSONDecodeError:
                logger.warning("Invalid %s JSON found in app settings; using defaults.", SCHEDULED_JOBS_SETTING_KEY)
                return default_scheduled_job_config()
            return normalize_scheduled_job_config((payload or {}).get("jobs"), allow_unknown=True)

    async def get_state(self) -> dict[str, Any]:
        """Return the current scheduled job configuration for the Settings UI."""
        return serialize_scheduled_jobs_state(await self._load_config_async())

    def get_periodic_jobs(self) -> list[dict[str, Any]]:
        """Return normalized runtime config for Celery beat registration."""
        config = self._load_config_sync()
        jobs = []
        for definition in SCHEDULED_JOB_DEFINITIONS:
            runtime = config[definition.job_id]
            jobs.append(
                {
                    "id": definition.job_id,
                    "registered_name": definition.registered_name,
                    "enabled": runtime["enabled"],
                    "cron": runtime["cron"],
                    "queue": definition.queue,
                }
            )
        return jobs

    async def update_state(self, jobs: dict[str, Any]) -> dict[str, Any]:
        """Persist the scheduled job config and reload the scheduler container."""
        from sqlalchemy import select

        from src.database.async_manager import async_db_manager

        normalized = normalize_scheduled_job_config(jobs)
        payload = json.dumps({"jobs": normalized}, sort_keys=True)

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                select(AppSettingsTable).where(AppSettingsTable.key == SCHEDULED_JOBS_SETTING_KEY)
            )
            row = result.scalar_one_or_none()
            if row:
                row.value = payload
                row.updated_at = datetime.now()
            else:
                session.add(
                    AppSettingsTable(
                        key=SCHEDULED_JOBS_SETTING_KEY,
                        value=payload,
                        category="system",
                        description="UI-managed schedule config for non-source Celery periodic jobs.",
                    )
                )
            await session.commit()

        reload_result = self.restart_scheduler()
        state = serialize_scheduled_jobs_state(normalized)
        state["scheduler_reload"] = reload_result
        return state

    def restart_scheduler(self) -> dict[str, Any]:
        """Restart the Celery beat container so updated schedules take effect immediately."""
        try:
            result = subprocess.run(
                ["docker", "restart", self.scheduler_container],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise SchedulerReloadError("Docker CLI is not available in the web container.") from exc
        except subprocess.TimeoutExpired as exc:
            raise SchedulerReloadError("Timed out while restarting the scheduler container.") from exc
        except Exception as exc:  # noqa: BLE001
            raise SchedulerReloadError(f"Failed to restart scheduler container: {exc}") from exc

        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "unknown error").strip()
            raise SchedulerReloadError(f"Scheduler restart failed: {stderr}")

        return {
            "reloaded": True,
            "container": self.scheduler_container,
            "output": (result.stdout or "").strip() or self.scheduler_container,
        }
