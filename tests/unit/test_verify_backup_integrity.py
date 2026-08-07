"""Integrity tests for scripts/verify_backup.py.

verify_backup.py is the only thing standing between a silently corrupted backup
and a failed restore, so these tests are deliberately weighted towards negative
cases: a checksum comparator that always returned True, or a structure validator
that accepted a metadata-less directory, must fail here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import verify_backup  # noqa: E402

pytestmark = pytest.mark.unit

DUMP_NAME = "cti_scraper_backup_20260706_020002.sql.gz"
DUMP_BODY = b"-- PostgreSQL database dump\nCOPY articles (id) FROM stdin;\n"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def make_system_backup(
    root: Path,
    *,
    components: dict | None = None,
    dump_body: bytes | None = DUMP_BODY,
    checksum: str | None = None,
    write_metadata: bool = True,
    metadata_text: str | None = None,
) -> Path:
    """Build a minimal on-disk system backup that verify_backup can walk."""
    backup_path = root / "system_backup_20260706_020002"
    backup_path.mkdir(parents=True, exist_ok=True)

    if dump_body is not None:
        (backup_path / DUMP_NAME).write_bytes(dump_body)

    if components is None:
        components = {
            "database": {
                "filename": DUMP_NAME,
                "checksum": checksum if checksum is not None else sha256(DUMP_BODY),
                "size_mb": 0.01,
            },
            "models": {"files": 1, "size_mb": 0.01},
            "config": {"files": 1, "size_mb": 0.01},
            "outputs": {"files": 1, "size_mb": 0.01},
        }

    for component_name in components:
        if component_name != "database" and not component_name.startswith("docker_volume_"):
            (backup_path / component_name).mkdir(exist_ok=True)

    if write_metadata:
        text = metadata_text
        if text is None:
            text = json.dumps({"version": "2.0", "timestamp": "2026-07-06T02:00:02", "components": components})
        (backup_path / "metadata.json").write_text(text)

    return backup_path


# --- validate_backup_structure ----------------------------------------------


def test_structure_rejects_a_missing_path(tmp_path):
    result = verify_backup.validate_backup_structure(tmp_path / "nope")

    assert result["valid"] is False
    assert any("does not exist" in error for error in result["errors"])


def test_structure_rejects_an_unrecognised_file(tmp_path):
    stray = tmp_path / "notes.txt"
    stray.write_text("not a backup")

    result = verify_backup.validate_backup_structure(stray)

    assert result["valid"] is False
    assert any("not a directory or recognized file" in error for error in result["errors"])


def test_structure_rejects_a_directory_with_an_unknown_name(tmp_path):
    unknown = tmp_path / "random_directory"
    unknown.mkdir()

    result = verify_backup.validate_backup_structure(unknown)

    assert result["valid"] is False
    assert any("Unknown backup type" in error for error in result["errors"])


def test_structure_rejects_a_system_backup_without_metadata(tmp_path):
    backup_path = make_system_backup(tmp_path, write_metadata=False)

    result = verify_backup.validate_backup_structure(backup_path)

    assert result["valid"] is False
    assert "No metadata.json file found" in result["errors"]


def test_structure_rejects_unparseable_metadata(tmp_path):
    backup_path = make_system_backup(tmp_path, metadata_text="{not json at all")

    result = verify_backup.validate_backup_structure(backup_path)

    assert result["valid"] is False
    assert any("Invalid metadata file" in error for error in result["errors"])


def test_structure_accepts_a_legacy_single_file_backup(tmp_path):
    legacy = tmp_path / "cti_scraper_backup_20260706_020002.sql.gz"
    legacy.write_bytes(DUMP_BODY)

    result = verify_backup.validate_backup_structure(legacy)

    assert result["valid"] is True
    assert result["backup_type"] == "legacy_database"
    assert result["version"] == "1.0"


def test_structure_accepts_a_complete_system_backup(tmp_path):
    backup_path = make_system_backup(tmp_path)

    result = verify_backup.validate_backup_structure(backup_path)

    assert result["valid"] is True
    assert result["backup_type"] == "system"
    assert result["version"] == "2.0"
    assert result["metadata"]["components"]["database"]["filename"] == DUMP_NAME
    # The database component is a dump file, not a directory, so it must be
    # exempt from the directory-exists check — a healthy backup reports no
    # warnings at all.
    assert result["warnings"] == []


def test_structure_warns_when_an_expected_component_is_absent(tmp_path):
    backup_path = make_system_backup(
        tmp_path,
        components={"database": {"filename": DUMP_NAME, "checksum": sha256(DUMP_BODY)}, "models": {"files": 1}},
    )

    result = verify_backup.validate_backup_structure(backup_path)

    # Missing components downgrade to warnings, not errors — the backup is still
    # restorable, just narrower than configured.
    assert result["valid"] is True
    assert any("'config' not found" in warning for warning in result["warnings"])
    assert any("'outputs' not found" in warning for warning in result["warnings"])


def test_structure_warns_when_a_declared_component_directory_is_missing(tmp_path):
    backup_path = make_system_backup(tmp_path)
    (backup_path / "outputs").rmdir()

    result = verify_backup.validate_backup_structure(backup_path)

    assert result["valid"] is True
    assert any("Component directory 'outputs' not found" in warning for warning in result["warnings"])


# --- validate_file_checksums -------------------------------------------------


def test_checksums_accept_an_intact_dump(tmp_path):
    backup_path = make_system_backup(tmp_path)
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is True
    assert result["files_checked"] == 1
    assert result["files_valid"] == 1
    assert result["errors"] == []


def test_checksums_detect_a_single_flipped_byte(tmp_path):
    backup_path = make_system_backup(tmp_path)
    metadata = json.loads((backup_path / "metadata.json").read_text())

    corrupted = bytearray(DUMP_BODY)
    corrupted[0] ^= 0x01
    (backup_path / DUMP_NAME).write_bytes(bytes(corrupted))

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is False
    assert result["files_checked"] == 1
    assert result["files_valid"] == 0
    assert any("checksum mismatch" in error for error in result["errors"])


def test_checksums_detect_a_truncated_dump(tmp_path):
    backup_path = make_system_backup(tmp_path)
    metadata = json.loads((backup_path / "metadata.json").read_text())
    (backup_path / DUMP_NAME).write_bytes(DUMP_BODY[: len(DUMP_BODY) // 2])

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is False
    assert any("checksum mismatch" in error for error in result["errors"])


def test_checksums_warn_but_pass_when_no_checksum_was_recorded(tmp_path):
    # The dump is present and non-empty; only the digest is missing from the
    # manifest, so there is nothing to compare against.
    backup_path = make_system_backup(tmp_path, components={"database": {"filename": DUMP_NAME}})
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is True
    assert result["files_checked"] == 0
    assert any("No checksum recorded" in warning for warning in result["warnings"])


def test_checksums_ignore_non_dict_component_entries(tmp_path):
    backup_path = make_system_backup(
        tmp_path,
        components={"database": {"filename": DUMP_NAME, "checksum": sha256(DUMP_BODY)}, "notes": "free text"},
    )
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is True
    assert result["files_checked"] == 1


def test_checksums_fail_when_the_declared_dump_file_is_missing(tmp_path):
    # A backup whose dump never landed (or was deleted afterwards) has nothing
    # to restore, so verification must fail rather than warn.
    backup_path = make_system_backup(tmp_path, dump_body=None)
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is False
    assert any("not found" in error for error in result["errors"])


def test_checksums_fail_on_a_zero_byte_dump(tmp_path):
    backup_path = make_system_backup(tmp_path, dump_body=b"")
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is False
    assert any("is empty" in error for error in result["errors"])


def test_checksums_fail_when_the_database_component_only_records_an_error(tmp_path):
    # create_system_backup() writes this shape when the pg_dump step fails; the
    # resulting backup has no dump file and must never verify as valid.
    backup_path = make_system_backup(
        tmp_path,
        components={"database": {"errors": ["Database backup failed: container not running"]}},
        dump_body=None,
    )
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_file_checksums(backup_path, metadata)

    assert result["valid"] is False
    assert "Database component declares no backup filename" in result["errors"]


# --- validate_critical_files -------------------------------------------------


def test_critical_files_counts_populated_files_as_valid(tmp_path):
    backup_path = make_system_backup(tmp_path)
    (backup_path / "config" / "backup.yaml").write_text("retention: {daily: 7}")
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_critical_files(backup_path, metadata)

    assert result["files_checked"] == 1
    assert result["files_valid"] == 1
    assert result["warnings"] == []


def test_critical_files_flags_zero_byte_files(tmp_path):
    backup_path = make_system_backup(tmp_path)
    (backup_path / "config" / "backup.yaml").touch()
    metadata = json.loads((backup_path / "metadata.json").read_text())

    result = verify_backup.validate_critical_files(backup_path, metadata)

    assert result["files_checked"] == 1
    assert result["files_valid"] == 0
    assert any("Invalid or empty file" in warning for warning in result["warnings"])


# --- verify_backup end to end ------------------------------------------------


def test_verify_passes_on_an_intact_backup(tmp_path):
    backup_path = make_system_backup(tmp_path)

    result = verify_backup.verify_backup(backup_path.name, backup_dir=str(tmp_path))

    assert result["overall_valid"] is True
    assert result["tests"]["structure"]["valid"] is True
    assert result["tests"]["checksums"]["files_valid"] == 1


def test_verify_fails_on_a_corrupted_dump(tmp_path):
    backup_path = make_system_backup(tmp_path)
    (backup_path / DUMP_NAME).write_bytes(b"corrupted payload")

    result = verify_backup.verify_backup(backup_path.name, backup_dir=str(tmp_path))

    assert result["overall_valid"] is False
    assert result["tests"]["checksums"]["valid"] is False


def test_verify_fails_and_short_circuits_when_metadata_is_missing(tmp_path):
    backup_path = make_system_backup(tmp_path, write_metadata=False)

    result = verify_backup.verify_backup(backup_path.name, backup_dir=str(tmp_path))

    assert result["overall_valid"] is False
    # Structure failure must stop the run: later phases would be meaningless
    # without metadata to check against.
    assert "checksums" not in result["tests"]
    assert "critical_files" not in result["tests"]


def test_verify_fails_for_a_backup_with_no_dump_file(tmp_path):
    # The database component is declared in metadata but the dump file is
    # absent — an unrestorable backup must not report as VALID.
    backup_path = make_system_backup(tmp_path, dump_body=None)

    result = verify_backup.verify_backup(backup_path.name, backup_dir=str(tmp_path))

    assert result["overall_valid"] is False
    assert any("not found" in error for error in result["tests"]["checksums"]["errors"])
