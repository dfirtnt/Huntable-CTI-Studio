"""Pydantic models for Article entities."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class ArticleCreate(BaseModel):
    """Model for creating a new article."""

    title: str
    canonical_url: str
    content: str
    source_id: int
    published_at: datetime
    modified_at: datetime | None = None
    authors: list[str] = []
    tags: list[str] = []
    summary: str | None = None
    article_metadata: dict[str, Any] = {}
    content_hash: str | None = None  # Usually calculated, but can be provided


class ArticleUpdate(BaseModel):
    """Model for updating an article."""

    title: str | None = None
    canonical_url: str | None = None
    content: str | None = None
    published_at: datetime | None = None
    modified_at: datetime | None = None
    authors: list[str] | None = None
    tags: list[str] | None = None
    summary: str | None = None
    article_metadata: dict[str, Any] | None = None
    processing_status: str | None = None
    archived: bool | None = None


class ArticleListFilter(BaseModel):
    """Filter parameters for listing articles."""

    source_id: int | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    processing_status: str | None = None
    content_contains: str | None = None
    sort_by: str | None = "published_at"
    sort_order: str | None = "desc"  # "asc" or "desc"


class Article(BaseModel):
    """Complete article model."""

    id: int
    source_id: int
    url: str  # Alias for canonical_url
    canonical_url: str
    title: str
    published_at: datetime
    modified_at: datetime | None = None
    authors: list[str]
    tags: list[str]
    summary: str | None = None
    content: str
    content_hash: str
    article_metadata: dict[str, Any]
    simhash: Decimal | None = None
    simhash_bucket: int | None = None
    discovered_at: datetime
    word_count: int
    content_length: int | None = None
    collected_at: datetime
    created_at: datetime
    updated_at: datetime
    processing_status: str
    embedding: Any | None = None  # Vector type
    embedding_model: str | None = None
    embedded_at: datetime | None = None

    model_config = {"from_attributes": True}


# Alias for backward compatibility
ArticleFilter = ArticleListFilter
