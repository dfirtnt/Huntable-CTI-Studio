"""Pydantic models for CTI Scraper."""

from src.models.annotation import (
    ALL_ANNOTATION_TYPES,
    ANNOTATION_MODE_TYPES,
    ANNOTATION_USAGE_VALUES,
    AnnotationStats,
    ArticleAnnotation,
    ArticleAnnotationCreate,
    ArticleAnnotationFilter,
    ArticleAnnotationUpdate,
)
from src.models.article import (
    Article,
    ArticleCreate,
    ArticleListFilter,
    ArticleUpdate,
)
from src.models.source import (
    Source,
    SourceConfig,
    SourceCreate,
    SourceFilter,
    SourceHealth,
    SourceUpdate,
)

__all__ = [
    # Source models
    "Source",
    "SourceCreate",
    "SourceUpdate",
    "SourceFilter",
    "SourceConfig",
    "SourceHealth",
    # Article models
    "Article",
    "ArticleCreate",
    "ArticleUpdate",
    "ArticleListFilter",
    # Annotation models
    "ArticleAnnotation",
    "ArticleAnnotationCreate",
    "ArticleAnnotationUpdate",
    "ArticleAnnotationFilter",
    "AnnotationStats",
    # Constants
    "ANNOTATION_MODE_TYPES",
    "ALL_ANNOTATION_TYPES",
    "ANNOTATION_USAGE_VALUES",
]
