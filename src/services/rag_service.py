"""
RAG Service for CTI Scraper

Provides high-level utilities for semantic search, context retrieval,
and other RAG operations using vector embeddings on articles.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from src.services.embedding_service import get_embedding_service, generate_query_embedding
from src.database.async_manager import AsyncDatabaseManager

logger = logging.getLogger(__name__)


class RAGService:
    """High-level RAG service for semantic search and context retrieval."""
    
    def __init__(self):
        """Initialize the RAG service."""
        self.embedding_service = get_embedding_service()
        self.db_manager = AsyncDatabaseManager()
        logger.info("Initialized RAG service")
    
    async def embed_query(self, query_text: str) -> List[float]:
        """
        Generate embedding for a search query.
        
        Args:
            query_text: Query text to embed
            
        Returns:
            Embedding vector
        """
        try:
            return generate_query_embedding(query_text)
        except Exception as e:
            logger.error(f"Failed to embed query: {e}")
            raise
    
    async def find_similar_chunks(self, query: str, top_k: int = 10, 
                                 threshold: float = 0.7, source_id: Optional[int] = None,
                                 context_length: int = 2000) -> List[Dict[str, Any]]:
        """
        Find similar chunks using semantic search on annotations.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            threshold: Minimum similarity threshold (0.0-1.0)
            source_id: Filter by source ID
            context_length: Maximum context length per chunk
            
        Returns:
            List of similar chunks with metadata
        """
        try:
            # Generate query embedding
            query_embedding = await self.embed_query(query)
            
            # Search for similar annotations/chunks
            similar_chunks = await self.db_manager.search_similar_annotations(
                query_embedding=query_embedding,
                limit=top_k,
                threshold=threshold,
                annotation_type=None  # Get all annotation types
            )
            
            # Enhance chunks with article metadata
            enhanced_chunks = []
            for chunk in similar_chunks:
                # Get full article context
                article = await self.db_manager.get_article_by_id(chunk['article_id'])
                if article:
                    chunk['article_title'] = article.get('title', 'Unknown')
                    chunk['article_url'] = article.get('canonical_url', '')
                    chunk['source_name'] = article.get('source_name', 'Unknown')
                    chunk['published_at'] = article.get('published_at')
                    
                    # Truncate context if needed
                    if len(chunk['selected_text']) > context_length:
                        chunk['selected_text'] = chunk['selected_text'][:context_length] + "..."
                    
                    enhanced_chunks.append(chunk)
            
            logger.info(f"Found {len(enhanced_chunks)} similar chunks for query: '{query[:50]}...'")
            return enhanced_chunks
            
        except Exception as e:
            logger.error(f"Failed to find similar chunks: {e}")
            return []
    
    async def find_similar_content(self, query: str, top_k: int = 10, 
                                 threshold: float = 0.7, source_id: Optional[int] = None,
                                 use_chunks: bool = True, context_length: int = 2000) -> List[Dict[str, Any]]:
        """
        Find similar content using both article-level and chunk-level search.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            threshold: Minimum similarity threshold (0.0-1.0)
            source_id: Filter by source ID
            use_chunks: Whether to use chunk-level search
            context_length: Maximum context length per result
            
        Returns:
            List of similar content with metadata
        """
        try:
            if use_chunks:
                # Use chunk-level search for better precision
                chunks = await self.find_similar_chunks(
                    query=query,
                    top_k=top_k,
                    threshold=threshold,
                    source_id=source_id,
                    context_length=context_length
                )
                
                # Deduplicate by article_id and merge results
                seen_articles = set()
                deduplicated_results = []
                
                for chunk in chunks:
                    article_id = chunk['article_id']
                    if article_id not in seen_articles:
                        seen_articles.add(article_id)
                        deduplicated_results.append({
                            'id': chunk['id'],
                            'article_id': article_id,
                            'title': chunk['article_title'],
                            'url': chunk['article_url'],
                            'source_name': chunk['source_name'],
                            'published_at': chunk['published_at'],
                            'content': chunk['selected_text'],
                            'similarity': chunk['similarity'],
                            'annotation_type': chunk['annotation_type'],
                            'confidence_score': chunk['confidence_score']
                        })
                
                logger.info(f"Found {len(deduplicated_results)} unique articles from chunk search")
                return deduplicated_results[:top_k]
            else:
                # Fallback to article-level search
                return await self.find_similar_articles(
                    query=query,
                    top_k=top_k,
                    threshold=threshold,
                    source_id=source_id
                )
                
        except Exception as e:
            logger.error(f"Failed to find similar content: {e}")
            return []
    
    async def find_similar_articles(self, query: str, top_k: int = 10, 
                                  threshold: float = 0.7, source_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Find similar articles using semantic search.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            threshold: Minimum similarity threshold (0.0-1.0)
            source_id: Filter by source ID
            
        Returns:
            List of similar articles with metadata
        """
        try:
            # Generate query embedding
            query_embedding = await self.embed_query(query)
            
            # Search for similar articles
            similar_articles = await self.db_manager.search_similar_articles(
                query_embedding=query_embedding,
                limit=top_k,
                threshold=threshold,
                source_id=source_id
            )
            
            logger.info(f"Found {len(similar_articles)} similar articles for query: '{query[:50]}...'")
            return similar_articles
            
        except Exception as e:
            logger.error(f"Failed to find similar articles: {e}")
            return []
    
    async def get_context_for_sigma(self, techniques: List[str], top_k: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get relevant context articles for SIGMA rule generation.
        
        Args:
            techniques: List of threat techniques to search for
            top_k: Number of articles per technique
            
        Returns:
            Dictionary mapping techniques to relevant articles
        """
        try:
            context_results = {}
            
            for technique in techniques:
                # Search for articles related to this technique
                articles = await self.find_similar_articles(
                    query=technique,
                    top_k=top_k,
                    threshold=0.6,  # Lower threshold for broader context
                    source_id=None
                )
                
                context_results[technique] = articles
                logger.debug(f"Found {len(articles)} articles for technique: {technique}")
            
            return context_results
            
        except Exception as e:
            logger.error(f"Failed to get context for SIGMA: {e}")
            return {}
    
    async def dedupe_similar_articles(self, threshold: float = 0.85) -> Dict[str, Any]:
        """
        Find and report similar articles for deduplication.
        
        Args:
            threshold: Similarity threshold for considering articles as duplicates
            
        Returns:
            Dictionary with deduplication results
        """
        try:
            # This is a simplified implementation - in practice, you'd want to
            # compare all articles against each other, which is computationally expensive
            # For now, we'll return a placeholder structure
            
            logger.warning("Deduplication of similar articles not yet implemented - computationally expensive")
            
            return {
                'status': 'not_implemented',
                'message': 'Similar article deduplication requires pairwise comparison of all embeddings',
                'recommendation': 'Use content_hash-based deduplication for exact duplicates instead'
            }
            
        except Exception as e:
            logger.error(f"Failed to dedupe similar articles: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def semantic_search(self, query: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform semantic search with optional filters.
        
        Args:
            query: Search query
            filters: Optional filters (source_id, date_range, etc.)
            
        Returns:
            Search results with metadata
        """
        try:
            # Extract filters
            source_id = filters.get('source_id') if filters else None
            top_k = filters.get('top_k', 10) if filters else 10
            threshold = filters.get('threshold', 0.7) if filters else 0.7
            
            # Perform search
            results = await self.find_similar_articles(
                query=query,
                top_k=top_k,
                threshold=threshold,
                source_id=source_id
            )
            
            # Get embedding stats for context
            stats = await self.db_manager.get_article_embedding_stats()
            
            return {
                'query': query,
                'results': results,
                'total_results': len(results),
                'filters_applied': filters or {},
                'embedding_stats': stats,
                'search_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return {
                'query': query,
                'results': [],
                'total_results': 0,
                'error': str(e),
                'search_timestamp': datetime.now().isoformat()
            }
    
    async def get_embedding_coverage(self) -> Dict[str, Any]:
        """
        Get statistics about embedding coverage.
        
        Returns:
            Dictionary with embedding statistics
        """
        try:
            return await self.db_manager.get_article_embedding_stats()
        except Exception as e:
            logger.error(f"Failed to get embedding coverage: {e}")
            return {
                'total_articles': 0,
                'embedded_count': 0,
                'embedding_coverage_percent': 0.0,
                'error': str(e)
            }
    
    async def find_related_techniques(self, technique: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Find related threat techniques based on semantic similarity.
        
        Args:
            technique: Threat technique to find related ones for
            top_k: Number of related techniques to return
            
        Returns:
            List of related techniques with similarity scores
        """
        try:
            # Search for similar articles
            similar_articles = await self.find_similar_articles(
                query=technique,
                top_k=top_k * 2,  # Get more results to filter
                threshold=0.6,
                source_id=None
            )
            
            # Extract unique techniques (simplified - in practice you'd want more sophisticated extraction)
            related_techniques = []
            seen_techniques = set()
            
            for article in similar_articles:
                # Simple technique extraction - look for common threat technique patterns
                text = (article['title'] + ' ' + article['content']).lower()
                
                # Common technique keywords (simplified)
                technique_keywords = [
                    'persistence', 'privilege escalation', 'defense evasion', 'credential access',
                    'discovery', 'lateral movement', 'collection', 'command and control',
                    'exfiltration', 'impact', 'initial access', 'execution'
                ]
                
                for keyword in technique_keywords:
                    if keyword in text and keyword not in seen_techniques:
                        related_techniques.append({
                            'technique': keyword,
                            'similarity': article['similarity'],
                            'source_article': article['title'],
                            'content_preview': article['content'][:200] + '...',
                            'source_name': article['source_name']
                        })
                        seen_techniques.add(keyword)
                        
                        if len(related_techniques) >= top_k:
                            break
                
                if len(related_techniques) >= top_k:
                    break
            
            logger.info(f"Found {len(related_techniques)} related techniques for: {technique}")
            return related_techniques
            
        except Exception as e:
            logger.error(f"Failed to find related techniques: {e}")
            return []
    
    async def close(self):
        """Close database connections."""
        await self.db_manager.close()


# Global instance for reuse
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """
    Get the global RAG service instance.
    
    Returns:
        RAGService instance
    """
    global _rag_service
    
    if _rag_service is None:
        _rag_service = RAGService()
    
    return _rag_service


# Convenience functions for common operations
async def semantic_search_articles(query: str, top_k: int = 10, threshold: float = 0.7) -> List[Dict[str, Any]]:
    """
    Convenience function for semantic article search.
    
    Args:
        query: Search query
        top_k: Number of results
        threshold: Similarity threshold
        
    Returns:
        List of similar articles
    """
    rag_service = get_rag_service()
    return await rag_service.find_similar_articles(query, top_k, threshold)


async def get_sigma_context(techniques: List[str], top_k: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convenience function for SIGMA context retrieval.
    
    Args:
        techniques: List of threat techniques
        top_k: Number of articles per technique
        
    Returns:
        Dictionary mapping techniques to relevant articles
    """
    rag_service = get_rag_service()
    return await rag_service.get_context_for_sigma(techniques, top_k)