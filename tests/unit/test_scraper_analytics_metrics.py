from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.web.routes import analytics

pytestmark = pytest.mark.unit


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        del exc_type, exc, tb
        return False


@pytest.mark.asyncio
async def test_source_performance_includes_collection_breakdown(monkeypatch):
    source = SimpleNamespace(
        id=10,
        name="Example Source",
        active=True,
        last_success=datetime(2026, 6, 26, 8, 30),
    )

    async def fake_list_sources():
        return [source]

    async def fake_ingestion_analytics():
        return {"source_breakdown": [{"source_name": "Example Source", "articles_count": 7}]}

    session = SimpleNamespace()
    session.execute = AsyncMock(
        side_effect=[
            _Result(
                [
                    SimpleNamespace(
                        source_id=10,
                        total=3,
                        failures=1,
                        collected_7d=12,
                        saved_7d=5,
                        filtered_7d=7,
                        zero_yield_runs=2,
                        median_rt=1.25,
                    )
                ]
            ),
            _Result(
                [
                    SimpleNamespace(
                        source_id=10,
                        error_message="selector returned no content",
                        check_metadata={
                            "articles_collected": 4,
                            "articles_saved": 0,
                            "articles_filtered": 4,
                            "zero_yield": True,
                        },
                    )
                ]
            ),
        ]
    )

    monkeypatch.setattr(analytics.async_db_manager, "list_sources", fake_list_sources)
    monkeypatch.setattr(analytics.async_db_manager, "get_ingestion_analytics", fake_ingestion_analytics)
    monkeypatch.setattr(analytics.async_db_manager, "get_session", lambda: _SessionContext(session))

    payload = await analytics.api_scraper_source_performance()

    row = payload["sources"][0]
    assert row["name"] == "Example Source"
    assert row["collected_7d"] == 12
    assert row["saved_7d"] == 5
    assert row["filtered_7d"] == 7
    assert row["latest_collected"] == 4
    assert row["latest_saved"] == 0
    assert row["latest_filtered"] == 4
    assert row["zero_yield"] is True
    assert row["zero_yield_runs"] == 2
    assert row["last_error"] == "selector returned no content"
    assert row["median_response"] == 1250
    assert row["error_rate"] == 33.3
