"""Pydantic models for Article entities."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal


class ArticleCreate(BaseModel):
    """Model for creating a new article."""
    title: str
    canonical_url: str
    content: str
    source_id: int
    published_at: datetime
    modified_at: Optional[datetime] = None
    authors: List[str] = []
    tags: List[str] = []
    summary: Optional[str] = None
    article_metadata: Dict[str, Any] = {}
    content_hash: Optional[str] = None  # Usually calculated, but can be provided


class ArticleUpdate(BaseModel):
    """Model for updating an article."""
    title: Optional[str] = None
    canonical_url: Optional[str] = None
    content: Optional[str] = None
    published_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    authors: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    article_metadata: Optional[Dict[str, Any]] = None
    processing_status: Optional[str] = None
    archived: Optional[bool] = None


class ArticleListFilter(BaseModel):
    """Filter parameters for listing articles."""
    source_id: Optional[int] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    processing_status: Optional[str] = None
    content_contains: Optional[str] = None
    sort_by: Optional[str] = "published_at"
    sort_order: Optional[str] = "desc"  # "asc" or "desc"


class Article(BaseModel):
    """Complete article model."""
    id: int
    source_id: int
    url: str  # Alias for canonical_url
    canonical_url: str
    title: str
    published_at: datetime
    modified_at: Optional[datetime] = None
    authors: List[str]
    tags: List[str]
    summary: Optional[str] = None
    content: str
    content_hash: str
    article_metadata: Dict[str, Any]
    simhash: Optional[Decimal] = None
    simhash_bucket: Optional[int] = None
    discovered_at: datetime
    word_count: int
    content_length: Optional[int] = None
    collected_at: datetime
    created_at: datetime
    updated_at: datetime
    processing_status: str
    embedding: Optional[Any] = None  # Vector type
    embedding_model: Optional[str] = None
    embedded_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

# Alias for backward compatibility
ArticleFilter = ArticleListFilter
