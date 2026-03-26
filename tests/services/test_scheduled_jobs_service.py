"""Tests for UI-managed scheduled Celery job settings."""

from __future__ import annotations

import subprocess

import pytest

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
        "check_sources_for_healing",
        "cleanup_old_data",
        "embed_new_articles",
        "sync_sigma_rules",
        "update_provider_model_catalogs",
    }
    assert next(job for job in jobs if job["id"] == "cleanup_old_data")["enabled"] is False
    assert next(job for job in jobs if job["id"] == "embed_new_articles")["cron"] == "30 11 * * *"


def test_restart_scheduler_returns_reload_metadata(monkeypatch):
    """Scheduler reload should surface the container restart result."""
    def fake_run(cmd, **kwargs):
        assert cmd == ["docker", "restart", "cti_scheduler"]
        return subprocess.CompletedProcess(cmd, 0, stdout="cti_scheduler\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = ScheduledJobsService().restart_scheduler()

    assert result == {
        "reloaded": True,
        "container": "cti_scheduler",
        "output": "cti_scheduler",
    }


def test_serialize_scheduled_jobs_state_reports_enabled_countable_jobs():
    """Serialized UI state should include each documented job with merged config."""
    state = serialize_scheduled_jobs_state(
        {
            "check_sources_for_healing": {"enabled": True, "cron": "0 * * * *"},
            "cleanup_old_data": {"enabled": False, "cron": "15 1 * * *"},
            "embed_new_articles": {"enabled": True, "cron": "0 15 * * *"},
            "sync_sigma_rules": {"enabled": True, "cron": "0 4 * * 0"},
            "update_provider_model_catalogs": {"enabled": True, "cron": "0 4 * * *"},
        }
    )

    assert state["timezone"] == "UTC"
    assert len(state["jobs"]) == 5
    assert next(job for job in state["jobs"] if job["id"] == "cleanup_old_data")["enabled"] is False
