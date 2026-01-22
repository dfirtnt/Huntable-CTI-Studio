"""Pydantic models for ArticleAnnotation entities."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


# Annotation type constants
ANNOTATION_MODE_TYPES = {
    "huntability": ["huntable", "not_huntable"],
    "observables": ["cmd", "reg", "file", "network", "process", "eventcode", "sigma"],
}

ALL_ANNOTATION_TYPES = [
    "huntable",
    "not_huntable",
    "cmd",
    "reg",
    "file",
    "network",
    "process",
    "eventcode",
    "sigma",
]

ANNOTATION_USAGE_VALUES = ["train", "eval", "gold"]


class ArticleAnnotationCreate(BaseModel):
    """Model for creating a new annotation."""
    article_id: int
    annotation_type: str
    selected_text: str
    start_position: int
    end_position: int
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    confidence_score: float = 1.0
    usage: str = "train"
    user_id: Optional[int] = None


class ArticleAnnotationUpdate(BaseModel):
    """Model for updating an annotation."""
    annotation_type: Optional[str] = None
    selected_text: Optional[str] = None
    start_position: Optional[int] = None
    end_position: Optional[int] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    confidence_score: Optional[float] = None
    # Note: usage cannot be changed after creation


class ArticleAnnotationFilter(BaseModel):
    """Filter parameters for listing annotations."""
    article_id: Optional[int] = None
    annotation_type: Optional[str] = None
    usage: Optional[str] = None


class ArticleAnnotation(BaseModel):
    """Complete annotation model."""
    id: int
    article_id: int
    user_id: Optional[int] = None
    annotation_type: str
    selected_text: str
    start_position: int
    end_position: int
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    confidence_score: float
    embedding: Optional[Any] = None  # Vector type
    embedding_model: Optional[str] = None
    embedded_at: Optional[datetime] = None
    used_for_training: bool
    usage: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnnotationStats(BaseModel):
    """Statistics about annotations."""
    total: int
    by_type: Dict[str, int]
    by_usage: Dict[str, int]
