"""Pydantic models for ArticleAnnotation entities."""

from datetime import datetime
from typing import Any

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
    context_before: str | None = None
    context_after: str | None = None
    confidence_score: float = 1.0
    usage: str = "train"
    user_id: int | None = None


class ArticleAnnotationUpdate(BaseModel):
    """Model for updating an annotation."""

    annotation_type: str | None = None
    selected_text: str | None = None
    start_position: int | None = None
    end_position: int | None = None
    context_before: str | None = None
    context_after: str | None = None
    confidence_score: float | None = None
    # Note: usage cannot be changed after creation


class ArticleAnnotationFilter(BaseModel):
    """Filter parameters for listing annotations."""

    article_id: int | None = None
    annotation_type: str | None = None
    usage: str | None = None


class ArticleAnnotation(BaseModel):
    """Complete annotation model."""

    id: int
    article_id: int
    user_id: int | None = None
    annotation_type: str
    selected_text: str
    start_position: int
    end_position: int
    context_before: str | None = None
    context_after: str | None = None
    confidence_score: float
    embedding: Any | None = None  # Vector type
    embedding_model: str | None = None
    embedded_at: datetime | None = None
    used_for_training: bool
    usage: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnnotationStats(BaseModel):
    """Statistics about annotations."""

    total: int
    by_type: dict[str, int]
    by_usage: dict[str, int]
