"""
Article annotation models for Pydantic schemas.
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ArticleAnnotationBase(BaseModel):
    """Base annotation model."""
    article_id: int
    user_id: Optional[int] = None
    annotation_type: str = Field(..., description="Type of annotation: 'huntable' or 'not_huntable'")
    selected_text: str = Field(..., description="The selected text content")
    start_position: int = Field(..., description="Start position in the article text")
    end_position: int = Field(..., description="End position in the article text")
    context_before: Optional[str] = Field(None, description="Text before the selection")
    context_after: Optional[str] = Field(None, description="Text after the selection")
    confidence_score: float = Field(0.0, description="Confidence score for the annotation")


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
    confidence_score: Optional[float] = None


class ArticleAnnotation(ArticleAnnotationBase):
    """Full annotation model with database fields."""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ArticleAnnotationFilter(BaseModel):
    """Model for filtering annotations."""
    article_id: Optional[int] = None
    user_id: Optional[int] = None
    annotation_type: Optional[str] = None
    confidence_score_min: Optional[float] = None
    confidence_score_max: Optional[float] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class AnnotationStats(BaseModel):
    """Statistics for annotations."""
    total_annotations: int
    huntable_count: int
    not_huntable_count: int
    avg_confidence_score: float
    articles_with_annotations: int
    most_common_annotation_type: str
