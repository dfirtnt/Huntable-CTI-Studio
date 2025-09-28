"""
Source models for Pydantic schemas.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class SourceBase(BaseModel):
    """Base source model."""
    name: str
    url: str
    source_type: str = Field(..., description="Type of source: 'rss', 'web', 'api'")
    tier: int = Field(1, description="Source tier: 1 (high priority), 2 (medium), 3 (low)")
    check_frequency: int = Field(3600, description="Check frequency in seconds")
    is_active: bool = Field(True, description="Whether the source is active")
    description: Optional[str] = Field(None, description="Description of the source")


class SourceCreate(BaseModel):
    """Model for creating a new source."""
    identifier: str = Field(..., description="Unique identifier for the source")
    name: str
    url: str
    rss_url: Optional[str] = None
    check_frequency: int = Field(3600, description="Check frequency in seconds")
    lookback_days: int = Field(180, description="How many days back to look for articles")
    active: bool = Field(True, description="Whether the source is active")
    tier: int = Field(2, description="Source priority tier")
    weight: float = Field(1.0, description="Source weighting for scoring")
    config: Optional['SourceConfig'] = Field(None, description="Source configuration")


class SourceUpdate(BaseModel):
    """Model for updating a source."""
    name: Optional[str] = None
    url: Optional[str] = None
    rss_url: Optional[str] = None
    check_frequency: Optional[int] = None
    lookback_days: Optional[int] = None
    active: Optional[bool] = None
    tier: Optional[int] = None
    weight: Optional[float] = None
    config: Optional[Dict[str, Any]] = None


class Source(BaseModel):
    """Full source model with database fields."""
    id: int
    identifier: str
    name: str
    url: str
    rss_url: Optional[str] = None
    check_frequency: int = Field(3600, description="Check frequency in seconds")
    lookback_days: int = Field(180, description="How many days back to look for articles")
    active: bool = Field(True, description="Whether the source is active")
    tier: int = Field(2, description="Source priority tier")
    weight: float = Field(1.0, description="Source weighting for scoring")
    config: Dict[str, Any] = Field(default_factory=dict, description="Source configuration")

    # Tracking fields
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    consecutive_failures: int = Field(0, description="Number of consecutive failures")
    total_articles: int = Field(0, description="Total articles collected from this source")

    # Health metrics
    success_rate: float = Field(0.0, description="Success rate")
    average_response_time: float = Field(0.0, description="Average response time")

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SourceFilter(BaseModel):
    """Model for filtering sources."""
    active: Optional[bool] = None
    identifier_contains: Optional[str] = None
    name_contains: Optional[str] = None
    consecutive_failures_gte: Optional[int] = None
    consecutive_failures_lte: Optional[int] = None
    last_checked_after: Optional[datetime] = None
    last_checked_before: Optional[datetime] = None


class SourceConfig(BaseModel):
    """Source configuration model for parsing and extraction settings."""
    # Scraping configuration
    allow: Optional[List[str]] = Field(None, description="Allowed domains")
    post_url_regex: Optional[List[str]] = Field(None, description="URL patterns for posts")
    robots: Optional[Dict[str, Any]] = Field(None, description="Robots.txt settings")
    min_content_length: Optional[int] = Field(None, description="Minimum content length")
    title_filter_keywords: Optional[List[str]] = Field(None, description="Keywords to filter out from titles")
    content_filter_keywords: Optional[List[str]] = Field(None, description="Keywords required in content")
    require_threat_intel_keywords: Optional[bool] = Field(None, description="Require threat intelligence keywords")
    rss_only: Optional[bool] = Field(None, description="Only use RSS, no web scraping")
    archive_pages: Optional[bool] = Field(None, description="Enable archive page scraping")
    archive_url_pattern: Optional[str] = Field(None, description="URL pattern for archive pages")
    max_archive_pages: Optional[int] = Field(None, description="Maximum archive pages to scrape")

    # Extraction configuration
    extract: Optional[Dict[str, Any]] = Field(None, description="Content extraction settings")
    content_selector: Optional[str] = Field(None, description="CSS selector for content")


class SourceHealth(BaseModel):
    """Source health status model."""
    source_id: int
    is_healthy: bool
    last_check: Optional[datetime] = None
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    response_time: Optional[float] = None
    articles_found: Optional[int] = None
