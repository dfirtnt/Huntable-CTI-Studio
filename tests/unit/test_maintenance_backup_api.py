"""Regression tests for the Docker-privileged maintenance boundary."""

from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException

from src.maintenance import main

pytestmark = pytest.mark.unit


def test_create_requires_the_shared_maintenance_token(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "secret")

    with pytest.raises(HTTPException, match="Forbidden") as exc_info:
        main.create_backup(main.CreateRequest(), x_maintenance_token="wrong")

    assert exc_info.value.status_code == 403


def test_restore_revalidates_path_and_uses_fixed_database_script(monkeypatch, tmp_path):
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "secret")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(main, "_run", lambda args, timeout: calls.append((args, timeout)) or {"returncode": 0})

    response = main.restore_backup(
        main.RestoreRequest(backup_name="backup_20260812_112100.sql", backup_dir="backups", no_snapshot=True),
        x_maintenance_token="secret",
    )

    assert response == {"returncode": 0}
    args, timeout = calls[0]
    assert args[1] == str(tmp_path / "scripts/restore_database.py")
    assert args[-2:] == ["--force", "--no-snapshot"]
    assert timeout == 600


def test_restore_rejects_traversal_even_when_called_without_the_web_route(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "secret")

    with pytest.raises(HTTPException) as exc_info:
        main.restore_backup(
            main.RestoreRequest(backup_name="../backup_20260812_112100.sql", backup_dir="backups"),
            x_maintenance_token="secret",
        )

    assert exc_info.value.status_code == 400


def test_restore_file_decodes_only_allowed_uploads_and_removes_temp_file(monkeypatch):
    monkeypatch.setenv("MAINTENANCE_API_TOKEN", "secret")
    seen = []
    monkeypatch.setattr(main, "_run", lambda args, timeout: seen.append(args) or {"returncode": 0})

    result = main.restore_file(
        main.RestoreFileRequest(content_base64=base64.b64encode(b"SELECT 1").decode(), suffix=".sql"),
        x_maintenance_token="secret",
    )

    assert result == {"returncode": 0}
    assert seen[0][1].endswith("scripts/restore_database_v2.py")
    assert not __import__("pathlib").Path(seen[0][2]).exists()
