"""Article models for the CTI Scraper application."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Article(BaseModel):
    """Article model for API responses."""
    
    id: int
    source_id: int
    url: str
    canonical_url: str
    title: str
    published_at: datetime
    modified_at: Optional[datetime] = None
    authors: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    content: str
    content_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    word_count: int
    content_length: Optional[int] = None
    collected_at: datetime
    created_at: datetime
    updated_at: datetime
    processing_status: str


class ArticleCreate(BaseModel):
    """Article model for creation."""
    
    source_id: int
    url: str
    canonical_url: str
    title: str
    published_at: datetime
    modified_at: Optional[datetime] = None
    authors: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    content: str
    content_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    word_count: int
    content_length: Optional[int] = None
    collected_at: datetime
    processing_status: str = "pending"


class ArticleUpdate(BaseModel):
    """Article model for updates."""
    
    title: Optional[str] = None
    modified_at: Optional[datetime] = None
    authors: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    content_hash: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    word_count: Optional[int] = None
    content_length: Optional[int] = None
    processing_status: Optional[str] = None


class ArticleFilter(BaseModel):
    """Article filter model."""
    
    source_id: Optional[int] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    processing_status: Optional[str] = None
    classification: Optional[str] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
