"""Contract test: FetchResult public attribute set must remain stable.

FetchResult is consumed by ContentFetcher callers (processor, source_manager).
Any attribute rename or removal is a silent breaking change for those callers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.fetcher import FetchResult
from src.models.source import Source

_REQUIRED_ATTRS = frozenset(
    {
        "source",
        "articles",
        "method",
        "success",
        "error",
        "response_time",
        "rss_parsing_stats",
        "timestamp",
    }
)


def _minimal_source() -> Source:
    now = datetime.now(tz=UTC)
    return Source(
        id=1,
        identifier="test-source",
        name="Test Source",
        url="https://example.com",
        check_frequency=3600,
        lookback_days=7,
        active=True,
        config={},
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.unit
@pytest.mark.contract
def test_fetch_result_attribute_contract():
    """FetchResult exposes a stable public attribute set consumed by pipeline callers."""
    result = FetchResult(source=_minimal_source(), articles=[], method="rss")
    assert _REQUIRED_ATTRS.issubset(vars(result).keys()), (
        f"FetchResult is missing expected attributes: {_REQUIRED_ATTRS - vars(result).keys()}"
    )


@pytest.mark.unit
@pytest.mark.contract
def test_fetch_result_defaults_are_stable():
    """Default values for optional fields must not change silently."""
    result = FetchResult(source=_minimal_source(), articles=[], method="rss")
    assert result.success is True
    assert result.error is None
    assert result.response_time == 0.0
    assert result.rss_parsing_stats == {}
    assert isinstance(result.timestamp, datetime)
