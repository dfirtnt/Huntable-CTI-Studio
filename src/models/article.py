"""Article data model for threat intelligence content."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, validator
import hashlib


class Article(BaseModel):
    """Article model representing collected threat intelligence content."""
    
    id: Optional[int] = None
    source_id: int
    canonical_url: str = Field(..., description="Canonical URL of the article")
    title: str = Field(..., min_length=1, description="Article title")
    published_at: datetime = Field(..., description="Publication date")
    modified_at: Optional[datetime] = Field(None, description="Last modification date")
    authors: List[str] = Field(default_factory=list, description="Article authors")
    tags: List[str] = Field(default_factory=list, description="Article tags/categories")
    summary: Optional[str] = Field(None, description="Article summary/excerpt")
    content: str = Field(..., min_length=1, description="Full article content")
    content_hash: str = Field(..., description="SHA256 hash of content for deduplication")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw structured data")
    quality_score: Optional[float] = Field(None, description="Content quality score (0-100)")
    word_count: Optional[int] = Field(None, description="Word count of the article")
    discovered_at: datetime = Field(default_factory=datetime.utcnow, description="When article was discovered")
    processing_status: str = Field(default="pending", description="Processing status")
    
    @validator('content_hash', always=True)
    def generate_content_hash(cls, v, values):
        """Generate SHA256 hash of content if not provided."""
        if not v and 'content' in values:
            content = values['content']
            title = values.get('title', '')
            # Combine title and content for better deduplication
            combined = f"{title}\n{content}".encode('utf-8')
            return hashlib.sha256(combined).hexdigest()
        return v
    
    @validator('canonical_url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith(('http://', 'https://', 'pdf://')):
            raise ValueError('URL must start with http://, https://, or pdf://')
        return v.strip()
    
    @validator('processing_status')
    def validate_status(cls, v):
        """Validate processing status values."""
        valid_statuses = {'pending', 'processed', 'failed', 'duplicate', 'completed'}
        if v not in valid_statuses:
            raise ValueError(f'Invalid status: {v}. Must be one of {valid_statuses}')
        return v
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "source_id": 1,
                "canonical_url": "https://example.com/blog/threat-analysis",
                "title": "Advanced Persistent Threat Analysis",
                "published_at": "2024-01-15T10:30:00Z",
                "authors": ["Jane Doe", "John Smith"],
                "tags": ["APT", "malware", "analysis"],
                "summary": "Comprehensive analysis of recent APT campaign...",
                "content": "Full article content here...",
                "content_hash": "abc123...",
                "metadata": {
                    "schema_type": "BlogPosting",
                    "word_count": 1500
                }
            }
        }


class ArticleCreate(BaseModel):
    """Model for creating new articles."""
    
    source_id: int
    canonical_url: str
    title: str
    published_at: datetime
    modified_at: Optional[datetime] = None
    authors: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    content: str
    content_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('content_hash', always=True)
    def generate_content_hash(cls, v, values):
        """Generate SHA256 hash of content if not provided."""
        if not v and 'content' in values and 'title' in values:
            content = values['content']
            title = values.get('title', '')
            # Combine title and content for better deduplication
            combined = f"{title}\n{content}".encode('utf-8')
            return hashlib.sha256(combined).hexdigest()
        return v
    
    def to_article(self) -> Article:
        """Convert to full Article model."""
        return Article(**self.dict())


class ArticleUpdate(BaseModel):
    """Model for updating existing articles."""
    
    title: Optional[str] = None
    modified_at: Optional[datetime] = None
    authors: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    processing_status: Optional[str] = None


class ArticleFilter(BaseModel):
    """Model for filtering articles in queries."""
    
    source_id: Optional[int] = None
    author: Optional[str] = None
    tag: Optional[str] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    content_contains: Optional[str] = None
    processing_status: Optional[str] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)
    
    # Sorting options
    sort_by: str = Field(default="discovered_at", description="Field to sort by")
    sort_order: str = Field(default="desc", description="Sort order: 'asc' or 'desc'")
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        """Validate sort_by field."""
        valid_fields = [
            'id', 'title', 'published_at', 'discovered_at', 'modified_at',
            'source_id', 'quality_score', 'threat_hunting_score', 'word_count', 'processing_status', 'annotation_count'
        ]
        if v not in valid_fields:
            raise ValueError(f'sort_by must be one of: {", ".join(valid_fields)}')
        return v
    
    @validator('sort_order')
    def validate_sort_order(cls, v):
        """Validate sort_order field."""
        if v not in ['asc', 'desc']:
            raise ValueError('sort_order must be "asc" or "desc"')
        return v