"""Pydantic models for CTI Scraper."""

from src.models.source import (
    Source,
    SourceCreate,
    SourceUpdate,
    SourceFilter,
    SourceConfig,
    SourceHealth,
)
from src.models.article import (
    Article,
    ArticleCreate,
    ArticleUpdate,
    ArticleListFilter,
)
from src.models.annotation import (
    ArticleAnnotation,
    ArticleAnnotationCreate,
    ArticleAnnotationUpdate,
    ArticleAnnotationFilter,
    AnnotationStats,
    ANNOTATION_MODE_TYPES,
    ALL_ANNOTATION_TYPES,
    ANNOTATION_USAGE_VALUES,
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
