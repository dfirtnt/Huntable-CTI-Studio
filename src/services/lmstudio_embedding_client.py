"""
LM Studio Embedding Client

Provides embedding generation using LM Studio's OpenAI-compatible API.
Used specifically for SIGMA rule embeddings.
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)


class LMStudioEmbeddingClient:
    """Client for generating embeddings via LM Studio API."""

    def __init__(self, model: str | None = None, config_models: dict | None = None):
        """
        Initialize the LM Studio embedding client.

        Args:
            model: Optional model name to use. If not provided, reads from workflow config or environment variable.
            config_models: Optional dict of agent models from workflow config (e.g., {"SigmaEmbeddingModel": "model_name"})

        Reads configuration in order:
        1. model parameter (if provided)
        2. config_models['SigmaEmbeddingModel'] (from workflow config)
        3. Environment variable LMSTUDIO_EMBEDDING_MODEL
        4. Default: "text-embedding-e5-base-v2"

        Also reads:
        - LMSTUDIO_EMBEDDING_URL: API endpoint URL
        """
        from src.utils.lmstudio_url import normalize_lmstudio_embedding_url

        self.url = normalize_lmstudio_embedding_url(
            os.getenv("LMSTUDIO_EMBEDDING_URL", "http://localhost:1234/v1/embeddings")
        )

        # Get model from parameter, config, or environment
        if model:
            self.model = model
        elif config_models and config_models.get("SigmaEmbeddingModel"):
            self.model = config_models["SigmaEmbeddingModel"]
            logger.info(f"Using embedding model from workflow config: {self.model}")
        else:
            # Fall back to environment variable
            self.model = os.getenv("LMSTUDIO_EMBEDDING_MODEL", "text-embedding-e5-base-v2")

        self.timeout = 60  # 60 second timeout for embeddings
        self.max_retries = 3
        self.retry_delay = 1  # seconds

        logger.info(f"Initialized LM Studio embedding client: {self.url} with model '{self.model}'")

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of 768 float values representing the embedding

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding generation")
            return [0.0] * 768

        return self.generate_embeddings_batch([text])[0]

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in a single batch request.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings (one per input text)

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not texts:
            return []

        # Filter out empty texts
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            logger.warning("No valid texts provided for batch embedding")
            return [[0.0] * 768] * len(texts)

        # Prepare request
        payload = {"input": valid_texts, "model": self.model}

        # Retry logic
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Requesting embeddings from LM Studio (attempt {attempt + 1}/{self.max_retries})")

                response = requests.post(self.url, json=payload, timeout=self.timeout)

                response.raise_for_status()

                # Parse response
                data = response.json()
                embeddings = []

                # Handle OpenAI-compatible response format
                if "data" in data:
                    # OpenAI format: {"data": [{"embedding": [...], ...}, ...]}
                    for item in data["data"]:
                        if "embedding" in item:
                            embeddings.append(item["embedding"])
                else:
                    # Alternative format: {"embeddings": [[...], [...]]}
                    if "embeddings" in data:
                        embeddings = data["embeddings"]
                    else:
                        # Fallback: assume first-level list
                        embeddings = data

                if not embeddings:
                    raise ValueError("No embeddings returned from LM Studio API")

                # Create full result list with zeros for empty texts
                result = []
                text_idx = 0
                for orig_text in texts:
                    if orig_text and orig_text.strip():
                        result.append(embeddings[text_idx])
                        text_idx += 1
                    else:
                        result.append([0.0] * 768)

                logger.info(f"Generated {len(valid_texts)} embeddings from LM Studio")
                return result

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"LM Studio timeout (attempt {attempt + 1}/{self.max_retries}): {e}")

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"LM Studio request failed (attempt {attempt + 1}/{self.max_retries}): {e}")

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error generating embeddings (attempt {attempt + 1}/{self.max_retries}): {e}")

            # Wait before retry (unless last attempt)
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay * (attempt + 1))

        # All retries failed
        logger.error(f"Failed to generate embeddings after {self.max_retries} attempts")
        raise RuntimeError(f"Could not generate embeddings from LM Studio: {last_exception}")

    def get_model_info(self) -> dict:
        """
        Get information about the embedding model.

        Returns:
            Dictionary with model information
        """
        return {"url": self.url, "model": self.model, "dimension": 768}

    def validate_embedding(self, embedding: list[float]) -> bool:
        """
        Validate that an embedding is properly formatted.

        Args:
            embedding: Embedding to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(embedding, list):
            return False

        if len(embedding) != 768:
            logger.warning(f"Embedding dimension mismatch: expected 768, got {len(embedding)}")
            return False

        if not all(isinstance(x, (int, float)) for x in embedding):
            return False

        return True
