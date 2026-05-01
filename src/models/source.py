"""Pydantic models for Source entities."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
