"""Pydantic models for Source entities."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

# Synthetic/internal feeds that are not real ingestion sources. Excluded from
# every source count so the dashboard and Sources page report the same numbers.
INTERNAL_SOURCE_IDENTIFIERS: tuple[str, ...] = ("manual", "eval_articles")


class SourceConfig(BaseModel):
    """Configuration for a source."""

    check_frequency: int | None = 3600
    lookback_days: int | None = 180
    min_content_length: int | None = None
    robots_user_agent: str | None = None
    # Allow additional config fields
    model_config = {"extra": "allow"}


class SourceCreate(BaseModel):
    """Model for creating a new source."""

    identifier: str
    name: str
    url: str
    rss_url: str | None = None
    active: bool = True
    config: SourceConfig | None = None


class SourceUpdate(BaseModel):
    """Model for updating a source."""

    identifier: str | None = None
    name: str | None = None
    url: str | None = None
    rss_url: str | None = None
    active: bool | None = None
    config: SourceConfig | None = None
    check_frequency: int | None = None
    lookback_days: int | None = None


class SourceFilter(BaseModel):
    """Filter parameters for listing sources."""

    active: bool | None = None
    identifier: str | None = None


class Source(BaseModel):
    """Complete source model."""

    id: int
    identifier: str
    name: str
    url: str
    rss_url: str | None = None
    check_frequency: int
    lookback_days: int
    active: bool
    config: dict[str, Any]
    last_check: datetime | None = None
    last_success: datetime | None = None
    consecutive_failures: int
    total_articles: int
    average_response_time: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceHealth(BaseModel):
    """Source health status model."""

    source_id: int
    identifier: str
    name: str
    active: bool
    tier: int | None = None
    last_check: datetime | None = None
    last_success: datetime | None = None
    consecutive_failures: int
    average_response_time: float
    total_articles: int

    model_config = {"from_attributes": True}


class SourceCounts(BaseModel):
    """Canonical source tallies shared by every UI surface."""

    active: int = 0
    inactive: int = 0
    failing: int = 0
    total: int = 0


def _attr(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def is_internal_source(source: Any) -> bool:
    """True for synthetic feeds (``manual``, ``eval_articles``) by identifier."""
    return (_attr(source, "identifier", "") or "") in INTERNAL_SOURCE_IDENTIFIERS


def summarize_sources(sources: Iterable[Any] | None) -> SourceCounts:
    """Canonical active/inactive/failing/total tally.

    De-duplicates by id and excludes internal feeds so the dashboard widget
    and the Sources page stat chips can never disagree.
    """
    counts = SourceCounts()
    seen: set[Any] = set()
    for source in sources or []:
        sid = _attr(source, "id")
        if sid is not None:
            if sid in seen:
                continue
            seen.add(sid)
        if is_internal_source(source):
            continue
        counts.total += 1
        if _attr(source, "active", True):
            counts.active += 1
        else:
            counts.inactive += 1
        failures = _attr(source, "consecutive_failures", 0) or 0
        if failures > 0:
            counts.failing += 1
    return counts
