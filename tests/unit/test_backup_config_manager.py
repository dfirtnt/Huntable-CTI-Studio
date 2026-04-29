"""Unit tests for BackupConfigManager validation, env overrides, and helper methods."""

from __future__ import annotations

import pytest
import yaml

from src.utils.backup_config import BackupConfigManager

pytestmark = pytest.mark.unit


class TestValidateConfig:
    """validate_config() must catch every class of invalid value."""

    def _manager(self) -> BackupConfigManager:
        return BackupConfigManager(config_file="/nonexistent.yaml", environment="development")

    def test_valid_defaults_produce_no_errors(self):
        errors = self._manager().validate_config()
        assert errors == []

    # ---- time fields ----

    def test_invalid_backup_time_format_non_numeric(self):
        m = self._manager()
        m.get_config().backup_time = "noon"
        errors = m.validate_config()
        assert any("backup_time" in e for e in errors)

    def test_invalid_backup_time_out_of_range(self):
        m = self._manager()
        m.get_config().backup_time = "25:00"
        errors = m.validate_config()
        assert any("backup_time" in e for e in errors)

    def test_invalid_cleanup_time_format(self):
        m = self._manager()
        m.get_config().cleanup_time = "03-30"
        errors = m.validate_config()
        assert any("cleanup_time" in e for e in errors)

    def test_valid_boundary_times_produce_no_errors(self):
        m = self._manager()
        m.get_config().backup_time = "00:00"
        m.get_config().cleanup_time = "23:59"
        assert m.validate_config() == []

    # ---- retention ----

    def test_negative_daily_retention_is_rejected(self):
        m = self._manager()
        m.get_config().daily = -1
        errors = m.validate_config()
        assert any("daily" in e for e in errors)

    def test_zero_max_size_gb_is_rejected(self):
        m = self._manager()
        m.get_config().max_size_gb = 0
        errors = m.validate_config()
        assert any("max_size_gb" in e for e in errors)

    def test_zero_daily_retention_is_allowed(self):
        m = self._manager()
        m.get_config().daily = 0
        assert m.validate_config() == []

    # ---- backup type ----

    def test_invalid_backup_type_rejected(self):
        m = self._manager()
        m.get_config().backup_type = "incremental"
        errors = m.validate_config()
        assert any("backup_type" in e for e in errors)

    def test_valid_backup_types_accepted(self):
        for btype in ("full", "database", "files"):
            m = self._manager()
            m.get_config().backup_type = btype
            assert m.validate_config() == [], f"{btype!r} should be valid"

    # ---- log level ----

    def test_invalid_log_level_rejected(self):
        m = self._manager()
        m.get_config().log_level = "TRACE"
        errors = m.validate_config()
        assert any("log_level" in e for e in errors)

    def test_valid_log_levels_accepted(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            m = self._manager()
            m.get_config().log_level = level
            assert m.validate_config() == [], f"{level!r} should be valid"

    # ---- performance ----

    def test_zero_max_threads_rejected(self):
        m = self._manager()
        m.get_config().max_threads = 0
        errors = m.validate_config()
        assert any("max_threads" in e for e in errors)

    def test_zero_timeout_rejected(self):
        m = self._manager()
        m.get_config().timeout = 0
        errors = m.validate_config()
        assert any("timeout" in e for e in errors)

    def test_multiple_errors_returned_together(self):
        m = self._manager()
        m.get_config().backup_type = "bad"
        m.get_config().log_level = "VERBOSE"
        m.get_config().max_size_gb = -5
        errors = m.validate_config()
        assert len(errors) >= 3


class TestEnvironmentOverrides:
    """Environment-specific YAML sections must override base config."""

    def test_production_env_overrides_backup_time(self, tmp_path):
        config_path = tmp_path / "backup.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "schedule": {"backup_time": "02:00", "cleanup_time": "03:00", "cleanup_day": 0},
                    "environments": {
                        "production": {
                            "schedule": {"backup_time": "01:00"},
                        }
                    },
                }
            )
        )

        manager = BackupConfigManager(config_file=str(config_path), environment="production")
        assert manager.get_config().backup_time == "01:00"

    def test_unknown_environment_leaves_base_config_unchanged(self, tmp_path):
        config_path = tmp_path / "backup.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "schedule": {"backup_time": "02:00", "cleanup_time": "03:00", "cleanup_day": 0},
                    "environments": {
                        "staging": {"schedule": {"backup_time": "04:00"}},
                    },
                }
            )
        )

        manager = BackupConfigManager(config_file=str(config_path), environment="production")
        assert manager.get_config().backup_time == "02:00"

    def test_empty_yaml_file_leaves_defaults(self, tmp_path):
        config_path = tmp_path / "backup.yaml"
        config_path.write_text("")
        manager = BackupConfigManager(config_file=str(config_path))
        assert manager.get_config().backup_time == "02:00"

    def test_missing_config_file_leaves_defaults(self):
        manager = BackupConfigManager(config_file="/nonexistent/path/backup.yaml")
        assert manager.get_config().daily == 7


class TestHelperMethods:
    """Helper accessor methods must return correct slices of config state."""

    def _manager(self) -> BackupConfigManager:
        return BackupConfigManager(config_file="/nonexistent.yaml")

    def test_get_retention_policy_keys(self):
        policy = self._manager().get_retention_policy()
        assert set(policy.keys()) == {"daily", "weekly", "monthly", "max_size_gb"}

    def test_get_schedule_config_keys(self):
        schedule = self._manager().get_schedule_config()
        assert set(schedule.keys()) == {"backup_time", "cleanup_time", "cleanup_day"}

    def test_get_backup_settings_keys(self):
        settings = self._manager().get_backup_settings()
        assert set(settings.keys()) == {"directory", "compress", "verify", "type"}

    def test_get_components_returns_all_six(self):
        components = self._manager().get_components()
        expected = {"database", "models", "config", "outputs", "logs", "docker_volumes"}
        assert set(components.keys()) == expected

    def test_get_docker_volumes_is_copy(self):
        manager = self._manager()
        volumes = manager.get_docker_volumes()
        volumes.append("injected")
        assert "injected" not in manager.get_docker_volumes()

    def test_get_critical_patterns_is_copy(self):
        manager = self._manager()
        patterns = manager.get_critical_patterns()
        patterns["injected"] = ["*.bad"]
        assert "injected" not in manager.get_critical_patterns()
