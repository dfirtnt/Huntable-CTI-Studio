"""Factory for creating Article test data."""

from datetime import datetime
from typing import Optional, Dict, Any
from src.models.article import ArticleCreate


class ArticleFactory:
    """Factory for creating Article test objects."""
    
    @staticmethod
    def create(
        title: Optional[str] = None,
        canonical_url: Optional[str] = None,
        content: Optional[str] = None,
        source_id: int = 1,
        **kwargs
    ) -> ArticleCreate:
        """Create an ArticleCreate object with defaults.
        
        Args:
            title: Article title (default: "Test Article")
            canonical_url: Article URL (default: "https://example.com/test")
            content: Article content (default: "Test content")
            source_id: Source ID (default: 1)
            **kwargs: Additional fields to override
            
        Returns:
            ArticleCreate object
        """
        defaults = {
            "title": title or "Test Article",
            "canonical_url": canonical_url or "https://example.com/test",
            "content": content or "Test content for testing purposes.",
            "source_id": source_id,
            "published_at": datetime.now(),
            "authors": kwargs.get("authors", []),
            "tags": kwargs.get("tags", []),
            "summary": kwargs.get("summary"),
            "article_metadata": kwargs.get("article_metadata", {}),
        }
        defaults.update(kwargs)
        return ArticleCreate(**defaults)
