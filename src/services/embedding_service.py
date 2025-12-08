"""
Embedding Service for CTI Scraper

Provides centralized embedding generation using Sentence Transformers.
Supports batch processing and model caching for efficiency.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer
import torch

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using Sentence Transformers."""
    
    def __init__(self, model_name: str = "all-mpnet-base-v2", cache_dir: Optional[str] = None):
        """
        Initialize the embedding service.
        
        Args:
            model_name: Name of the Sentence Transformers model to use
            cache_dir: Directory to cache the model (defaults to ~/.cache/torch/sentence_transformers)
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.model: Optional[SentenceTransformer] = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model_loaded = False
        
        logger.info(f"Initialized EmbeddingService with model '{model_name}' on device '{self.device}'")
    
    def _load_model(self) -> None:
        """Load the Sentence Transformers model if not already loaded."""
        if self._model_loaded and self.model is not None:
            return
        
        try:
            logger.info(f"Loading Sentence Transformers model: {self.model_name}")
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=self.cache_dir,
                device=self.device
            )
            self._model_loaded = True
            logger.info(f"Successfully loaded model '{self.model_name}' on {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load embedding model '{self.model_name}': {e}")
            raise RuntimeError(f"Could not load embedding model: {e}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of 768 float values representing the embedding
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding generation")
            return [0.0] * 768
        
        self._load_model()
        
        try:
            # Generate embedding
            embedding = self.model.encode(text, convert_to_tensor=False)
            
            # Ensure it's a list of floats
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            
            logger.debug(f"Generated embedding for text of length {len(text)}")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
    
    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process in each batch
            
        Returns:
            List of embeddings (one per input text)
        """
        if not texts:
            return []
        
        self._load_model()
        
        try:
            # Filter out empty texts and keep track of indices
            valid_texts = []
            valid_indices = []
            
            for i, text in enumerate(texts):
                if text and text.strip():
                    valid_texts.append(text)
                    valid_indices.append(i)
            
            if not valid_texts:
                logger.warning("No valid texts provided for batch embedding")
                return [[0.0] * 768] * len(texts)
            
            # Generate embeddings in batches
            embeddings = self.model.encode(
                valid_texts,
                batch_size=batch_size,
                convert_to_tensor=False,
                show_progress_bar=len(valid_texts) > 100
            )
            
            # Convert to list format
            if isinstance(embeddings, np.ndarray):
                embeddings = embeddings.tolist()
            
            # Create full result list with zeros for empty texts
            result = [[0.0] * 768] * len(texts)
            for i, embedding in zip(valid_indices, embeddings):
                result[i] = embedding
            
            logger.info(f"Generated {len(valid_texts)} embeddings in batch processing")
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")
    
    def create_enriched_text(self, article_title: str, source_name: str, 
                           article_content: str, summary: str = None, tags: list = None,
                           article_metadata: dict = None) -> str:
        """
        Create enriched text for embedding by combining metadata with article content.
        
        Args:
            article_title: Title of the article
            source_name: Name of the source
            article_content: The full article content
            summary: Article summary (optional)
            tags: List of article tags (optional)
            article_metadata: Article metadata dict (optional)
            
        Returns:
            Enriched text ready for embedding
        """
        # Clean and truncate inputs to prevent overly long embeddings
        title = (article_title or "Unknown Title")[:200]
        source = (source_name or "Unknown Source")[:100]
        content = (article_content or "")[:3000]  # Limit content size
        summary_text = (summary or "")[:500] if summary else ""
        tags_text = ", ".join(tags[:10]) if tags else ""  # Limit to 10 tags
        
        text_parts = [
            f"Title: {title}",
            f"Source: {source}"
        ]
        
        if summary_text:
            text_parts.append(f"Summary: {summary_text}")
        
        if tags_text:
            text_parts.append(f"Tags: {tags_text}")
        
        # Add hunt scoring information
        if article_metadata:
            hunt_score = article_metadata.get('threat_hunting_score', 0)
            if hunt_score > 0:
                text_parts.append(f"Threat Hunting Score: {hunt_score:.1f}/100")
                
                # Add keyword matches
                perfect_matches = article_metadata.get('perfect_keyword_matches', [])
                good_matches = article_metadata.get('good_keyword_matches', [])
                lolbas_matches = article_metadata.get('lolbas_matches', [])
                
                if perfect_matches:
                    text_parts.append(f"Perfect Threat Keywords: {', '.join(perfect_matches[:10])}")
                if good_matches:
                    text_parts.append(f"Good Threat Keywords: {', '.join(good_matches[:10])}")
                if lolbas_matches:
                    text_parts.append(f"LOLBAS Executables: {', '.join(lolbas_matches[:10])}")
        
        text_parts.append(f"Content: {content}")
        
        return "\n".join(text_parts)
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.
        
        Returns:
            Dictionary with model information
        """
        if not self._model_loaded:
            return {
                "model_name": self.model_name,
                "loaded": False,
                "device": self.device
            }
        
        return {
            "model_name": self.model_name,
            "loaded": True,
            "device": self.device,
            "max_seq_length": getattr(self.model, 'max_seq_length', 512),
            "embedding_dimension": 768  # all-mpnet-base-v2 has 768 dimensions
        }
    
    def validate_embedding(self, embedding: List[float]) -> bool:
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
            return False
        
        if not all(isinstance(x, (int, float)) for x in embedding):
            return False
        
        return True


# Global instance for reuse across the application
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """
    Get the global embedding service instance.
    
    Returns:
        EmbeddingService instance
    """
    global _embedding_service
    
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    
    return _embedding_service


def generate_article_embedding(article_title: str, source_name: str, 
                             article_content: str, summary: str = None, tags: list = None) -> List[float]:
    """
    Convenience function to generate embedding for an article.
    
    Args:
        article_title: Title of the article
        source_name: Name of the source
        article_content: The full article content
        summary: Article summary (optional)
        tags: List of article tags (optional)
        
    Returns:
        Embedding vector
    """
    service = get_embedding_service()
    enriched_text = service.create_enriched_text(article_title, source_name, article_content, summary, tags)
    return service.generate_embedding(enriched_text)


def generate_query_embedding(query_text: str) -> List[float]:
    """
    Generate embedding for a search query.
    
    Args:
        query_text: Query text to embed
        
    Returns:
        Embedding vector
    """
    service = get_embedding_service()
    return service.generate_embedding(query_text)
