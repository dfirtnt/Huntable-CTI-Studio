"""Edge case tests for _compute_ingestion_health severity model."""

from types import SimpleNamespace

import pytest

from src.web.routes.dashboard import _compute_ingestion_health

pytestmark = pytest.mark.unit


def _source(identifier, *, active=True, consecutive_failures=0):
    return SimpleNamespace(
        identifier=identifier,
        active=active,
        consecutive_failures=consecutive_failures,
    )


def test_all_healthy_sources_returns_nominal():
    sources = [_source(f"s{i}") for i in range(5)]
    health = _compute_ingestion_health(sources)

    assert health["status"] == "nominal"
    assert health["label"] == "Nominal"
    assert health["uptime"] == 100.0
    assert health["healthy_sources"] == 5
    assert health["warning_sources"] == 0
    assert health["critical_sources"] == 0


def test_empty_source_list_returns_critical():
    health = _compute_ingestion_health([])
    assert health["status"] == "critical"
    assert health["uptime"] == 0.0
    assert health["monitored_sources"] == 0


def test_all_sources_excluded_returns_critical():
    sources = [
        _source("manual"),
        _source("eval_articles"),
    ]
    health = _compute_ingestion_health(sources)
    assert health["status"] == "critical"
    assert health["monitored_sources"] == 0


def test_all_inactive_sources_returns_critical():
    sources = [_source("s1", active=False), _source("s2", active=False)]
    health = _compute_ingestion_health(sources)
    assert health["status"] == "critical"
    assert health["monitored_sources"] == 0


def test_none_consecutive_failures_treated_as_zero():
    source = _source("s1")
    source.consecutive_failures = None
    health = _compute_ingestion_health([source])

    assert health["status"] == "nominal"
    assert health["healthy_sources"] == 1


def test_single_warning_source_is_degraded():
    sources = [_source("s1", consecutive_failures=1)]
    health = _compute_ingestion_health(sources)

    assert health["status"] == "degraded"
    assert health["warning_sources"] == 1
    assert health["uptime"] == 50.0


def test_single_critical_source_is_degraded_below_threshold():
    sources = [
        _source("s1", consecutive_failures=3),
        _source("s2"),
        _source("s3"),
        _source("s4"),
        _source("s5"),
    ]
    health = _compute_ingestion_health(sources)

    assert health["status"] == "degraded"
    assert health["critical_sources"] == 1


def test_missing_active_attribute_defaults_to_included():
    source = SimpleNamespace(identifier="s1", consecutive_failures=0)
    health = _compute_ingestion_health([source])

    assert health["status"] == "nominal"
    assert health["monitored_sources"] == 1


def test_missing_consecutive_failures_attribute_defaults_to_zero():
    source = SimpleNamespace(identifier="s1", active=True)
    health = _compute_ingestion_health([source])

    assert health["status"] == "nominal"
    assert health["healthy_sources"] == 1


def test_boundary_failure_count_2_is_warning_3_is_critical():
    warning_src = _source("w", consecutive_failures=2)
    critical_src = _source("c", consecutive_failures=3)

    h_warning = _compute_ingestion_health([warning_src, _source("h1")])
    assert h_warning["warning_sources"] == 1
    assert h_warning["critical_sources"] == 0

    h_critical = _compute_ingestion_health([critical_src, _source("h1")])
    assert h_critical["warning_sources"] == 0
    assert h_critical["critical_sources"] == 1


def test_uptime_weights_warning_at_half():
    sources = [
        _source("s1"),
        _source("s2", consecutive_failures=1),
    ]
    health = _compute_ingestion_health(sources)

    assert health["uptime"] == pytest.approx(75.0, abs=0.1)
