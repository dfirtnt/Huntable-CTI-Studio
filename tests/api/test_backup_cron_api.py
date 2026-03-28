"""API tests for backup cron management endpoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.web.routes import backup as backup_routes


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_backup_cron_returns_state(monkeypatch):
    """GET handler should surface cron state payload."""
    expected = {
        "cron_available": True,
        "automated": True,
        "jobs": [
            {
                "schedule": "0 2 * * *",
                "command": "echo hi",
                "managed": False,
                "kind": "external",
                "comment": None,
                "raw": "0 2 * * * echo hi",
            }
        ],
        "managed_jobs": [],
        "config": {"backup_time": "02:00"},
    }
    monkeypatch.setattr(backup_routes, "_get_cron_state", lambda: expected)

    result = await backup_routes.api_get_backup_cron()

    assert result["success"] is True
    assert result["cron_available"] is True
    assert result["config"]["backup_time"] == "02:00"


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_backup_cron_saves_config_and_applies_when_requested(monkeypatch):
    """POST handler should save config and install managed cron jobs when requested."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

        def validate_config(self):
            return []

        def save_config(self):
            return True

    class FakeService:
        def get_state(self, cfg):
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [],
                "managed_jobs": [],
                "config": {"backup_time": cfg.backup_time},
            }

        def install_backup_schedule(self, cfg):
            return {
                "cron_available": True,
                "automated": True,
                "jobs": [],
                "managed_jobs": [{"kind": "backup"}],
                "config": {"backup_time": cfg.backup_time},
            }

    monkeypatch.setattr(backup_routes, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_routes, "BackupCronService", lambda: FakeService())

    payload = backup_routes.BackupCronUpdate(
        backup_time="04:20",
        cleanup_time="05:30",
        daily=8,
        weekly=4,
        monthly=2,
        max_size_gb=60,
        backup_dir="archives",
        backup_type="database",
        compress=False,
        verify=True,
        install_crontab=True,
    )

    result = await backup_routes.api_update_backup_cron(payload)

    assert result["success"] is True
    assert result["crontab_applied"] is True
    assert result["automated"] is True
    assert config.backup_time == "04:20"
    assert config.backup_type == "database"
    assert config.compress is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_delete_backup_cron_removes_managed_jobs(monkeypatch):
    """DELETE handler should call service removal and return updated state."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

    class FakeService:
        def remove_backup_schedule(self, cfg):
            assert cfg is config
            return {"cron_available": True, "automated": False, "jobs": [], "managed_jobs": [], "config": {}}

    monkeypatch.setattr(backup_routes, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_routes, "BackupCronService", lambda: FakeService())

    result = await backup_routes.api_delete_backup_cron()

    assert result["success"] is True
    assert result["automated"] is False
