"""
Base classes for literal observable extractors.

Extractors are deterministic components that return verbatim observables.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ObservableExtractor(ABC):
    """
    Base class for literal observable extractors.

    Extractors should not perform inference or enrichment—they simply emit
    observables that appear verbatim in the source article.
    """

    observable_type: str

    @abstractmethod
    def extract(self, text: str, *, article_id: int) -> list[dict]:
        """Return verbatim observables found in text."""

    @abstractmethod
    def supports(self) -> list[str]:
        """Annotation types consumed by this extractor (e.g., ['CMD'])."""
