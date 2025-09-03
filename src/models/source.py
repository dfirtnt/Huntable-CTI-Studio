"""Source data model for threat intelligence sources."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, validator


class SourceConfig(BaseModel):
    """Configuration model for source scraping settings."""
    
    # Scope configuration
    allow: List[str] = Field(default_factory=list, description="Allowed domains")
    post_url_regex: List[str] = Field(default_factory=list, description="Post URL patterns")
    
    # Discovery strategies
    discovery: Dict[str, Any] = Field(default_factory=dict, description="URL discovery configuration")
    
    # Extraction configuration
    extract: Dict[str, Any] = Field(default_factory=dict, description="Content extraction configuration")
    
    # Legacy fallback
    content_selector: Optional[str] = Field(None, description="Legacy content selector")


class DiscoveryStrategy(BaseModel):
    """Discovery strategy configuration."""
    
    listing: Optional[Dict[str, Any]] = None
    sitemap: Optional[Dict[str, Any]] = None


class ListingConfig(BaseModel):
    """Configuration for listing-based discovery."""
    
    urls: List[str] = Field(..., description="URLs to scan for post links")
    post_link_selector: str = Field(..., description="CSS selector for post links")
    next_selector: Optional[str] = Field(None, description="CSS selector for next page")
    max_pages: int = Field(default=3, description="Maximum pages to scan")


class SitemapConfig(BaseModel):
    """Configuration for sitemap-based discovery."""
    
    urls: List[str] = Field(..., description="Sitemap URLs")


class ExtractionConfig(BaseModel):
    """Configuration for content extraction."""
    
    prefer_jsonld: bool = Field(default=True, description="Prefer JSON-LD extraction")
    title_selectors: List[str] = Field(default_factory=list, description="Title CSS selectors")
    date_selectors: List[str] = Field(default_factory=list, description="Date CSS selectors")
    body_selectors: List[str] = Field(default_factory=list, description="Body CSS selectors")
    author_selectors: List[str] = Field(default_factory=list, description="Author CSS selectors")


class Source(BaseModel):
    """Source model representing a threat intelligence source."""
    
    id: Optional[int] = None
    identifier: str = Field(..., description="Unique identifier from YAML config")
    name: str = Field(..., min_length=1, description="Human readable name")
    url: str = Field(..., description="Base URL of the source")
    rss_url: Optional[str] = Field(None, description="RSS/Atom feed URL")
    check_frequency: int = Field(default=3600, ge=60, description="Check frequency in seconds")
    active: bool = Field(default=True, description="Whether source is active")
    config: SourceConfig = Field(default_factory=SourceConfig, description="Source configuration")
    
    # Tracking fields
    last_check: Optional[datetime] = Field(None, description="Last check timestamp")
    last_success: Optional[datetime] = Field(None, description="Last successful check")
    consecutive_failures: int = Field(default=0, description="Consecutive failure count")
    total_articles: int = Field(default=0, description="Total articles collected")
    
    # Health metrics
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Success rate (0-1)")
    average_response_time: float = Field(default=0.0, ge=0.0, description="Average response time in seconds")
    
    @validator('identifier')
    def validate_identifier(cls, v):
        """Validate identifier format."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Identifier must contain only alphanumeric characters, hyphens, and underscores')
        return v.lower()
    
    @validator('url', 'rss_url')
    def validate_urls(cls, v):
        """Validate URL format."""
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v.strip() if v else v
    
    def should_check(self) -> bool:
        """Check if source should be checked based on frequency."""
        if not self.active:
            return False
        
        if not self.last_check:
            return True
        
        time_since_check = (datetime.utcnow() - self.last_check).total_seconds()
        return time_since_check >= self.check_frequency
    
    def update_health_metrics(self, success: bool, response_time: float = 0.0):
        """Update health metrics after a check."""
        if success:
            self.consecutive_failures = 0
            self.last_success = datetime.utcnow()
        else:
            self.consecutive_failures += 1
        
        self.last_check = datetime.utcnow()
        
        # Update response time (simple moving average)
        if self.average_response_time == 0.0:
            self.average_response_time = response_time
        else:
            self.average_response_time = (self.average_response_time + response_time) / 2
    
    def should_disable(self, max_failures: int = 10) -> bool:
        """Check if source should be auto-disabled due to failures."""
        return self.consecutive_failures >= max_failures
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
        schema_extra = {
            "example": {
                "identifier": "crowdstrike_blog",
                "name": "CrowdStrike Intelligence Blog",
                "url": "https://www.crowdstrike.com/blog/",
                "rss_url": "https://www.crowdstrike.com/blog/feed/",
                "check_frequency": 1800,
                "active": True,
                "config": {
                    "allow": ["crowdstrike.com"],
                    "post_url_regex": ["^https://www\\.crowdstrike\\.com/blog/.*"],
                    "discovery": {
                        "strategies": [
                            {
                                "listing": {
                                    "urls": ["https://www.crowdstrike.com/blog/"],
                                    "post_link_selector": "a[href*='/blog/']",
                                    "max_pages": 3
                                }
                            }
                        ]
                    },
                    "extract": {
                        "prefer_jsonld": True,
                        "title_selectors": ["h1", "meta[property='og:title']::attr(content)"],
                        "date_selectors": ["meta[property='article:published_time']::attr(content)"],
                        "body_selectors": ["article", "main"]
                    }
                }
            }
        }


class SourceCreate(BaseModel):
    """Model for creating new sources."""
    
    identifier: str
    name: str
    url: str
    rss_url: Optional[str] = None
    check_frequency: int = 3600
    active: bool = True
    config: SourceConfig = Field(default_factory=SourceConfig)
    
    def to_source(self) -> Source:
        """Convert to full Source model."""
        return Source(**self.dict())


class SourceUpdate(BaseModel):
    """Model for updating existing sources."""
    
    name: Optional[str] = None
    url: Optional[str] = None
    rss_url: Optional[str] = None
    check_frequency: Optional[int] = None
    active: Optional[bool] = None
    config: Optional[SourceConfig] = None


class SourceFilter(BaseModel):
    """Model for filtering sources in queries."""
    
    active: Optional[bool] = None
    identifier_contains: Optional[str] = None
    name_contains: Optional[str] = None
    consecutive_failures_gte: Optional[int] = None
    last_check_before: Optional[datetime] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)


class SourceHealth(BaseModel):
    """Model for source health status."""
    
    source_id: int
    identifier: str
    name: str
    active: bool
    last_check: Optional[datetime]
    last_success: Optional[datetime]
    consecutive_failures: int
    success_rate: float
    average_response_time: float
    total_articles: int
    health_status: str  # 'healthy', 'warning', 'critical', 'disabled'
    
    @validator('health_status', always=True)
    def determine_health_status(cls, v, values):
        """Determine health status based on metrics."""
        if not values.get('active'):
            return 'disabled'
        
        failures = values.get('consecutive_failures', 0)
        success_rate = values.get('success_rate', 0.0)
        
        if failures >= 10:
            return 'critical'
        elif failures >= 5 or success_rate < 0.5:
            return 'warning'
        else:
            return 'healthy'
