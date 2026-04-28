"""Tests for embedding service functionality.

Uses mocked SentenceTransformer; no real model loading.
"""

from unittest.mock import Mock, patch

import numpy as np
import pytest

from src.services.embedding_service import EmbeddingService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestEmbeddingService:
    """Test EmbeddingService functionality (mocked model)."""

    @pytest.fixture
    def mock_sentence_transformer(self):
        """Create mock SentenceTransformer."""
        model = Mock()
        # encode returns 1D array for single text, 2D for batch
        model.encode = Mock(return_value=np.array([0.1] * 768))
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

    def test_zero_vectors_are_independent_when_all_empty(self, service):
        """Regression: [[0.0]*768]*n aliases all slots to the same list.
        Mutating one zero-vector must not corrupt the others."""
        embeddings = service.generate_embeddings_batch(["", "   ", ""])

        assert len(embeddings) == 3
        # Mutate slot 0 in-place
        embeddings[0][0] = 999.0
        # Slots 1 and 2 must be unaffected
        assert embeddings[1][0] == 0.0, "aliased zero-vector: mutating slot 0 corrupted slot 1"
        assert embeddings[2][0] == 0.0, "aliased zero-vector: mutating slot 0 corrupted slot 2"

    def test_zero_vectors_are_independent_in_mixed_batch(self, service, mock_sentence_transformer):
        """Regression: zero slots in a mixed batch must be independent lists."""
        mock_sentence_transformer.encode.return_value = np.array([[0.5] * 768])

        embeddings = service.generate_embeddings_batch(["valid", "", ""])

        # Mutate the first zero slot
        embeddings[1][0] = 42.0
        # Second zero slot must be unaffected
        assert embeddings[2][0] == 0.0, "aliased zero-vector: mutating slot 1 corrupted slot 2"

    def test_embedding_count_mismatch_raises(self, service, mock_sentence_transformer):
        """Regression: model returning fewer embeddings than valid texts must raise, not silently drop.
        zip(strict=True) surfaces this as RuntimeError."""
        # 2 valid texts but model returns only 1 embedding
        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 768])

        with pytest.raises(RuntimeError, match="Batch embedding generation failed"):
            service.generate_embeddings_batch(["text one", "text two"])

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

    def test_load_model_uses_cache_first(self):
        """When cached load succeeds, only one SentenceTransformer call (local_files_only=True)."""
        with patch("src.services.embedding_service.SentenceTransformer") as mock_st:
            mock_model = Mock()
            mock_model.encode = Mock(return_value=np.array([0.1] * 768))
            mock_st.return_value = mock_model

            svc = EmbeddingService(model_name="some-model")
            svc._load_model()

            assert mock_st.call_count == 1
            call_kw = mock_st.call_args[1]
            assert call_kw.get("local_files_only") is True

    def test_load_model_falls_back_to_download_when_cache_misses(self):
        """When cached load fails, second call is without local_files_only (download allowed)."""
        with patch("src.services.embedding_service.SentenceTransformer") as mock_st:
            mock_model = Mock()
            mock_model.encode = Mock(return_value=np.array([0.1] * 768))
            mock_st.side_effect = [OSError("not in cache"), mock_model]

            svc = EmbeddingService(model_name="some-model")
            svc._load_model()

            assert mock_st.call_count == 2
            assert mock_st.call_args_list[0][1].get("local_files_only") is True
            # Second call has no local_files_only (default False)
            assert mock_st.call_args_list[1][1].get("local_files_only", False) is False

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
        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 768] * 100)

        service.generate_embeddings_batch(texts, batch_size=10)

        assert mock_sentence_transformer.encode.called

    def test_generate_embeddings_batch_progress_bar_disabled_by_default(self, service, mock_sentence_transformer):
        """Batch embedding should not show a progress bar unless explicitly enabled."""
        texts = ["text"] * 150
        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 768] * 150)

        service.generate_embeddings_batch(texts)

        assert mock_sentence_transformer.encode.call_args.kwargs["show_progress_bar"] is False

    def test_generate_embeddings_batch_progress_bar_enabled_from_env(
        self, service, mock_sentence_transformer, monkeypatch: pytest.MonkeyPatch
    ):
        """Batch embedding should honor EMBEDDING_SHOW_PROGRESS_BAR=true."""
        texts = ["text"] * 2
        mock_sentence_transformer.encode.return_value = np.array([[0.1] * 768] * 2)
        monkeypatch.setenv("EMBEDDING_SHOW_PROGRESS_BAR", "true")

        service.generate_embeddings_batch(texts)

        assert mock_sentence_transformer.encode.call_args.kwargs["show_progress_bar"] is True
