"""Tests for CTI-managed backup cron service and config persistence."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from src.services.backup_cron_service import BackupCronService
from src.utils.backup_config import BackupConfigManager, set_backup_automation_state

pytestmark = pytest.mark.unit


def test_list_jobs_classifies_managed_and_external(monkeypatch):
    """Cron listing should identify CTI-managed backup jobs without hiding external jobs."""
    crontab_text = "\n".join(
        [
            "# CTI Scraper backup - Daily backup at 02:00",
            "0 2 * * * cd /repo && ./scripts/backup_restore.sh create --type full --backup-dir backups >> logs/backup.log 2>&1",
            "",
            "# unrelated",
            "15 4 * * * /usr/bin/env echo hello",
        ]
    )

    def fake_run(cmd, **kwargs):
        assert cmd == ["crontab", "-l"]
        return subprocess.CompletedProcess(cmd, 0, stdout=crontab_text, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    jobs = BackupCronService(project_root=Path("/repo")).list_jobs()

    assert len(jobs) == 2
    assert jobs[0].managed is True
    assert jobs[0].kind == "backup"
    assert jobs[1].managed is False
    assert jobs[1].kind == "external"


def test_install_backup_schedule_preserves_external_jobs(monkeypatch):
    """Applying managed cron should replace only CTI-owned entries."""
    initial_text = "\n".join(
        [
            "# existing comment",
            "15 4 * * * /usr/bin/env echo hello",
            "",
            "# CTI Scraper backup - Daily backup at 01:00",
            "0 1 * * * cd /repo && ./scripts/backup_restore.sh create --type full --backup-dir backups >> logs/backup.log 2>&1",
        ]
    )
    state = {"crontab": initial_text}

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=state["crontab"], stderr="")
        if cmd == ["crontab", "-"]:
            written = kwargs["input"]
            assert "/usr/bin/env echo hello" in written
            assert "01:00" not in written
            assert "--type database" in written
            assert "--backup-dir archives" in written
            assert "--no-compress" in written
            assert "--daily 9" in written
            state["crontab"] = written.strip()
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    manager = BackupConfigManager()
    config = manager.get_config()
    config.backup_time = "05:30"
    config.cleanup_time = "06:45"
    config.daily = 9
    config.weekly = 5
    config.monthly = 2
    config.max_size_gb = 77
    config.backup_dir = "archives"
    config.backup_type = "database"
    config.compress = False
    config.verify = True

    result = BackupCronService(project_root=Path("/repo")).install_backup_schedule(config)

    assert result["automated"] is True
    assert len(result["managed_jobs"]) == 2
    assert any(
        job["command"].startswith("cd /repo && ./scripts/backup_restore.sh prune") for job in result["managed_jobs"]
    )


def test_get_snapshot_uses_persisted_automation_state_when_crontab_unavailable(tmp_path, monkeypatch):
    """Snapshot should fall back to the shared automation marker when crontab is unavailable."""
    state_file = tmp_path / "config" / "backup_automation_state.json"
    assert set_backup_automation_state(True, state_file=state_file) is True

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("crontab")

    monkeypatch.setattr(subprocess, "run", fake_run)

    snapshot = BackupCronService(project_root=tmp_path).get_snapshot()

    assert snapshot["cron_available"] is False
    assert snapshot["automated"] is True
    assert snapshot["jobs"] == []
    assert snapshot["managed_jobs"] == []


def test_render_managed_entries_cron_time_format(monkeypatch):
    """Rendered cron line must use minute-then-hour order: '0 2 * * *' for '02:00'."""
    captured: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd == ["crontab", "-"]:
            captured.append(kwargs["input"])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.utils.backup_config import BackupConfig

    config = BackupConfig()
    config.backup_time = "02:30"
    config.cleanup_time = "03:15"
    config.cleanup_day = 0

    BackupCronService(project_root=Path("/repo")).install_backup_schedule(config)

    assert captured, "crontab write should have been called"
    written = captured[0]
    # Cron format: minute hour dow dom month; "02:30" -> "30 02" (leading zero preserved from config)
    assert "30 02 * * *" in written, f"Expected '30 02 * * *' in cron entry but got:\n{written}"
    # Cleanup time "03:15" on day 0 -> "15 03 * * 0"
    assert "15 03 * * 0" in written, f"Expected '15 03 * * 0' in cleanup entry but got:\n{written}"


def test_render_managed_entries_flags_when_compress_and_verify_off(monkeypatch):
    """--no-compress and --no-verify flags must appear when those options are disabled."""
    captured: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd == ["crontab", "-"]:
            captured.append(kwargs["input"])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.utils.backup_config import BackupConfig

    config = BackupConfig()
    config.compress = False
    config.verify = False

    BackupCronService(project_root=Path("/repo")).install_backup_schedule(config)

    written = captured[0]
    assert "--no-compress" in written
    assert "--no-verify" in written


def test_render_managed_entries_no_flags_when_compress_and_verify_on(monkeypatch):
    """--no-compress and --no-verify must NOT appear when compress/verify are enabled."""
    captured: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd == ["crontab", "-"]:
            captured.append(kwargs["input"])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.utils.backup_config import BackupConfig

    config = BackupConfig()
    config.compress = True
    config.verify = True

    BackupCronService(project_root=Path("/repo")).install_backup_schedule(config)

    written = captured[0]
    assert "--no-compress" not in written
    assert "--no-verify" not in written


def test_strip_managed_entries_from_empty_crontab(monkeypatch):
    """Stripping managed entries from an empty crontab should produce an empty string."""

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd == ["crontab", "-"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.utils.backup_config import BackupConfig

    result = BackupCronService(project_root=Path("/repo")).remove_backup_schedule(BackupConfig())
    assert result["automated"] is False


def test_strip_managed_entries_leaves_only_external_jobs(monkeypatch):
    """Removing managed entries must leave unrelated cron jobs untouched."""
    only_managed = "\n".join(
        [
            "# CTI Scraper backup - Daily backup at 02:00",
            "0 2 * * * cd /repo && ./scripts/backup_restore.sh create --type full --backup-dir backups >> logs/backup.log 2>&1",
            "",
            "# CTI Scraper backup - Weekly cleanup at 03:00",
            "0 3 * * 0 cd /repo && ./scripts/backup_restore.sh prune --backup-dir backups --force >> logs/backup.log 2>&1",
            "",
            "15 4 * * * /usr/bin/env echo hello",
        ]
    )
    written: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=only_managed, stderr="")
        if cmd == ["crontab", "-"]:
            written.append(kwargs["input"])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.utils.backup_config import BackupConfig

    BackupCronService(project_root=Path("/repo")).remove_backup_schedule(BackupConfig())

    result_text = written[0]
    assert "backup_restore.sh" not in result_text
    assert "CTI Scraper backup" not in result_text
    assert "/usr/bin/env echo hello" in result_text


def test_cron_available_returns_false_when_crontab_not_found(monkeypatch):
    """cron_available() must return False when crontab binary is missing."""

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("crontab")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert BackupCronService().cron_available() is False


def test_cron_available_returns_true_when_crontab_works(monkeypatch):
    """cron_available() must return True when crontab responds normally."""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert BackupCronService().cron_available() is True


def test_write_crontab_raises_cron_command_error_on_failure(monkeypatch):
    """_write_crontab must raise CronCommandError when crontab exits non-zero."""
    from src.services.backup_cron_service import CronCommandError

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd == ["crontab", "-"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.utils.backup_config import BackupConfig

    with pytest.raises(CronCommandError, match="permission denied"):
        BackupCronService(project_root=Path("/repo")).install_backup_schedule(BackupConfig())


def test_save_config_preserves_unknown_top_level_sections(tmp_path):
    """Saving backup config should not drop unrelated YAML sections."""
    config_path = tmp_path / "backup.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schedule": {"backup_time": "02:00", "cleanup_time": "03:00", "cleanup_day": 0},
                "notifications": {"enabled": True, "methods": ["email"]},
                "environments": {"production": {"backup": {"verify": True}}},
            }
        )
    )

    manager = BackupConfigManager(config_file=str(config_path), environment="development")
    manager.get_config().backup_time = "08:15"

    assert manager.save_config() is True

    saved = yaml.safe_load(config_path.read_text())
    assert saved["schedule"]["backup_time"] == "08:15"
    assert saved["notifications"] == {"enabled": True, "methods": ["email"]}
    assert saved["environments"] == {"production": {"backup": {"verify": True}}}
