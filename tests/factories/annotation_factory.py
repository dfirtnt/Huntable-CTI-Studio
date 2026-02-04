"""Factory for creating Annotation test data."""

from src.models.annotation import ArticleAnnotationCreate


class AnnotationFactory:
    """Factory for creating Annotation test objects."""

    @staticmethod
    def create(
        article_id: int = 1,
        annotation_type: str = "huntable",
        selected_text: str | None = None,
        start_position: int = 0,
        end_position: int = 100,
        **kwargs,
    ) -> ArticleAnnotationCreate:
        """Create an ArticleAnnotationCreate object with defaults.

        Args:
            article_id: Article ID (default: 1)
            annotation_type: Annotation type (default: "huntable")
            selected_text: Selected text (default: 1000 chars for huntability)
            start_position: Start position (default: 0)
            end_position: End position (default: 100)
            **kwargs: Additional fields to override

        Returns:
            ArticleAnnotationCreate object
        """
        if selected_text is None:
            if annotation_type in ["huntable", "not_huntable"]:
                # Huntability annotations need ~1000 chars
                selected_text = "x" * 1000
            else:
                selected_text = "Test annotation text"

        defaults = {
            "article_id": article_id,
            "annotation_type": annotation_type,
            "selected_text": selected_text,
            "start_position": start_position,
            "end_position": end_position,
            "context_before": kwargs.get("context_before"),
            "context_after": kwargs.get("context_after"),
            "confidence_score": kwargs.get("confidence_score", 1.0),
            "usage": kwargs.get("usage", "train"),
        }
        defaults.update(kwargs)
        return ArticleAnnotationCreate(**defaults)
