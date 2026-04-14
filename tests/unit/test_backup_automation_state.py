"""Unit tests for get_backup_automation_state and set_backup_automation_state.

These cover the shared-state persistence layer used by BackupCronService when
crontab is unavailable (e.g. running inside a container that can't read the
host crontab).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.backup_config import get_backup_automation_state, set_backup_automation_state

pytestmark = pytest.mark.unit


class TestGetBackupAutomationState:
    """get_backup_automation_state reads and normalizes persisted JSON."""

    def test_returns_default_when_file_missing(self, tmp_path):
        state = get_backup_automation_state(tmp_path / "nonexistent.json")
        assert state == {"enabled": False, "backend": None, "updated_at": None}

    def test_reads_enabled_true(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps({"enabled": True, "backend": "cron", "updated_at": "2026-04-14T00:00:00+00:00"})
        )
        state = get_backup_automation_state(state_file)
        assert state["enabled"] is True
        assert state["backend"] == "cron"
        assert state["updated_at"] == "2026-04-14T00:00:00+00:00"

    def test_reads_enabled_false(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"enabled": False, "backend": None, "updated_at": None}))
        state = get_backup_automation_state(state_file)
        assert state["enabled"] is False

    def test_returns_default_for_corrupt_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text("{not valid json")
        state = get_backup_automation_state(state_file)
        assert state == {"enabled": False, "backend": None, "updated_at": None}

    def test_returns_default_for_non_dict_json(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps([1, 2, 3]))
        state = get_backup_automation_state(state_file)
        assert state == {"enabled": False, "backend": None, "updated_at": None}

    def test_missing_keys_fall_back_to_defaults(self, tmp_path):
        """Partial state file (e.g. manually edited) should not raise."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"enabled": True}))
        state = get_backup_automation_state(state_file)
        assert state["enabled"] is True
        assert state["backend"] is None
        assert state["updated_at"] is None


class TestSetBackupAutomationState:
    """set_backup_automation_state persists state and creates parent dirs."""

    def test_writes_enabled_true(self, tmp_path):
        state_file = tmp_path / "config" / "state.json"
        result = set_backup_automation_state(True, backend="cron", state_file=state_file)
        assert result is True
        assert state_file.exists()
        payload = json.loads(state_file.read_text())
        assert payload["enabled"] is True
        assert payload["backend"] == "cron"
        assert "updated_at" in payload

    def test_writes_enabled_false(self, tmp_path):
        state_file = tmp_path / "state.json"
        set_backup_automation_state(False, state_file=state_file)
        payload = json.loads(state_file.read_text())
        assert payload["enabled"] is False

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "state.json"
        result = set_backup_automation_state(True, state_file=nested)
        assert result is True
        assert nested.exists()

    def test_roundtrip_with_get(self, tmp_path):
        """set then get should return the same values."""
        state_file = tmp_path / "state.json"
        set_backup_automation_state(True, backend="cron", state_file=state_file)
        state = get_backup_automation_state(state_file)
        assert state["enabled"] is True
        assert state["backend"] == "cron"

    def test_overwrite_updates_value(self, tmp_path):
        state_file = tmp_path / "state.json"
        set_backup_automation_state(True, state_file=state_file)
        set_backup_automation_state(False, state_file=state_file)
        state = get_backup_automation_state(state_file)
        assert state["enabled"] is False

    def test_returns_false_on_unwritable_path(self, tmp_path):
        """Write failure must return False, not raise."""
        unwritable = Path("/proc/no_such_dir/state.json")
        result = set_backup_automation_state(True, state_file=unwritable)
        assert result is False
