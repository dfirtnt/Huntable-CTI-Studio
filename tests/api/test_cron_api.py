"""API tests for generic cron endpoints."""

from __future__ import annotations

import inspect

import pytest

from src.services.backup_cron_service import CronUnavailableError
from src.web.routes import cron as cron_routes

pytestmark = pytest.mark.api


async def _run_async(awaitable):
    return await awaitable


def test_get_cron_returns_snapshot(monkeypatch):
    """GET /api/cron should return the current crontab snapshot."""

    class FakeService:
        def get_snapshot(self):
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [{"schedule": "0 1 * * *", "command": "echo hi", "managed": False, "kind": "external"}],
                "managed_jobs": [],
                "raw": "0 1 * * * echo hi",
            }

    monkeypatch.setattr(cron_routes, "BackupCronService", lambda: FakeService())

    result = __import__("asyncio").run(cron_routes.api_get_cron())

    assert result["success"] is True
    assert result["cron_available"] is True
    assert result["raw"] == "0 1 * * * echo hi"


def test_replace_cron_returns_updated_snapshot(monkeypatch):
    """PUT /api/cron should replace the crontab and return the updated snapshot."""

    class FakeService:
        def replace_crontab(self, content: str):
            assert content == "5 4 * * * echo updated"
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [{"schedule": "5 4 * * *", "command": "echo updated", "managed": False, "kind": "external"}],
                "managed_jobs": [],
                "raw": content,
            }

    monkeypatch.setattr(cron_routes, "BackupCronService", lambda: FakeService())

    result = __import__("asyncio").run(
        cron_routes.api_replace_cron(cron_routes.CronUpdate(content="5 4 * * * echo updated"))
    )

    assert result["success"] is True
    assert result["jobs"][0]["schedule"] == "5 4 * * *"


def test_replace_cron_returns_success_when_cron_unavailable(monkeypatch):
    """Regression: PUT /api/cron must return 200 with cron_available:false when crontab is unavailable.

    On macOS (sandboxed or no Full Disk Access) crontab raises CronUnavailableError.
    Before the fix this propagated as 503, which the Settings page Save button treated
    as a failure and displayed 'Failed to save: cron editor'.
    """

    class FakeService:
        def replace_crontab(self, content: str):
            raise CronUnavailableError("crontab not available in this environment")

        def get_snapshot(self):
            return {
                "cron_available": False,
                "automated": False,
                "jobs": [],
                "managed_jobs": [],
                "raw": "",
            }

    monkeypatch.setattr(cron_routes, "BackupCronService", lambda: FakeService())

    result = __import__("asyncio").run(cron_routes.api_replace_cron(cron_routes.CronUpdate(content="")))

    assert result["success"] is True
    assert result["cron_available"] is False
    assert result["jobs"] == []


def test_cron_endpoints_require_no_admin_auth():
    """Regression: cron endpoints must not have FastAPI Depends() defaults.

    The Settings page sends no X-API-Key header. If either cron handler
    grows a Depends(...) default the endpoint will silently return 401
    and break the cron editor save.
    """
    from fastapi.params import Depends

    for handler in (cron_routes.api_get_cron, cron_routes.api_replace_cron):
        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            assert not isinstance(param.default, Depends), (
                f"{handler.__name__} must not use FastAPI Depends() -- the Settings page does not authenticate"
            )
