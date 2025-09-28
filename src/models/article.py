"""
Article models for Pydantic schemas.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ArticleBase(BaseModel):
    """Base article model."""
    title: str
    content: str
    url: str
    canonical_url: Optional[str] = None
    source_id: int
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    classification: Optional[str] = Field(None, description="Article classification: 'chosen', 'rejected', 'unclassified'")
    threat_hunting_score: Optional[float] = Field(None, description="Threat hunting relevance score")
    content_length: Optional[int] = Field(None, description="Length of content in characters")


class ArticleCreate(ArticleBase):
    """Model for creating a new article."""
    pass


class ArticleUpdate(BaseModel):
    """Model for updating an article."""
    title: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    canonical_url: Optional[str] = None
    classification: Optional[str] = None
    threat_hunting_score: Optional[float] = None
    content_length: Optional[int] = None


class Article(ArticleBase):
    """Full article model with database fields."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ArticleFilter(BaseModel):
    """Model for filtering articles."""
    source_id: Optional[int] = None
    classification: Optional[str] = None
    threat_hunting_score_min: Optional[float] = None
    threat_hunting_score_max: Optional[float] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    collected_after: Optional[datetime] = None
    collected_before: Optional[datetime] = None
    content_length_min: Optional[int] = None
    content_length_max: Optional[int] = None
