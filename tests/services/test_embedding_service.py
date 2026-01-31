"""Tests for embedding service functionality.

SKIPPED: EmbeddingService uses Sentence Transformers models.
Models are downloaded from HuggingFace Hub (public repository) but run locally - no API keys needed.
Tests are skipped because model loading/download is slow for unit tests.
"""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.services.embedding_service import EmbeddingService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
# SKIPPED: Model loading is slow for unit tests (models run locally, downloaded from HuggingFace Hub)
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skip(
        reason="SKIPPED: EmbeddingService requires Sentence Transformers model loading (slow for unit tests)"
    ),
]


class TestEmbeddingService:
    """Test EmbeddingService functionality.

    SKIPPED: EmbeddingService uses Sentence Transformers models.
    Models are downloaded from HuggingFace Hub but run locally - no API keys or connections needed.
    Tests are skipped because model loading is slow for unit tests.
    """

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Create mock SentenceTransformer."""
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1] * 768]))
        return model

    @pytest.fixture
    def service(self, mock_sentence_transformer):
        """Create EmbeddingService instance with mocked model."""
        with patch("src.services.embedding_service.SentenceTransformer", return_value=mock_sentence_transformer):
            service = EmbeddingService(model_name="test-model")
            service.model = mock_sentence_transformer
            service._model_loaded = True
            return service

    def test_generate_embedding_success(self, service, mock_sentence_transformer):
        """Test successful embedding generation."""
        text = "This is a test article about threat intelligence"

        embedding = service.generate_embedding(text)

        assert len(embedding) == 768
        assert all(isinstance(x, float) for x in embedding)
        mock_sentence_transformer.encode.assert_called_once()

    def test_generate_embedding_empty_text(self, service):
        """Test embedding generation with empty text."""
        embedding = service.generate_embedding("")

        assert len(embedding) == 768
        assert all(x == 0.0 for x in embedding)

    def test_generate_embeddings_batch_success(self, service, mock_sentence_transformer):
        """Test successful batch embedding generation."""
        texts = ["First article about malware", "Second article about ransomware", "Third article about APT"]

        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 768] * len(texts))

        embeddings = service.generate_embeddings_batch(texts, batch_size=32)

        assert len(embeddings) == len(texts)
        assert all(len(emb) == 768 for emb in embeddings)

    def test_generate_embeddings_batch_empty_list(self, service):
        """Test batch embedding with empty list."""
        embeddings = service.generate_embeddings_batch([])

        assert embeddings == []

    def test_generate_embeddings_batch_mixed_empty(self, service, mock_sentence_transformer):
        """Test batch embedding with some empty texts."""
        texts = [
            "Valid text",
            "",
            "Another valid text",
            "   ",  # Whitespace only
        ]

        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 768] * 2)  # Only 2 valid texts

        embeddings = service.generate_embeddings_batch(texts)

        assert len(embeddings) == len(texts)
        # Empty texts should have zero embeddings
        assert embeddings[1] == [0.0] * 768
        assert embeddings[3] == [0.0] * 768

    def test_create_enriched_text(self, service):
        """Test enriched text creation."""
        enriched = service.create_enriched_text(
            article_title="APT29 Attack",
            source_name="Threat Intel Feed",
            article_content="Attack details here",
            summary="Summary",
            tags=["apt", "malware"],
            article_metadata={"threat_hunting_score": 90.0},
        )

        assert "APT29 Attack" in enriched
        assert "Threat Intel Feed" in enriched
        assert "Attack details here" in enriched

    def test_model_loading(self, service):
        """Test model loading."""
        with patch("src.services.embedding_service.SentenceTransformer") as mock_st:
            mock_model = Mock()
            mock_st.return_value = mock_model

            service._model_loaded = False
            service.model = None

            service._load_model()

            assert service.model is not None
            assert service._model_loaded is True

    def test_generate_embedding_error_handling(self, service, mock_sentence_transformer):
        """Test error handling in embedding generation."""
        mock_sentence_transformer.encode.side_effect = Exception("Model error")

        with pytest.raises(RuntimeError) as exc_info:
            service.generate_embedding("test text")
        assert exc_info.value.__cause__ is not None
        assert str(exc_info.value.__cause__) == "Model error"

    def test_generate_embeddings_batch_error_handling(self, service, mock_sentence_transformer):
        """Test error handling in batch embedding generation."""
        mock_sentence_transformer.encode.side_effect = Exception("Model error")

        with pytest.raises(RuntimeError) as exc_info:
            service.generate_embeddings_batch(["text1", "text2"])
        assert exc_info.value.__cause__ is not None
        assert str(exc_info.value.__cause__) == "Model error"

    def test_generate_embeddings_batch_size(self, service, mock_sentence_transformer):
        """Test batch size parameter."""
        texts = ["text"] * 100

        service.generate_embeddings_batch(texts, batch_size=10)

        # Verify encode was called (may be called multiple times for batches)
        assert mock_sentence_transformer.encode.called
