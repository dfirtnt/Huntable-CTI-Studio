"""Utilities for managing CTI-owned backup cron jobs."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.backup_config import BackupConfig

MANAGED_COMMENT_PREFIX = "# CTI Scraper backup"
BACKUP_COMMAND_FRAGMENT = "./scripts/backup_restore.sh create"
CLEANUP_COMMAND_FRAGMENT = "./scripts/backup_restore.sh prune"


class CronUnavailableError(RuntimeError):
    """Raised when the host does not provide the crontab command."""


class CronCommandError(RuntimeError):
    """Raised when crontab operations fail unexpectedly."""


@dataclass
class CronJob:
    """Parsed cron job entry."""

    schedule: str
    command: str
    raw: str
    managed: bool
    kind: str
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "schedule": self.schedule,
            "command": self.command,
            "raw": self.raw,
            "managed": self.managed,
            "kind": self.kind,
            "comment": self.comment,
        }


class BackupCronService:
    """Read, install, and remove CTI-managed backup cron jobs."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).resolve().parents[2]

    def cron_available(self) -> bool:
        """Return whether the local environment supports crontab."""
        try:
            self._read_crontab()
        except CronUnavailableError:
            return False
        return True

    def list_jobs(self) -> list[CronJob]:
        """List cron jobs from the current user's crontab."""
        return self._parse_jobs(self._read_crontab())

    def get_snapshot(self) -> dict[str, Any]:
        """Return current cron availability, raw text, and parsed jobs."""
        try:
            raw = self._read_crontab()
        except CronUnavailableError:
            return {
                "cron_available": False,
                "automated": False,
                "jobs": [],
                "managed_jobs": [],
                "raw": "",
            }

        jobs = self._parse_jobs(raw)
        managed_jobs = [job.to_dict() for job in jobs if job.managed]
        return {
            "cron_available": True,
            "automated": any(job.managed for job in jobs),
            "jobs": [job.to_dict() for job in jobs],
            "managed_jobs": managed_jobs,
            "raw": raw,
        }

    def get_state(self, config: BackupConfig) -> dict[str, Any]:
        """Return current cron availability, jobs, and config state."""
        snapshot = self.get_snapshot()
        return {
            **snapshot,
            "config": {
                "backup_time": config.backup_time,
                "cleanup_time": config.cleanup_time,
                "cleanup_day": config.cleanup_day,
                "daily": config.daily,
                "weekly": config.weekly,
                "monthly": config.monthly,
                "max_size_gb": config.max_size_gb,
                "backup_dir": config.backup_dir,
                "backup_type": config.backup_type,
                "compress": config.compress,
                "verify": config.verify,
                "components": {
                    "database": config.database,
                    "models": config.models,
                    "config": config.config,
                    "outputs": config.outputs,
                    "logs": config.logs,
                    "docker_volumes": config.docker_volumes,
                },
            },
        }

    def replace_crontab(self, contents: str) -> dict[str, Any]:
        """Replace the entire current user's crontab."""
        self._write_crontab(contents)
        return self.get_snapshot()

    def install_backup_schedule(self, config: BackupConfig) -> dict[str, Any]:
        """Install or update the managed backup cron entries."""
        current = self._read_crontab()
        preserved = self._strip_managed_entries(current)
        managed = self._render_managed_entries(config)
        updated = self._join_crontab_sections(preserved, managed)
        self._write_crontab(updated)
        return self.get_state(config)

    def remove_backup_schedule(self, config: BackupConfig) -> dict[str, Any]:
        """Remove the managed backup cron entries while keeping other jobs."""
        current = self._read_crontab()
        preserved = self._strip_managed_entries(current)
        self._write_crontab(preserved)
        return self.get_state(config)

    def _read_crontab(self) -> str:
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise CronUnavailableError("crontab is not available in this environment") from exc

        if result.returncode == 0:
            return result.stdout.strip()

        stderr = (result.stderr or "").lower()
        if result.returncode == 1 and "no crontab" in stderr:
            return ""

        raise CronCommandError(result.stderr.strip() or "failed to read crontab")

    def _write_crontab(self, contents: str) -> None:
        normalized = contents.strip()
        payload = f"{normalized}\n" if normalized else "\n"

        try:
            result = subprocess.run(
                ["crontab", "-"],
                input=payload,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise CronUnavailableError("crontab is not available in this environment") from exc

        if result.returncode != 0:
            raise CronCommandError(result.stderr.strip() or "failed to write crontab")

    def _strip_managed_entries(self, crontab_text: str) -> str:
        kept_lines: list[str] = []

        for raw_line in crontab_text.splitlines():
            line = raw_line.strip()
            if not line:
                if kept_lines and kept_lines[-1] != "":
                    kept_lines.append("")
                continue
            if self._is_managed_line(line):
                continue
            kept_lines.append(raw_line)

        while kept_lines and kept_lines[-1] == "":
            kept_lines.pop()

        return "\n".join(kept_lines)

    def _parse_jobs(self, crontab_text: str) -> list[CronJob]:
        jobs: list[CronJob] = []
        pending_comments: list[str] = []

        for raw_line in crontab_text.splitlines():
            line = raw_line.strip()
            if not line:
                pending_comments = []
                continue

            if line.startswith("#"):
                pending_comments.append(raw_line)
                continue

            parts = raw_line.split(None, 5)
            if len(parts) < 6:
                pending_comments = []
                continue

            schedule = " ".join(parts[:5])
            command = parts[5].strip()
            comment = "\n".join(pending_comments) if pending_comments else None
            kind = self._detect_kind(command)
            managed = kind != "external" or any(MANAGED_COMMENT_PREFIX in item for item in pending_comments)

            jobs.append(
                CronJob(
                    schedule=schedule,
                    command=command,
                    raw=raw_line,
                    managed=managed,
                    kind=kind,
                    comment=comment,
                )
            )
            pending_comments = []

        return jobs

    def _render_managed_entries(self, config: BackupConfig) -> str:
        backup_minute, backup_hour = self._time_to_hour_minute(config.backup_time)
        cleanup_minute, cleanup_hour = self._time_to_hour_minute(config.cleanup_time)
        cleanup_day = str(config.cleanup_day)

        project_dir = shlex.quote(str(self.project_root))
        backup_dir = shlex.quote(config.backup_dir)
        backup_type = shlex.quote(config.backup_type)
        log_path = shlex.quote("logs/backup.log")

        backup_args = [f"--type {backup_type}", f"--backup-dir {backup_dir}"]
        if not config.compress:
            backup_args.append("--no-compress")
        if not config.verify:
            backup_args.append("--no-verify")

        prune_args = [
            f"--backup-dir {backup_dir}",
            f"--daily {config.daily}",
            f"--weekly {config.weekly}",
            f"--monthly {config.monthly}",
            f"--max-size-gb {config.max_size_gb}",
            "--force",
        ]

        backup_command = (
            f"{backup_minute} {backup_hour} * * * "
            f"cd {project_dir} && ./scripts/backup_restore.sh create {' '.join(backup_args)} "
            f">> {log_path} 2>&1"
        )
        cleanup_command = (
            f"{cleanup_minute} {cleanup_hour} * * {cleanup_day} "
            f"cd {project_dir} && ./scripts/backup_restore.sh prune {' '.join(prune_args)} "
            f">> {log_path} 2>&1"
        )

        return "\n".join(
            [
                f"{MANAGED_COMMENT_PREFIX} - Daily backup at {config.backup_time}",
                backup_command,
                "",
                f"{MANAGED_COMMENT_PREFIX} - Weekly cleanup at {config.cleanup_time}",
                cleanup_command,
            ]
        )

    def _join_crontab_sections(self, preserved: str, managed: str) -> str:
        sections = [section.strip() for section in (preserved, managed) if section and section.strip()]
        return "\n\n".join(sections)

    def _detect_kind(self, command: str) -> str:
        if BACKUP_COMMAND_FRAGMENT in command:
            return "backup"
        if CLEANUP_COMMAND_FRAGMENT in command:
            return "cleanup"
        return "external"

    def _is_managed_line(self, line: str) -> bool:
        return line.startswith(MANAGED_COMMENT_PREFIX) or BACKUP_COMMAND_FRAGMENT in line or CLEANUP_COMMAND_FRAGMENT in line

    def _time_to_hour_minute(self, time_value: str) -> tuple[str, str]:
        hour, minute = time_value.split(":", 1)
        return minute, hour
