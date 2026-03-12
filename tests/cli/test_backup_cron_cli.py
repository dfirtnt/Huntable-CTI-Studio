"""CLI tests for backup cron management."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

from click.testing import CliRunner

from src.cli.main import cli

backup_module = importlib.import_module("src.cli.commands.backup")


def test_backup_cron_show_lists_jobs(monkeypatch):
    """backup cron show should print managed and external jobs."""
    class FakeManager:
        def get_config(self):
            return SimpleNamespace()

    class FakeService:
        def get_state(self, config):
            return {
                "cron_available": True,
                "automated": True,
                "jobs": [
                    {"managed": True, "schedule": "0 2 * * *", "command": "managed job"},
                    {"managed": False, "schedule": "15 4 * * *", "command": "external job"},
                ],
                "managed_jobs": [{"kind": "backup"}],
                "config": {"backup_time": "02:00", "cleanup_time": "03:00"},
            }

    monkeypatch.setattr(backup_module, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_module, "BackupCronService", lambda: FakeService())

    result = CliRunner().invoke(cli, ["backup", "cron", "show"])

    assert result.exit_code == 0, result.output
    assert "Automated backups: enabled" in result.output
    assert "[managed] 0 2 * * * -> managed job" in result.output
    assert "[external] 15 4 * * * -> external job" in result.output


def test_backup_cron_apply_updates_schedule(monkeypatch):
    """backup cron apply should save config and install managed jobs."""
    config = SimpleNamespace(
        backup_time="02:00",
        cleanup_time="03:00",
        daily=7,
        weekly=4,
        monthly=3,
        max_size_gb=50,
        backup_dir="backups",
        backup_type="full",
        compress=True,
        verify=True,
    )

    class FakeManager:
        def get_config(self):
            return config

        def validate_config(self):
            return []

        def save_config(self):
            return True

    class FakeService:
        def install_backup_schedule(self, cfg):
            assert cfg.backup_time == "06:15"
            return {"managed_jobs": [{}, {}]}

    monkeypatch.setattr(backup_module, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_module, "BackupCronService", lambda: FakeService())

    result = CliRunner().invoke(cli, ["backup", "cron", "apply", "--backup-time", "06:15", "--type", "database"])

    assert result.exit_code == 0, result.output
    assert "Backup cron schedule applied" in result.output
    assert config.backup_type == "database"


def test_backup_cron_disable_removes_managed_jobs(monkeypatch):
    """backup cron disable should remove the managed schedule."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

    class FakeService:
        def remove_backup_schedule(self, cfg):
            assert cfg is config
            return {}

    monkeypatch.setattr(backup_module, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_module, "BackupCronService", lambda: FakeService())

    result = CliRunner().invoke(cli, ["backup", "cron", "disable"])

    assert result.exit_code == 0, result.output
    assert "Backup cron schedule removed" in result.output
