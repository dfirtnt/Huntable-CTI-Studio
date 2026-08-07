"""Tests for the backup-producing half of scripts/backup_system.py.

Covers the file-selection and integrity primitives that decide what actually
lands in a system backup — gitignore filtering, always-include overrides,
critical-file validation, and the SHA-256 manifest the verifier later checks.
A backup that succeeds while containing the wrong bytes is the failure mode
these tests exist to catch.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import backup_system  # noqa: E402
import verify_backup  # noqa: E402

pytestmark = pytest.mark.unit


# --- checksums ---------------------------------------------------------------


def test_calculate_checksum_matches_hashlib(tmp_path):
    payload = b"-- PostgreSQL database dump\nCOPY articles (id) FROM stdin;\n"
    dump = tmp_path / "dump.sql"
    dump.write_bytes(payload)

    assert backup_system.calculate_checksum(dump) == hashlib.sha256(payload).hexdigest()


def test_calculate_checksum_is_stable_across_chunk_boundaries(tmp_path):
    # The implementation reads in 4 KiB chunks; a file spanning several chunks
    # must hash identically to a single-shot hash of the same bytes.
    payload = bytes(range(256)) * 200
    dump = tmp_path / "large.sql"
    dump.write_bytes(payload)

    assert backup_system.calculate_checksum(dump) == hashlib.sha256(payload).hexdigest()


def test_calculate_checksum_returns_empty_string_when_unreadable(tmp_path):
    # backup_system swallows the error and returns "", which then cannot match
    # any real digest — verification fails loudly rather than the backup dying.
    assert backup_system.calculate_checksum(tmp_path) == ""


# --- gitignore parsing -------------------------------------------------------


def test_get_gitignore_patterns_skips_comments_and_blank_lines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".gitignore").write_text("# comment\n\n*.log\n  \nvenv/\n.env\n")

    assert backup_system.get_gitignore_patterns() == ["*.log", "venv/", ".env"]


def test_get_gitignore_patterns_returns_empty_without_a_gitignore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert backup_system.get_gitignore_patterns() == []


def test_should_ignore_path_matches_file_patterns_by_name():
    patterns = ["*.log", ".env"]

    assert backup_system.should_ignore_path(Path("logs/backup.log"), patterns) is True
    assert backup_system.should_ignore_path(Path(".env"), patterns) is True
    assert backup_system.should_ignore_path(Path("config/backup.yaml"), patterns) is False


def test_should_ignore_path_matches_directory_patterns_relative_to_the_walk_root():
    patterns = ["venv/"]

    assert backup_system.should_ignore_path(Path("venv"), patterns) is True
    assert backup_system.should_ignore_path(Path("venv/lib/site-packages"), patterns) is True


def test_should_ignore_path_directory_patterns_do_not_match_nested_absolute_paths():
    # Characterisation: directory patterns are anchored to the string form of
    # the path, so a gitignored directory nested below the walk root is NOT
    # filtered. This errs towards including more data in a backup, but it means
    # .gitignore coverage is weaker than it looks.
    assert backup_system.should_ignore_path(Path("/srv/app/venv/lib"), ["venv/"]) is False


def test_should_ignore_path_returns_false_with_no_patterns():
    assert backup_system.should_ignore_path(Path("config/backup.yaml"), []) is False


# --- critical file validation ------------------------------------------------


def test_validate_critical_files_reports_a_missing_directory(tmp_path):
    valid_files, errors = backup_system.validate_critical_files(tmp_path / "absent", ["*.yaml"])

    assert valid_files == []
    assert errors == [f"Directory does not exist: {tmp_path / 'absent'}"]


def test_validate_critical_files_reports_patterns_with_no_matches(tmp_path):
    (tmp_path / "backup.yaml").write_text("retention: {daily: 7}")

    valid_files, errors = backup_system.validate_critical_files(tmp_path, ["*.yaml", "*.pkl"])

    assert [path.name for path in valid_files] == ["backup.yaml"]
    assert any("No files found matching pattern '*.pkl'" in error for error in errors)


def test_validate_critical_files_rejects_zero_byte_files(tmp_path):
    (tmp_path / "empty.yaml").touch()

    valid_files, errors = backup_system.validate_critical_files(tmp_path, ["*.yaml"])

    assert valid_files == []
    assert any("Invalid or empty file" in error for error in errors)


def test_validate_critical_files_accepts_populated_files(tmp_path):
    (tmp_path / "backup.yaml").write_text("retention: {daily: 7}")
    (tmp_path / "sources.yaml").write_text("sources: []")

    valid_files, errors = backup_system.validate_critical_files(tmp_path, ["*.yaml"])

    assert sorted(path.name for path in valid_files) == ["backup.yaml", "sources.yaml"]
    assert errors == []


# --- directory backup --------------------------------------------------------


def build_source_tree(root: Path) -> Path:
    source = root / "config"
    (source / "presets" / "private").mkdir(parents=True)
    (source / "presets" / "public").mkdir(parents=True)
    (source / "backup.yaml").write_text("retention: {daily: 7}")
    (source / "presets" / "public" / "quickstart.json").write_text("{}")
    (source / "presets" / "private" / "operator.json").write_text("{}")
    (source / "debug.log").write_text("noise")
    return source


def test_backup_directory_preserves_the_source_tree(tmp_path):
    source = build_source_tree(tmp_path)
    backup_dir = tmp_path / "system_backup_20260706_020002"
    backup_dir.mkdir()

    result = backup_system.backup_directory(source, backup_dir, "config", [], respect_gitignore=False)

    assert result["errors"] == []
    assert result["files"] == 4
    assert result["size_mb"] > 0
    assert (backup_dir / "config" / "backup.yaml").read_text() == "retention: {daily: 7}"
    assert (backup_dir / "config" / "presets" / "public" / "quickstart.json").exists()
    assert (backup_dir / "config" / "presets" / "private" / "operator.json").exists()


def test_backup_directory_skips_ignored_files(tmp_path):
    source = build_source_tree(tmp_path)
    backup_dir = tmp_path / "system_backup_20260706_020002"
    backup_dir.mkdir()

    result = backup_system.backup_directory(source, backup_dir, "config", ["*.log"], respect_gitignore=True)

    assert result["files"] == 3
    assert not (backup_dir / "config" / "debug.log").exists()
    assert (backup_dir / "config" / "backup.yaml").exists()


def test_backup_directory_always_include_overrides_the_ignore_list(tmp_path):
    # Private workflow presets are gitignored on purpose but must still be
    # captured, which is what always_include_paths exists for.
    source = build_source_tree(tmp_path)
    backup_dir = tmp_path / "system_backup_20260706_020002"
    backup_dir.mkdir()

    result = backup_system.backup_directory(
        source,
        backup_dir,
        "config",
        ["private", "*.log"],
        respect_gitignore=True,
        always_include_paths=[source / "presets" / "private"],
    )

    assert (backup_dir / "config" / "presets" / "private" / "operator.json").exists()
    assert not (backup_dir / "config" / "debug.log").exists()
    assert result["errors"] == []


def test_backup_directory_without_always_include_drops_the_ignored_subtree(tmp_path):
    # The inverse of the test above: without the override the same pattern
    # silently excludes the private presets.
    source = build_source_tree(tmp_path)
    backup_dir = tmp_path / "system_backup_20260706_020002"
    backup_dir.mkdir()

    backup_system.backup_directory(source, backup_dir, "config", ["private", "*.log"], respect_gitignore=True)

    assert not (backup_dir / "config" / "presets" / "private").exists()
    assert (backup_dir / "config" / "presets" / "public" / "quickstart.json").exists()


def test_backup_directory_reports_a_missing_source_without_raising(tmp_path):
    backup_dir = tmp_path / "system_backup_20260706_020002"
    backup_dir.mkdir()

    result = backup_system.backup_directory(tmp_path / "absent", backup_dir, "models", [])

    assert result["files"] == 0
    assert result["size_mb"] == 0.0
    assert result["errors"] == [f"Source directory does not exist: {tmp_path / 'absent'}"]


# --- manifest contract -------------------------------------------------------


def test_manifest_checksum_written_by_backup_system_satisfies_verify_backup(tmp_path):
    """The producer and the verifier must agree on the digest.

    backup_system.calculate_checksum writes metadata.json; verify_backup
    recomputes it independently. If either side changed algorithm, chunking, or
    encoding, every backup would verify as corrupt — this pins the contract.
    """
    source = build_source_tree(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup_path = backup_dir / "system_backup_20260706_020002"
    backup_path.mkdir()

    dump_name = "cti_scraper_backup_20260706_020002.sql.gz"
    dump_path = backup_path / dump_name
    dump_path.write_bytes(b"-- PostgreSQL database dump\nCOPY articles (id) FROM stdin;\n")

    config_result = backup_system.backup_directory(source, backup_path, "config", ["*.log"], respect_gitignore=True)

    metadata = {
        "version": "2.0",
        "timestamp": "2026-07-06T02:00:02",
        "backup_name": backup_path.name,
        "components": {
            "database": {
                "filename": dump_name,
                "checksum": backup_system.calculate_checksum(dump_path),
                "size_mb": dump_path.stat().st_size / (1024 * 1024),
            },
            "config": config_result,
        },
    }
    (backup_path / "metadata.json").write_text(json.dumps(metadata))

    result = verify_backup.verify_backup(backup_path.name, backup_dir=str(backup_dir))

    assert result["tests"]["checksums"]["valid"] is True
    assert result["tests"]["checksums"]["files_checked"] == 1
    assert result["tests"]["checksums"]["files_valid"] == 1
    assert result["overall_valid"] is True


def test_verify_rejects_a_manifest_whose_dump_was_swapped_after_the_backup(tmp_path):
    source = build_source_tree(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup_path = backup_dir / "system_backup_20260706_020002"
    backup_path.mkdir()

    dump_name = "cti_scraper_backup_20260706_020002.sql.gz"
    dump_path = backup_path / dump_name
    dump_path.write_bytes(b"-- PostgreSQL database dump\nCOPY articles (id) FROM stdin;\n")

    metadata = {
        "version": "2.0",
        "timestamp": "2026-07-06T02:00:02",
        "components": {
            "database": {"filename": dump_name, "checksum": backup_system.calculate_checksum(dump_path)},
            "config": backup_system.backup_directory(source, backup_path, "config", [], respect_gitignore=False),
        },
    }
    (backup_path / "metadata.json").write_text(json.dumps(metadata))

    dump_path.write_bytes(b"-- PostgreSQL database dump\nCOPY articles (id) FROM stdin;\n-- tampered\n")

    result = verify_backup.verify_backup(backup_path.name, backup_dir=str(backup_dir))

    assert result["overall_valid"] is False
    assert any("checksum mismatch" in error for error in result["tests"]["checksums"]["errors"])
