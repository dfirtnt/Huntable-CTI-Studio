"""CLI tests for generic cron commands."""

from __future__ import annotations

import importlib

from click.testing import CliRunner

from src.cli.main import cli

cron_module = importlib.import_module("src.cli.commands.cron")


def test_cron_show_lists_jobs(monkeypatch):
    """cron show should list parsed cron jobs."""

    class FakeService:
        def get_snapshot(self):
            return {
                "cron_available": True,
                "jobs": [
                    {"managed": False, "schedule": "0 1 * * *", "command": "echo hi"},
                    {"managed": True, "schedule": "30 2 * * *", "command": "backup job"},
                ],
                "raw": "ignored",
            }

    monkeypatch.setattr(cron_module, "BackupCronService", lambda: FakeService())

    result = CliRunner().invoke(cli, ["cron", "show"])

    assert result.exit_code == 0, result.output
    assert "[external] 0 1 * * * -> echo hi" in result.output
    assert "[managed] 30 2 * * * -> backup job" in result.output


def test_cron_set_replaces_crontab(tmp_path, monkeypatch):
    """cron set should replace the current crontab from a file."""
    cron_file = tmp_path / "cron.txt"
    cron_file.write_text("5 4 * * * echo updated\n")

    class FakeService:
        def replace_crontab(self, content: str):
            assert content == "5 4 * * * echo updated\n"
            return {"jobs": [{"schedule": "5 4 * * *", "command": "echo updated"}]}

    monkeypatch.setattr(cron_module, "BackupCronService", lambda: FakeService())

    result = CliRunner().invoke(cli, ["cron", "set", "--file", str(cron_file)])

    assert result.exit_code == 0, result.output
    assert "Updated crontab with 1 parsed job" in result.output
