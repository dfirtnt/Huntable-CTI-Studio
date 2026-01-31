"""
Deterministic extractor for literal command line observables.

This extractor relies entirely on manually curated CMD annotations
and emits the spans verbatim for downstream agents such as SIGMA generation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Union

from src.extractors.base import ObservableExtractor

if TYPE_CHECKING:
    from src.models.annotation import ArticleAnnotation

AnnotationLike = Union[dict[str, object], "ArticleAnnotation"]


class CMDObservableExtractor(ObservableExtractor):
    """Simple extractor that surfaces annotated command lines."""

    observable_type = "commandline"

    def __init__(self, annotations: Iterable[AnnotationLike] | None = None):
        """
        Initialize the extractor with optional annotations.

        Parameters
        ----------
        annotations:
            Iterable of annotation dictionaries or ArticleAnnotation models.
        """
        self._annotations: list[AnnotationLike] = list(annotations or [])

    def supports(self) -> list[str]:
        return ["CMD"]

    def extract(self, text: str, *, article_id: int) -> list[dict]:
        """
        Emit literal command lines that have been annotated for the article.

        Parameters
        ----------
        text:
            Article content (unused; provided for interface compatibility).
        article_id:
            The article identifier, included in the emitted metadata.
        """
        if not self._annotations:
            return []

        observables: list[dict] = []
        for annotation in self._annotations:
            annotation_type = _get_attr(annotation, "annotation_type")
            if annotation_type != "CMD":
                continue

            selected_text = _get_attr(annotation, "selected_text") or ""
            if not selected_text:
                continue

            start_pos = int(_get_attr(annotation, "start_position") or 0)
            end_pos = int(_get_attr(annotation, "end_position") or start_pos + len(selected_text))

            observables.append(
                {
                    "observable_type": self.observable_type,
                    "value": selected_text,
                    "confidence": 1.0,
                    "source": {
                        "article_id": article_id,
                        "char_start": start_pos,
                        "char_end": end_pos,
                    },
                }
            )

        return observables

    def with_annotations(self, annotations: Iterable[AnnotationLike]) -> CMDObservableExtractor:
        """Return a new extractor instance preloaded with annotations."""
        return CMDObservableExtractor(annotations)


def _get_attr(annotation: AnnotationLike, field: str) -> object | None:
    """Safely access attributes on dicts or objects."""
    if isinstance(annotation, dict):
        return annotation.get(field)
    return getattr(annotation, field, None)
