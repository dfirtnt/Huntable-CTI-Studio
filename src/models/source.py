"""Source models for CTI Scraper."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class SourceConfig(BaseModel):
    """Source configuration model."""
    check_frequency: int = Field(default=3600, description="Check frequency in seconds")
    lookback_days: int = Field(default=180, description="Number of days to look back")
    tier: int = Field(default=2, description="Source tier (1=high, 2=medium, 3=low)")
    weight: float = Field(default=1.0, description="Source weight for scoring")
    config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration")


class SourceCreate(BaseModel):
    """Model for creating a new source."""
    id: Optional[int] = None
    name: str = Field(..., description="Source name")
    url: str = Field(..., description="Source URL")
    rss_url: Optional[str] = Field(None, description="RSS feed URL")
    identifier: Optional[str] = Field(None, description="Unique identifier")
    active: bool = Field(default=True, description="Whether source is active")
    config: SourceConfig = Field(default_factory=SourceConfig, description="Source configuration")


class SourceUpdate(BaseModel):
    """Model for updating a source."""
    name: Optional[str] = None
    url: Optional[str] = None
    rss_url: Optional[str] = None
    active: Optional[bool] = None
    config: Optional[SourceConfig] = None


class SourceFilter(BaseModel):
    """Model for filtering sources."""
    active: Optional[bool] = None
    tier: Optional[int] = None
    name_contains: Optional[str] = None


class SourceHealth(BaseModel):
    """Model for source health information."""
    source_id: int
    last_check: Optional[datetime] = None
    success_rate: float = Field(default=0.0, description="Success rate (0.0 to 1.0)")
    average_response_time: Optional[float] = None
    total_checks: int = Field(default=0, description="Total number of checks")
    successful_checks: int = Field(default=0, description="Number of successful checks")
    last_error: Optional[str] = None


class Source(BaseModel):
    """Source model."""
    id: int
    name: str
    url: str
    rss_url: Optional[str] = None
    identifier: str
    active: bool = True
    check_frequency: int = 3600
    lookback_days: int = 180
    tier: int = 2
    weight: float = 1.0
    last_check: Optional[datetime] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        from_attributes = True
