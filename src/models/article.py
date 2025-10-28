"""Article models for CTI Scraper."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class ArticleCreate(BaseModel):
    """Model for creating a new article."""
    title: str = Field(..., description="Article title")
    content: str = Field(..., description="Article content")
    canonical_url: str = Field(..., description="Canonical URL")
    source_id: int = Field(..., description="Source ID")
    published_at: datetime = Field(..., description="Publication date")
    authors: List[str] = Field(default_factory=list, description="List of authors")
    tags: List[str] = Field(default_factory=list, description="List of tags")
    summary: Optional[str] = Field(None, description="Article summary")
    content_hash: str = Field(..., description="Content hash for deduplication")
    article_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ArticleUpdate(BaseModel):
    """Model for updating an article."""
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    authors: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    article_metadata: Optional[Dict[str, Any]] = None


class ArticleFilter(BaseModel):
    """Model for filtering articles."""
    source_id: Optional[int] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    title_contains: Optional[str] = None
    content_contains: Optional[str] = None
    tags: Optional[List[str]] = None
    authors: Optional[List[str]] = None
    processing_status: Optional[str] = None


class Article(BaseModel):
    """Article model."""
    id: int
    source_id: int
    canonical_url: str
    title: str
    published_at: datetime
    modified_at: Optional[datetime] = None
    authors: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    content: str
    content_hash: str
    article_metadata: Dict[str, Any] = Field(default_factory=dict)
    simhash: Optional[int] = None
    simhash_bucket: Optional[int] = None
    collected_at: datetime
    processing_status: str = "pending"
    word_count: int = 0
    content_length: Optional[int] = None
    discovered_at: datetime
    created_at: datetime
    updated_at: datetime
    archived: bool = False
    embedding: Optional[Any] = None
    embedding_model: Optional[str] = None
    embedded_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class ArticleListFilter(BaseModel):
    """Model for filtering and sorting articles in list view."""
    source_id: Optional[int] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    title_contains: Optional[str] = None
    content_contains: Optional[str] = None
    tags: Optional[List[str]] = None
    authors: Optional[List[str]] = None
    processing_status: Optional[str] = None
    sort_by: str = "threat_hunting_score"
    sort_order: str = "desc"
    limit: Optional[int] = None
    offset: Optional[int] = None
