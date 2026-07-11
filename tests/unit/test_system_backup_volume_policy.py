"""Docker volume backup and restore policy tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from src.utils.backup_config import BackupConfigManager

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import backup_system as backup_system_script  # noqa: E402
import restore_system as restore_system_script  # noqa: E402

pytestmark = pytest.mark.unit


def test_checked_in_backup_config_disables_docker_volumes():
    manager = BackupConfigManager(config_file="config/backup.yaml", environment="development")
    config = manager.get_config()

    assert config.docker_volumes is False
    assert config.volume_list == []


def test_checked_in_backup_yaml_does_not_define_volume_names():
    with open("config/backup.yaml") as f:
        data = yaml.safe_load(f)

    assert data["components"]["docker_volumes"] is False
    assert "docker_volumes" not in data


def test_restore_rejects_requested_legacy_docker_volume_component(tmp_path, capsys):
    backup_path = tmp_path / "system_backup_20260706_020000"
    backup_path.mkdir()
    (backup_path / "metadata.json").write_text(
        json.dumps(
            {
                "version": "2.0",
                "components": {
                    "database": {"filename": "database.sql.gz"},
                    "docker_volume_postgres_data": {
                        "filename": "postgres_data_20260706_020000.tar.gz",
                        "size_mb": 0.00008,
                        "errors": [],
                    },
                },
            }
        )
    )

    success = restore_system_script.restore_system(
        str(backup_path),
        components=["docker_volume_postgres_data"],
        dry_run=True,
    )

    assert success is False
    assert "Docker volume restore is not supported" in capsys.readouterr().out


def test_direct_docker_volume_backup_call_is_disabled(tmp_path):
    result = backup_system_script.backup_docker_volume("postgres_data", tmp_path)

    assert result["filename"] is None
    assert result["size_mb"] == 0.0
    assert result["errors"] == ["Docker volume backup is not supported; PostgreSQL is backed up via pg_dump"]
