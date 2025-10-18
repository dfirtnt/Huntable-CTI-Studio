"""
Annotation models for CTI Scraper.

This module defines the data models for article annotations.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class ArticleAnnotationBase(BaseModel):
    """Base annotation model."""
    article_id: int
    annotation_type: str = Field(..., description="Type of annotation: 'huntable' or 'not_huntable'")
    selected_text: str
    start_position: int
    end_position: int
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    used_for_training: bool = Field(default=False)


class ArticleAnnotationCreate(ArticleAnnotationBase):
    """Model for creating a new annotation."""
    pass


class ArticleAnnotationUpdate(BaseModel):
    """Model for updating an annotation."""
    annotation_type: Optional[str] = None
    selected_text: Optional[str] = None
    start_position: Optional[int] = None
    end_position: Optional[int] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    used_for_training: Optional[bool] = None


class ArticleAnnotation(ArticleAnnotationBase):
    """Complete annotation model."""
    id: int
    user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ArticleAnnotationFilter(BaseModel):
    """Filter for querying annotations."""
    article_id: Optional[int] = None
    annotation_type: Optional[str] = None
    used_for_training: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class AnnotationStats(BaseModel):
    """Statistics for annotations."""
    total_annotations: int
    huntable_count: int
    not_huntable_count: int
    used_for_training_count: int
    unused_for_training_count: int
    average_confidence: float
    articles_with_annotations: int
