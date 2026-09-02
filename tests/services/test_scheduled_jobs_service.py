"""Tests for UI-managed scheduled Celery job settings."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from src.services.scheduled_jobs_service import (
    ScheduledJobsConfigError,
    ScheduledJobsService,
    cron_expression_to_kwargs,
    normalize_scheduled_job_config,
    serialize_scheduled_jobs_state,
)


def test_normalize_scheduled_job_config_merges_defaults():
    """Partial stored config should merge with defaults for the documented jobs."""
    config = normalize_scheduled_job_config(
        {
            "cleanup_old_data": {"enabled": False, "cron": "15 1 * * *"},
            "sync_sigma_rules": {"enabled": True, "cron": "0 7 * * 1"},
        }
    )

    assert config["cleanup_old_data"] == {"enabled": False, "cron": "15 1 * * *"}
    assert config["sync_sigma_rules"] == {"enabled": True, "cron": "0 7 * * 1"}


def test_normalize_scheduled_job_config_rejects_unknown_job():
    """Unknown job ids should fail validation instead of being stored silently."""
    with pytest.raises(ScheduledJobsConfigError):
        normalize_scheduled_job_config({"not_real": {"enabled": True, "cron": "0 0 * * *"}})


def test_normalize_scheduled_job_config_attaches_job_id_to_cron_errors():
    """A bad cron on one job must name that job, not just fail generically --
    the route/UI use `.job_id` to highlight the offending field instead of
    surfacing an unattributed "Validation error"."""
    with pytest.raises(ScheduledJobsConfigError) as exc_info:
        normalize_scheduled_job_config({"cleanup_old_data": {"enabled": True, "cron": "not a cron"}})

    assert exc_info.value.job_id == "cleanup_old_data"
    assert "cleanup_old_data" not in str(exc_info.value)  # message names the problem, not the job id
    assert str(exc_info.value)  # non-empty: the specific reason, not a bare "Validation error"


def test_normalize_scheduled_job_config_attaches_job_id_to_enabled_type_errors():
    with pytest.raises(ScheduledJobsConfigError) as exc_info:
        normalize_scheduled_job_config({"sync_sigma_rules": {"enabled": "yes", "cron": "0 4 * * 0"}})

    assert exc_info.value.job_id == "sync_sigma_rules"


def test_normalize_scheduled_job_config_unknown_job_error_has_no_job_id():
    """Errors that aren't scoped to a single job (e.g. an unrecognized job id
    in the payload) must not claim a job_id -- there's no single field to blame."""
    with pytest.raises(ScheduledJobsConfigError) as exc_info:
        normalize_scheduled_job_config({"not_real": {"enabled": True, "cron": "0 0 * * *"}})

    assert exc_info.value.job_id is None


def test_normalize_scheduled_job_config_can_ignore_removed_jobs():
    """Stored config should tolerate retired job ids when loading legacy state."""
    config = normalize_scheduled_job_config(
        {
            "cleanup_old_data": {"enabled": False, "cron": "15 1 * * *"},
            "generate_daily_report": {"enabled": True, "cron": "0 6 * * *"},
        },
        allow_unknown=True,
    )

    assert "generate_daily_report" not in config
    assert config["cleanup_old_data"] == {"enabled": False, "cron": "15 1 * * *"}


def test_cron_expression_to_kwargs_maps_standard_fields():
    """Cron parsing should preserve field order for Celery crontab registration."""
    kwargs = cron_expression_to_kwargs("5 4 * * 0")

    assert kwargs == {
        "minute": "5",
        "hour": "4",
        "day_of_month": "*",
        "month_of_year": "*",
        "day_of_week": "0",
    }


def test_get_periodic_jobs_uses_persisted_config(monkeypatch):
    """Beat registration should receive the merged runtime config."""
    service = ScheduledJobsService()
    monkeypatch.setattr(
        service,
        "_load_config_sync",
        lambda: normalize_scheduled_job_config(
            {
                "cleanup_old_data": {"enabled": False, "cron": "15 1 * * *"},
                "embed_new_articles": {"enabled": True, "cron": "30 11 * * *"},
            }
        ),
    )

    jobs = service.get_periodic_jobs()

    assert {job["id"] for job in jobs} == {
        "cleanup_old_data",
        "embed_new_articles",
        "sync_sigma_rules",
        "update_provider_model_catalogs",
    }
    assert next(job for job in jobs if job["id"] == "cleanup_old_data")["enabled"] is False
    assert next(job for job in jobs if job["id"] == "embed_new_articles")["cron"] == "30 11 * * *"


def test_scheduler_refresh_metadata_describes_database_polling():
    """The web API must not need a Docker restart to apply a schedule change."""
    result = ScheduledJobsService().scheduler_refresh_metadata()

    assert result == {
        "reloaded": True,
        "mechanism": "database_poll",
        "poll_interval_seconds": 30,
    }


def test_serialize_scheduled_jobs_state_reports_enabled_countable_jobs():
    """Serialized UI state should include each documented job with merged config."""
    state = serialize_scheduled_jobs_state(
        {
            "cleanup_old_data": {"enabled": False, "cron": "15 1 * * *"},
            "embed_new_articles": {"enabled": True, "cron": "0 15 * * *"},
            "sync_sigma_rules": {"enabled": True, "cron": "0 4 * * 0"},
            "update_provider_model_catalogs": {"enabled": True, "cron": "0 4 * * *"},
        }
    )

    assert state["timezone"] == "UTC"
    assert len(state["jobs"]) == 4
    assert next(job for job in state["jobs"] if job["id"] == "cleanup_old_data")["enabled"] is False
