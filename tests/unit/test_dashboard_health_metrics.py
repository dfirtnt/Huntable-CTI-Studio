from types import SimpleNamespace

import pytest

from src.web.routes import metrics
from src.web.routes.dashboard import _compute_ingestion_health

pytestmark = pytest.mark.unit


def _source(identifier: str, *, active: bool = True, consecutive_failures: int = 0):
    return SimpleNamespace(
        identifier=identifier,
        active=active,
        consecutive_failures=consecutive_failures,
    )


def test_compute_ingestion_health_treats_limited_failures_as_degraded():
    sources = [
        _source("source-1"),
        _source("source-2"),
        _source("source-3"),
        _source("source-4"),
        _source("source-5", consecutive_failures=1),
        _source("source-6", consecutive_failures=2),
        _source("manual", consecutive_failures=99),
        _source("inactive-source", active=False, consecutive_failures=99),
    ]

    health = _compute_ingestion_health(sources)

    assert health["status"] == "degraded"
    assert health["label"] == "Degraded"
    assert health["warning_sources"] == 2
    assert health["critical_sources"] == 0
    assert health["monitored_sources"] == 6
    assert health["uptime"] == pytest.approx(83.3, abs=0.1)


def test_compute_ingestion_health_marks_widespread_severe_failures_critical():
    sources = [
        _source("source-1", consecutive_failures=3),
        _source("source-2", consecutive_failures=4),
        _source("source-3", consecutive_failures=5),
        _source("source-4"),
        _source("source-5"),
        _source("source-6"),
        _source("source-7"),
        _source("source-8"),
        _source("source-9"),
        _source("source-10"),
    ]

    health = _compute_ingestion_health(sources)

    assert health["status"] == "critical"
    assert health["label"] == "Critical"
    assert health["critical_sources"] == 3
    assert health["warning_sources"] == 0
    assert health["uptime"] == pytest.approx(70.0, abs=0.1)


@pytest.mark.asyncio
async def test_api_metrics_health_returns_computed_status(monkeypatch):
    sources = [
        _source("source-1"),
        _source("source-2"),
        _source("source-3"),
        _source("source-4"),
        _source("source-5", consecutive_failures=3),
        _source("source-6"),
        _source("eval_articles", consecutive_failures=10),
    ]

    async def fake_list_sources():
        return sources

    monkeypatch.setattr(metrics.async_db_manager, "list_sources", fake_list_sources)

    payload = await metrics.api_metrics_health()

    assert payload["status"] == "degraded"
    assert payload["label"] == "Degraded"
    assert payload["critical_sources"] == 1
    assert payload["warning_sources"] == 0
    assert payload["monitored_sources"] == 6
    assert payload["total_sources"] == 7
    assert payload["uptime"] == pytest.approx(83.3, abs=0.1)


def _article(created_at):
    return SimpleNamespace(created_at=created_at)


def test_hourly_volume_is_a_rolling_24h_window_not_hour_of_day():
    from datetime import datetime, timedelta

    from src.web.routes.dashboard import _bucket_article_volume

    now = datetime(2026, 11, 1, 13, 47)
    articles = [
        _article(datetime(2026, 11, 1, 13, 5)),  # current hour
        _article(datetime(2026, 10, 31, 14, 10)),  # oldest in-window hour
        _article(datetime(2026, 10, 31, 13, 30)),  # 24h+ ago: excluded
        _article(datetime(2026, 10, 20, 13, 0)),  # same hour-of-day, weeks ago: excluded
        _article(None),
    ]

    daily, hourly = _bucket_article_volume(articles, now=now)

    keys = list(hourly)
    assert len(keys) == 24
    assert keys == sorted(keys)  # oldest first, stable order
    assert keys[0] == "2026-10-31T14"
    assert keys[-1] == "2026-11-01T13"
    assert hourly["2026-11-01T13"] == 1
    assert hourly["2026-10-31T14"] == 1
    assert sum(hourly.values()) == 2
    assert daily["2026-11-01"] == 1
    assert daily["2026-10-31"] == 2
    assert "2026-10-20" not in daily
    assert min(daily) == (now - timedelta(days=9)).strftime("%Y-%m-%d")


def test_hourly_volume_accepts_iso_strings_with_timezone():
    from datetime import datetime

    from src.web.routes.dashboard import _bucket_article_volume

    now = datetime.now()
    stamp = now.astimezone().isoformat()
    _, hourly = _bucket_article_volume([_article(stamp)], now=now)
    assert hourly[now.strftime("%Y-%m-%dT%H")] == 1
