"""API tests for backup cron management endpoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.web.routes import backup as backup_routes


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_backup_cron_returns_state(monkeypatch):
    """GET handler should surface cron state payload."""
    expected = {
        "cron_available": True,
        "automated": True,
        "jobs": [
            {
                "schedule": "0 2 * * *",
                "command": "echo hi",
                "managed": False,
                "kind": "external",
                "comment": None,
                "raw": "0 2 * * * echo hi",
            }
        ],
        "managed_jobs": [],
        "config": {"backup_time": "02:00"},
    }
    monkeypatch.setattr(backup_routes, "_get_cron_state", lambda: expected)

    result = await backup_routes.api_get_backup_cron()

    assert result["success"] is True
    assert result["cron_available"] is True
    assert result["config"]["backup_time"] == "02:00"


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_backup_cron_saves_config_and_applies_when_requested(monkeypatch):
    """POST handler should save config and install managed cron jobs when requested."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

        def validate_config(self):
            return []

        def save_config(self):
            return True

    class FakeService:
        def get_state(self, cfg):
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [],
                "managed_jobs": [],
                "config": {"backup_time": cfg.backup_time},
            }

        def install_backup_schedule(self, cfg):
            return {
                "cron_available": True,
                "automated": True,
                "jobs": [],
                "managed_jobs": [{"kind": "backup"}],
                "config": {"backup_time": cfg.backup_time},
            }

    monkeypatch.setattr(backup_routes, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_routes, "BackupCronService", lambda: FakeService())

    payload = backup_routes.BackupCronUpdate(
        backup_time="04:20",
        cleanup_time="05:30",
        daily=8,
        weekly=4,
        monthly=2,
        max_size_gb=60,
        backup_dir="archives",
        backup_type="database",
        compress=False,
        verify=True,
        install_crontab=True,
    )

    result = await backup_routes.api_update_backup_cron(payload)

    assert result["success"] is True
    assert result["crontab_applied"] is True
    assert result["automated"] is True
    assert config.backup_time == "04:20"
    assert config.backup_type == "database"
    assert config.compress is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_delete_backup_cron_removes_managed_jobs(monkeypatch):
    """DELETE handler should call service removal and return updated state."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

    class FakeService:
        def remove_backup_schedule(self, cfg):
            assert cfg is config
            return {"cron_available": True, "automated": False, "jobs": [], "managed_jobs": [], "config": {}}

    monkeypatch.setattr(backup_routes, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_routes, "BackupCronService", lambda: FakeService())

    result = await backup_routes.api_delete_backup_cron()

    assert result["success"] is True
    assert result["automated"] is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_restore_from_file_rejects_invalid_extension():
    """Only .sql and .sql.gz files should be accepted for file-based restore."""
    from io import BytesIO

    from fastapi import UploadFile

    bad_file = UploadFile(filename="backup.txt", file=BytesIO(b"irrelevant"))
    with pytest.raises(Exception) as exc_info:
        await backup_routes.api_restore_from_file(file=bad_file)
    assert exc_info.value.status_code == 400
    assert "Invalid file type" in str(exc_info.value.detail)


@pytest.mark.api
@pytest.mark.asyncio
async def test_restore_from_file_accepts_sql_extension(monkeypatch, tmp_path):
    """A .sql file should pass extension validation and proceed to script invocation."""
    import subprocess
    from io import BytesIO

    from fastapi import UploadFile

    fake_script = tmp_path / "restore_database_v2.py"
    fake_script.touch()

    monkeypatch.setattr(
        backup_routes,
        "Path",
        lambda *args: fake_script.parent if args == () else __import__("pathlib").Path(*args),
    )

    run_calls: list = []

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="restored", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Patch project_root resolution inside the handler
    original_path = backup_routes.Path

    def patched_path(*args):
        p = original_path(*args)
        if str(p).endswith("restore_database_v2.py"):
            return fake_script
        return p

    monkeypatch.setattr(backup_routes, "Path", patched_path)

    sql_file = UploadFile(filename="backup.sql", file=BytesIO(b"SELECT 1"))
    result = await backup_routes.api_restore_from_file(file=sql_file)
    assert result["success"] is True


@pytest.mark.api
@pytest.mark.asyncio
async def test_restore_from_file_accepts_sql_gz_extension(monkeypatch, tmp_path):
    """A .sql.gz file should pass extension validation."""
    import subprocess
    from io import BytesIO

    from fastapi import UploadFile

    fake_script = tmp_path / "restore_database_v2.py"
    fake_script.touch()
    original_path = backup_routes.Path

    def patched_path(*args):
        p = original_path(*args)
        if str(p).endswith("restore_database_v2.py"):
            return fake_script
        return p

    monkeypatch.setattr(backup_routes, "Path", patched_path)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="restored", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    gz_file = UploadFile(filename="backup.sql.gz", file=BytesIO(b"\x1f\x8b"))
    result = await backup_routes.api_restore_from_file(file=gz_file)
    assert result["success"] is True


@pytest.mark.api
def test_update_backup_cron_requires_no_admin_auth():
    """Regression: POST /api/backup/cron must not require admin auth.

    The Settings page Save button has no mechanism to supply X-API-Key.
    If RequireAdminAuth is re-added to this handler the endpoint returns
    401 for every save, breaking the UI silently.
    """
    import inspect

    from src.web.auth import RequireAdminAuth

    sig = inspect.signature(backup_routes.api_update_backup_cron)
    for param in sig.parameters.values():
        assert param.default is not RequireAdminAuth, (
            "api_update_backup_cron must not use RequireAdminAuth -- the Settings page sends no X-API-Key header"
        )
