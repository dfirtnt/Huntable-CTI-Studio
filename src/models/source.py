"""Pydantic models for Source entities."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Configuration for a source."""
    check_frequency: Optional[int] = 3600
    lookback_days: Optional[int] = 180
    min_content_length: Optional[int] = None
    robots_user_agent: Optional[str] = None
    # Allow additional config fields
    model_config = {"extra": "allow"}


class SourceCreate(BaseModel):
    """Model for creating a new source."""
    identifier: str
    name: str
    url: str
    rss_url: Optional[str] = None
    active: bool = True
    config: Optional[SourceConfig] = None


class SourceUpdate(BaseModel):
    """Model for updating a source."""
    identifier: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    rss_url: Optional[str] = None
    active: Optional[bool] = None
    config: Optional[SourceConfig] = None
    check_frequency: Optional[int] = None
    lookback_days: Optional[int] = None


class SourceFilter(BaseModel):
    """Filter parameters for listing sources."""
    active: Optional[bool] = None
    identifier: Optional[str] = None


class Source(BaseModel):
    """Complete source model."""
    id: int
    identifier: str
    name: str
    url: str
    rss_url: Optional[str] = None
    check_frequency: int
    lookback_days: int
    active: bool
    config: Dict[str, Any]
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
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
    tier: Optional[int] = None
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    consecutive_failures: int
    average_response_time: float
    total_articles: int

    model_config = {"from_attributes": True}
