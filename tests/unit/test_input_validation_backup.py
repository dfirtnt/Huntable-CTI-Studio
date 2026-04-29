"""Unit tests for backup-specific input validation (validate_backup_name/dir/components)."""

from __future__ import annotations

import pytest

from src.utils.input_validation import (
    ValidationError,
    validate_backup_components,
    validate_backup_dir,
    validate_backup_name,
)

pytestmark = pytest.mark.unit


class TestValidateBackupName:
    """validate_backup_name must enforce format and block injection attempts."""

    def test_valid_database_backup(self):
        result = validate_backup_name("backup_20260428_020000")
        assert result == "backup_20260428_020000"

    def test_valid_system_backup(self):
        result = validate_backup_name("system_backup_20260428_020000")
        assert result == "system_backup_20260428_020000"

    def test_valid_backup_with_extension(self):
        result = validate_backup_name("backup_20260428_020000.sql")
        assert result == "backup_20260428_020000.sql"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="empty"):
            validate_backup_name("")

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError, match="'\\.\\.'"):
            validate_backup_name("../../../etc/passwd")

    def test_absolute_path_rejected(self):
        with pytest.raises(ValidationError, match="absolute"):
            validate_backup_name("/etc/backup_20260428_020000")

    def test_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_name("backup_20260428_020000; rm -rf /")

    def test_backtick_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_name("backup_20260428_020000`id`")

    def test_pipe_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_name("backup_20260428_020000|cat /etc/passwd")

    def test_dollar_sign_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_name("backup_20260428_020000$HOME")

    def test_system_prefix_not_allowed_when_flag_false(self):
        with pytest.raises(ValidationError):
            validate_backup_name("system_backup_20260428_020000", allow_system_prefix=False)

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="too long"):
            validate_backup_name("backup_20260428_020000" + "x" * 240)

    def test_arbitrary_name_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_name("my_backup")


class TestValidateBackupDir:
    """validate_backup_dir must block traversal and injection in directory paths."""

    def test_valid_simple_dir(self):
        assert validate_backup_dir("backups") == "backups"

    def test_valid_nested_dir(self):
        assert validate_backup_dir("backups/daily") == "backups/daily"

    def test_empty_dir_rejected(self):
        with pytest.raises(ValidationError, match="empty"):
            validate_backup_dir("")

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError, match="'\\.\\.'"):
            validate_backup_dir("backups/../../../etc")

    def test_absolute_path_rejected(self):
        with pytest.raises(ValidationError, match="relative"):
            validate_backup_dir("/backups")

    def test_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_dir("backups;rm -rf /")

    def test_dollar_sign_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_dir("backups$HOME")

    def test_spaces_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_dir("my backups")


class TestValidateBackupComponents:
    """validate_backup_components must accept valid component names and reject all others."""

    def test_none_returns_none(self):
        assert validate_backup_components(None) is None

    def test_empty_string_returns_none(self):
        assert validate_backup_components("") is None

    def test_single_valid_component(self):
        assert validate_backup_components("database") == "database"

    def test_multiple_valid_components(self):
        result = validate_backup_components("database,models,config")
        assert result == "database,models,config"

    def test_all_valid_components(self):
        all_valid = "database,models,config,outputs,logs,docker_volumes"
        assert validate_backup_components(all_valid) == all_valid

    def test_unknown_component_rejected(self):
        with pytest.raises(ValidationError, match="Invalid component"):
            validate_backup_components("database,secrets")

    def test_semicolon_in_components_rejected(self):
        with pytest.raises(ValidationError):
            validate_backup_components("database;rm -rf /")

    def test_whitespace_around_components_is_stripped(self):
        result = validate_backup_components("database, models")
        assert result is not None
