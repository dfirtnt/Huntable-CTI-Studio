"""Tests for the pre-restore snapshot and rollback path in scripts/restore_system.py.

restore_database() drops and recreates the live database, so the snapshot taken
just before that is the only thing standing between a failed restore and an
empty production database. These tests drive that safety net with Docker and
psql mocked out: no container, no real database.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import restore_system  # noqa: E402

pytestmark = pytest.mark.unit

# Identifies the data-loading psql invocation specifically. Matching on
# "/tmp/restore.sql" alone would also catch the `rm -f /tmp/restore.sql` cleanup.
RESTORE_MARKER = "-v ON_ERROR_STOP=1"


def _result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def make_backup(tmp_path: Path) -> tuple[Path, dict]:
    """A minimal on-disk backup that restore_database() will accept."""
    dump = tmp_path / "cti_scraper_backup_20260806_020003.sql"
    dump.write_text("-- PostgreSQL database dump\nSELECT 1;\n", encoding="utf-8")
    return tmp_path, {"version": "2.0", "components": {"database": {"filename": dump.name}}}


# --- create_database_snapshot ------------------------------------------------


def test_snapshot_writes_a_timestamped_dump_and_returns_its_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []

    def run_side_effect(cmd, **_kwargs):
        calls.append(" ".join(str(part) for part in cmd))
        return _result()

    with patch("subprocess.run", side_effect=run_side_effect):
        snapshot_path = restore_system.create_database_snapshot()

    assert snapshot_path is not None
    written = Path(snapshot_path)
    assert written.parent.name == "backups"
    assert written.name.startswith("pre_restore_snapshot_")
    assert written.name.endswith(".sql")
    assert written.exists()
    # The snapshot must come from the live database, via the running container.
    assert any("pg_dump" in call and "cti_postgres" in call for call in calls)


def test_snapshot_returns_none_when_pg_dump_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run", return_value=_result(returncode=1, stderr="pg_dump: error: connection failed")):
        assert restore_system.create_database_snapshot() is None


def test_snapshot_returns_none_when_the_dump_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run", side_effect=OSError("docker socket unavailable")):
        assert restore_system.create_database_snapshot() is None


# --- snapshot gating ---------------------------------------------------------


def test_restore_aborts_before_dropping_the_database_when_the_snapshot_fails(tmp_path):
    """The most important property in this file.

    If the snapshot cannot be taken there is nothing to roll back to, so the
    restore must stop *before* the DROP DATABASE — otherwise a failure past
    that point leaves no database at all.
    """
    backup_path, metadata = make_backup(tmp_path)
    calls = []

    def run_side_effect(cmd, **_kwargs):
        calls.append(" ".join(str(part) for part in cmd))
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=None),
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    assert result is False
    assert not any("DROP DATABASE" in call for call in calls)
    assert not any(RESTORE_MARKER in call for call in calls)


def test_successful_snapshot_lets_the_restore_reach_drop_and_create(tmp_path):
    """Positive control for the test above.

    Without this, "no DROP DATABASE was issued" could pass for the wrong reason
    — a mock that never reaches the destructive block at all. Here the same
    harness, with a snapshot that succeeds, must show the full sequence.
    """
    backup_path, metadata = make_backup(tmp_path)
    snapshot_file = tmp_path / "pre_restore_snapshot_20260806_021500.sql"
    snapshot_file.write_text("-- snapshot\nSELECT 1;\n", encoding="utf-8")
    calls = []

    def run_side_effect(cmd, **_kwargs):
        calls.append(" ".join(str(part) for part in cmd))
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=str(snapshot_file)),
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    assert result is True
    assert any("DROP DATABASE" in call for call in calls)
    assert any("CREATE DATABASE" in call for call in calls)
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in call for call in calls)
    assert any(RESTORE_MARKER in call for call in calls)


def test_force_does_not_skip_the_snapshot(tmp_path):
    # --force only skips the confirmation prompt; it must never skip the
    # snapshot, which is the rollback source.
    backup_path, metadata = make_backup(tmp_path)

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=None) as snapshot,
        patch("subprocess.run", return_value=_result()),
    ):
        restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    snapshot.assert_called_once()


def test_no_snapshot_flag_skips_snapshot_creation(tmp_path):
    backup_path, metadata = make_backup(tmp_path)

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot") as snapshot,
        patch("subprocess.run", return_value=_result()),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=False, force=True)

    assert result is True
    snapshot.assert_not_called()


# --- rollback wiring ---------------------------------------------------------


def test_failed_restore_rolls_back_to_the_snapshot(tmp_path):
    backup_path, metadata = make_backup(tmp_path)
    snapshot_file = tmp_path / "pre_restore_snapshot_20260806_021500.sql"
    snapshot_file.write_text("-- snapshot\nSELECT 1;\n", encoding="utf-8")

    def run_side_effect(cmd, **_kwargs):
        flat = " ".join(str(part) for part in cmd)
        if RESTORE_MARKER in flat:
            return _result(returncode=1, stderr="psql:/tmp/restore.sql:25: ERROR:  relation does not exist\n")
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=str(snapshot_file)),
        patch("restore_system.restore_database_snapshot", return_value=True) as rollback,
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    rollback.assert_called_once_with(snapshot_file)
    assert result is True


def test_failed_restore_reports_failure_when_the_rollback_also_fails(tmp_path):
    backup_path, metadata = make_backup(tmp_path)
    snapshot_file = tmp_path / "pre_restore_snapshot_20260806_021500.sql"
    snapshot_file.write_text("-- snapshot\nSELECT 1;\n", encoding="utf-8")

    def run_side_effect(cmd, **_kwargs):
        flat = " ".join(str(part) for part in cmd)
        if RESTORE_MARKER in flat:
            return _result(returncode=1, stderr="psql:/tmp/restore.sql:1: FATAL:  out of memory\n")
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=str(snapshot_file)),
        patch("restore_system.restore_database_snapshot", return_value=False),
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    assert result is False


def test_failed_restore_without_a_snapshot_does_not_attempt_rollback(tmp_path):
    backup_path, metadata = make_backup(tmp_path)

    def run_side_effect(cmd, **_kwargs):
        flat = " ".join(str(part) for part in cmd)
        if RESTORE_MARKER in flat:
            return _result(returncode=1, stderr="psql:/tmp/restore.sql:1: ERROR:  syntax error\n")
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.restore_database_snapshot") as rollback,
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=False, force=True)

    assert result is False
    rollback.assert_not_called()


def test_rollback_is_skipped_when_the_snapshot_file_vanished(tmp_path):
    # create_database_snapshot reported success but the file is gone; the
    # rollback must not be attempted against a path that no longer exists.
    backup_path, metadata = make_backup(tmp_path)

    def run_side_effect(cmd, **_kwargs):
        flat = " ".join(str(part) for part in cmd)
        if RESTORE_MARKER in flat:
            return _result(returncode=1, stderr="psql:/tmp/restore.sql:1: ERROR:  syntax error\n")
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=str(tmp_path / "gone.sql")),
        patch("restore_system.restore_database_snapshot") as rollback,
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    assert result is False
    rollback.assert_not_called()


def test_rollback_reenters_restore_without_taking_another_snapshot(tmp_path):
    """Guards against unbounded recursion.

    restore_database_snapshot() calls back into restore_database(); if it did
    not pass create_snapshot=False, a failing restore would snapshot, fail,
    roll back, snapshot again, and so on.
    """
    snapshot_file = tmp_path / "pre_restore_snapshot_20260806_021500.sql"
    snapshot_file.write_text("-- snapshot\nSELECT 1;\n", encoding="utf-8")

    with patch("restore_system.restore_database", return_value=True) as inner:
        result = restore_system.restore_database_snapshot(snapshot_file)

    assert result is True
    args, kwargs = inner.call_args
    assert args[0] == tmp_path
    assert args[1]["components"]["database"]["filename"] == snapshot_file.name
    assert kwargs["create_snapshot"] is False
    assert kwargs["force"] is True


def test_rollback_round_trip_restores_from_the_snapshot_dump(tmp_path):
    """End-to-end through the real rollback function, only psql mocked.

    The first restore attempt fails; the second — driven by the rollback —
    succeeds, and the file it loads is the snapshot, not the backup.
    """
    backup_path, metadata = make_backup(tmp_path)
    snapshot_file = tmp_path / "pre_restore_snapshot_20260806_021500.sql"
    snapshot_file.write_text("-- snapshot\nSELECT 1;\n", encoding="utf-8")

    copied_sources = []
    restore_attempts = []

    def run_side_effect(cmd, **_kwargs):
        parts = [str(part) for part in cmd]
        flat = " ".join(parts)
        if parts[:2] == ["docker", "cp"]:
            copied_sources.append(Path(parts[2]).read_text(encoding="utf-8"))
        if RESTORE_MARKER in flat:
            restore_attempts.append(flat)
            if len(restore_attempts) == 1:
                return _result(returncode=1, stderr="psql:/tmp/restore.sql:25: ERROR:  relation does not exist\n")
        return _result()

    with (
        patch("restore_system.check_docker_container", return_value=True),
        patch("restore_system.create_database_snapshot", return_value=str(snapshot_file)),
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_system.restore_database(backup_path, metadata, create_snapshot=True, force=True)

    assert result is True
    assert len(restore_attempts) == 2
    assert "-- snapshot" in copied_sources[-1]


# --- validate_backup_directory -----------------------------------------------


def test_validate_backup_directory_rejects_a_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="Backup directory not found"):
        restore_system.validate_backup_directory(tmp_path / "absent")


def test_validate_backup_directory_rejects_a_file(tmp_path):
    stray = tmp_path / "backup.tar.gz"
    stray.write_text("not a directory")

    with pytest.raises(ValueError, match="not a directory"):
        restore_system.validate_backup_directory(stray)


def test_validate_backup_directory_requires_metadata(tmp_path):
    with pytest.raises(ValueError, match="No metadata file found"):
        restore_system.validate_backup_directory(tmp_path)


def test_validate_backup_directory_rejects_unparseable_metadata(tmp_path):
    (tmp_path / "metadata.json").write_text("{not json")

    with pytest.raises(ValueError, match="Invalid metadata file"):
        restore_system.validate_backup_directory(tmp_path)


def test_validate_backup_directory_rejects_an_unsupported_version(tmp_path):
    (tmp_path / "metadata.json").write_text('{"version": "3.0", "components": {"database": {}}}')

    with pytest.raises(ValueError, match="Unsupported backup version"):
        restore_system.validate_backup_directory(tmp_path)


def test_validate_backup_directory_rejects_empty_components(tmp_path):
    (tmp_path / "metadata.json").write_text('{"version": "2.0", "components": {}}')

    with pytest.raises(ValueError, match="No backup components found"):
        restore_system.validate_backup_directory(tmp_path)


def test_validate_backup_directory_accepts_a_well_formed_backup(tmp_path):
    (tmp_path / "metadata.json").write_text(
        '{"version": "2.0", "components": {"database": {"filename": "dump.sql.gz"}}}'
    )

    metadata = restore_system.validate_backup_directory(tmp_path)

    assert metadata["components"]["database"]["filename"] == "dump.sql.gz"


# --- verify_restore ----------------------------------------------------------


def test_verify_restore_passes_when_the_database_answers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run", return_value=_result(stdout=" 32 \n")):
        assert restore_system.verify_restore({"database"}) is True


def test_verify_restore_fails_when_the_database_is_unreachable(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.chdir(tmp_path)

    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(2, "psql")):
        assert restore_system.verify_restore({"database"}) is False


def test_verify_restore_fails_when_a_restored_directory_is_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert restore_system.verify_restore({"config"}) is False


def test_verify_restore_accepts_a_populated_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "backup.yaml").write_text("retention: {daily: 7}")

    assert restore_system.verify_restore({"config"}) is True


def test_verify_restore_accepts_an_empty_directory(tmp_path, monkeypatch):
    # An empty component directory is a valid restore of an empty backup.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()

    assert restore_system.verify_restore({"outputs"}) is True
