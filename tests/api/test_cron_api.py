"""API tests for generic cron endpoints."""

from __future__ import annotations

from src.web.routes import cron as cron_routes


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
