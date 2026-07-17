"""Regression tests for backup restore psql error handling."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import restore_database  # noqa: E402
import restore_system  # noqa: E402
import verify_backup  # noqa: E402

pytestmark = pytest.mark.unit


def _result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_verify_backup_test_restore_connects_create_database_to_postgres(tmp_path):
    backup_file = tmp_path / "database.sql"
    backup_file.write_text("SELECT 1;\n", encoding="utf-8")
    metadata = {"components": {"database": {"filename": backup_file.name}}}
    calls = []

    def run_side_effect(cmd, **_kwargs):
        calls.append(cmd)
        flat = " ".join(str(part) for part in cmd)
        if "-f /tmp/test_restore.sql" in flat:
            return _result()
        if "COUNT(*)" in flat:
            return _result(stdout="1\n")
        return _result()

    with patch("verify_backup.check_docker_container", return_value=True):
        with patch("subprocess.run", side_effect=run_side_effect):
            result = verify_backup.test_database_restore(tmp_path, metadata)

    assert result["valid"] is True
    create_calls = [" ".join(str(part) for part in cmd) for cmd in calls if "CREATE DATABASE" in " ".join(cmd)]
    assert create_calls
    assert " -d postgres " in create_calls[0]


def test_verify_backup_test_restore_fails_on_psql_statement_error(tmp_path):
    backup_file = tmp_path / "database.sql"
    backup_file.write_text("SELECT 1;\n", encoding="utf-8")
    metadata = {"components": {"database": {"filename": backup_file.name}}}
    calls = []
    hnsw_error = (
        "psql:/tmp/test_restore.sql:25: ERROR:  could not resize shared memory segment to 63999680 bytes: "
        "No space left on device\n"
    )

    def run_side_effect(cmd, **_kwargs):
        calls.append(cmd)
        flat = " ".join(str(part) for part in cmd)
        if "-f /tmp/test_restore.sql" in flat:
            return _result(returncode=0, stderr=hnsw_error)
        return _result()

    with patch("verify_backup.check_docker_container", return_value=True):
        with patch("subprocess.run", side_effect=run_side_effect):
            result = verify_backup.test_database_restore(tmp_path, metadata)

    assert result["valid"] is False
    assert "could not resize shared memory segment" in result["errors"][0]
    restore_calls = [
        " ".join(str(part) for part in cmd) for cmd in calls if "-f /tmp/test_restore.sql" in " ".join(cmd)
    ]
    assert restore_calls
    assert "-v ON_ERROR_STOP=1" in restore_calls[0]


def test_restore_system_database_restore_succeeds_with_normal_notice_noise(tmp_path):
    """A clean restore must not be flagged by the new error-detection gate.

    Real pg_dump restores routinely emit harmless NOTICE/WARNING chatter on
    stderr (e.g. "extension already exists, skipping") even on success. If
    extract_psql_errors over-matched this benign output, every restore would
    be reported as failed -- the false-positive counterpart to the two
    failure-path tests above.
    """
    backup_file = tmp_path / "database.sql"
    backup_file.write_text("SELECT 1;\n", encoding="utf-8")
    metadata = {"components": {"database": {"filename": backup_file.name}}}
    benign_noise = (
        'NOTICE:  extension "vector" already exists, skipping\nWARNING:  there is no transaction in progress\n'
    )

    def run_side_effect(cmd, **_kwargs):
        flat = " ".join(str(part) for part in cmd)
        if "-f /tmp/restore.sql" in flat:
            return _result(returncode=0, stderr=benign_noise)
        return _result()

    with patch("restore_system.check_docker_container", return_value=True):
        with patch("subprocess.run", side_effect=run_side_effect):
            result = restore_system.restore_database(tmp_path, metadata, create_snapshot=False, force=True)

    assert result is True


def test_restore_database_succeeds_with_normal_notice_noise(tmp_path):
    """Legacy single-file restore (scripts/restore_database.py) must not flag benign stderr noise."""
    backup_file = tmp_path / "cti_scraper_backup_test.sql"
    backup_file.write_text("-- PostgreSQL database dump\nSELECT 1;\n", encoding="utf-8")
    benign_noise = (
        'NOTICE:  extension "vector" already exists, skipping\nWARNING:  there is no transaction in progress\n'
    )

    def run_side_effect(cmd, **_kwargs):
        flat = " ".join(str(part) for part in cmd)
        if "-f /tmp/restore.sql" in flat:
            return _result(returncode=0, stderr=benign_noise)
        return _result()

    with (
        patch("restore_database.check_docker_container", return_value=True),
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_database.restore_database(backup_file, create_snapshot=False, force=True)

    assert result is True


def test_restore_database_fails_on_psql_statement_error(tmp_path):
    """RCE-adjacent regression: legacy restore_database.py must not report success on a partial restore.

    psql exits 0 even when individual statements fail, so returncode alone is
    unreliable. This mirrors the fix already shipped in restore_system.py.
    """
    backup_file = tmp_path / "cti_scraper_backup_test.sql"
    backup_file.write_text("-- PostgreSQL database dump\nSELECT 1;\n", encoding="utf-8")
    calls = []
    hnsw_error = (
        "psql:/tmp/restore.sql:25: ERROR:  could not resize shared memory segment to 63999680 bytes: "
        "No space left on device\n"
    )

    def run_side_effect(cmd, **_kwargs):
        calls.append(cmd)
        flat = " ".join(str(part) for part in cmd)
        if "-f /tmp/restore.sql" in flat:
            return _result(returncode=0, stderr=hnsw_error)
        return _result()

    with (
        patch("restore_database.check_docker_container", return_value=True),
        patch("subprocess.run", side_effect=run_side_effect),
    ):
        result = restore_database.restore_database(backup_file, create_snapshot=False, force=True)

    assert result is False
    restore_calls = [" ".join(str(part) for part in cmd) for cmd in calls if "-f /tmp/restore.sql" in " ".join(cmd)]
    assert restore_calls
    assert "-v ON_ERROR_STOP=1" in restore_calls[0]


def test_restore_system_database_restore_fails_on_psql_statement_error(tmp_path):
    backup_file = tmp_path / "database.sql"
    backup_file.write_text("SELECT 1;\n", encoding="utf-8")
    metadata = {"components": {"database": {"filename": backup_file.name}}}
    calls = []
    hnsw_error = (
        "psql:/tmp/restore.sql:25: ERROR:  could not resize shared memory segment to 63999680 bytes: "
        "No space left on device\n"
    )

    def run_side_effect(cmd, **_kwargs):
        calls.append(cmd)
        flat = " ".join(str(part) for part in cmd)
        if "-f /tmp/restore.sql" in flat:
            return _result(returncode=0, stderr=hnsw_error)
        return _result()

    with patch("restore_system.check_docker_container", return_value=True):
        with patch("subprocess.run", side_effect=run_side_effect):
            result = restore_system.restore_database(tmp_path, metadata, create_snapshot=False, force=True)

    assert result is False
    restore_calls = [" ".join(str(part) for part in cmd) for cmd in calls if "-f /tmp/restore.sql" in " ".join(cmd)]
    assert restore_calls
    assert "-v ON_ERROR_STOP=1" in restore_calls[0]
