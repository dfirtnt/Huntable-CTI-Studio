"""
RAG Service for CTI Scraper

Provides high-level utilities for semantic search, context retrieval,
and other RAG operations using vector embeddings on articles.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text

from src.database.async_manager import AsyncDatabaseManager
from src.services.embedding_service import EmbeddingService, generate_query_embedding, get_embedding_service

logger = logging.getLogger(__name__)


class RAGService:
    """High-level RAG service for semantic search and context retrieval."""

    def __init__(self):
        """Initialize the RAG service."""
        self.embedding_service = get_embedding_service()  # For articles (all-mpnet-base-v2)
        self.sigma_embedding_service = EmbeddingService(model_name="intfloat/e5-base-v2")  # For SIGMA rules
        self.db_manager = AsyncDatabaseManager()
        logger.info("Initialized RAG service with separate embedding models for articles and SIGMA rules")

    async def embed_query(self, query_text: str) -> list[float]:
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

    async def find_similar_chunks(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.7,
        source_id: int | None = None,
        context_length: int = 2000,
    ) -> list[dict[str, Any]]:
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
                annotation_type=None,  # Get all annotation types
            )

            # Enhance chunks with article metadata
            enhanced_chunks = []
            for chunk in similar_chunks:
                # Get full article context
                article = await self.db_manager.get_article_by_id(chunk["article_id"])
                if article:
                    chunk["article_title"] = article.get("title", "Unknown")
                    chunk["article_url"] = article.get("canonical_url", "")
                    chunk["source_name"] = article.get("source_name", "Unknown")
                    chunk["published_at"] = article.get("published_at")

                    # Truncate context if needed
                    if len(chunk["selected_text"]) > context_length:
                        chunk["selected_text"] = chunk["selected_text"][:context_length] + "..."

                    enhanced_chunks.append(chunk)

            logger.info(f"Found {len(enhanced_chunks)} similar chunks for query: '{query[:50]}...'")
            return enhanced_chunks

        except Exception as e:
            logger.error(f"Failed to find similar chunks: {e}")
            return []

    async def find_similar_content(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.7,
        source_id: int | None = None,
        use_chunks: bool = True,
        context_length: int = 2000,
        min_hunt_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find similar content using both article-level and chunk-level search.

        Args:
            query: Search query text
            top_k: Number of results to return
            threshold: Minimum similarity threshold (0.0-1.0)
            source_id: Filter by source ID
            use_chunks: Whether to use chunk-level search
            context_length: Maximum context length per result
            min_hunt_score: Minimum threat hunting score filter (0-100)

        Returns:
            List of similar content with metadata
        """
        try:
            if use_chunks:
                # Use chunk-level search for better precision
                chunks = await self.find_similar_chunks(
                    query=query, top_k=top_k, threshold=threshold, source_id=source_id, context_length=context_length
                )

                # Deduplicate by article_id and merge results
                seen_articles = set()
                deduplicated_results = []

                for chunk in chunks:
                    article_id = chunk["article_id"]
                    if article_id not in seen_articles:
                        # Get full article to check hunt score
                        article = await self.db_manager.get_article_by_id(article_id)
                        if article:
                            hunt_score = article.get("article_metadata", {}).get("threat_hunting_score", 0)

                            # Apply hunt score filter if specified
                            if min_hunt_score is not None and hunt_score < min_hunt_score:
                                continue

                            seen_articles.add(article_id)
                            deduplicated_results.append(
                                {
                                    "id": chunk["id"],
                                    "article_id": article_id,
                                    "title": chunk["article_title"],
                                    "url": chunk["article_url"],
                                    "source_name": chunk["source_name"],
                                    "published_at": chunk["published_at"],
                                    "content": chunk["selected_text"],
                                    "similarity": chunk["similarity"],
                                    "annotation_type": chunk["annotation_type"],
                                    "confidence_score": chunk["confidence_score"],
                                    "hunt_score": hunt_score,
                                }
                            )

                if not deduplicated_results:
                    logger.info("No chunk hits; falling back to article-level search (threshold=0)")
                    articles_fb = await self.find_similar_articles(
                        query=query, top_k=max(top_k * 4, 24), threshold=0.0, source_id=source_id
                    )
                    for a in articles_fb:
                        if len(deduplicated_results) >= top_k:
                            break
                        aid = a["id"]
                        hs = (a.get("metadata") or {}).get("threat_hunting_score", 0)
                        if min_hunt_score is not None and hs < min_hunt_score:
                            continue
                        body = a.get("content") or a.get("summary") or ""
                        deduplicated_results.append(
                            {
                                "id": aid,
                                "article_id": aid,
                                "title": a.get("title", "Unknown"),
                                "url": a.get("canonical_url", ""),
                                "source_name": a.get("source_name", "Unknown"),
                                "published_at": a.get("published_at"),
                                "content": body[:context_length] + ("..." if len(body) > context_length else ""),
                                "similarity": a.get("similarity", 0),
                                "annotation_type": "article_embedding",
                                "confidence_score": a.get("similarity", 0),
                                "hunt_score": hs,
                            }
                        )

                logger.info(f"Found {len(deduplicated_results)} unique articles from chunk search (incl. fallback)")
                return deduplicated_results[:top_k]
            # Fallback to article-level search
            articles = await self.find_similar_articles(
                query=query,
                top_k=top_k * 2,  # Get more to filter
                threshold=threshold,
                source_id=source_id,
            )

            # Apply hunt score filter if specified
            if min_hunt_score is not None:
                filtered_articles = []
                for article in articles:
                    hunt_score = article.get("article_metadata", {}).get("threat_hunting_score", 0)
                    if hunt_score >= min_hunt_score:
                        article["hunt_score"] = hunt_score
                        filtered_articles.append(article)
                return filtered_articles[:top_k]

            return articles[:top_k]

        except Exception as e:
            logger.error(f"Failed to find similar content: {e}")
            return []

    async def find_similar_articles(
        self, query: str, top_k: int = 10, threshold: float = 0.7, source_id: int | None = None
    ) -> list[dict[str, Any]]:
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
                query_embedding=query_embedding, limit=top_k, threshold=threshold, source_id=source_id
            )

            logger.info(f"Found {len(similar_articles)} similar articles for query: '{query[:50]}...'")
            return similar_articles

        except Exception as e:
            logger.error(f"Failed to find similar articles: {e}")
            return []

    async def get_context_for_sigma(self, techniques: list[str], top_k: int = 5) -> dict[str, list[dict[str, Any]]]:
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
                    source_id=None,
                )

                context_results[technique] = articles
                logger.debug(f"Found {len(articles)} articles for technique: {technique}")

            return context_results

        except Exception as e:
            logger.error(f"Failed to get context for SIGMA: {e}")
            return {}

    async def dedupe_similar_articles(self, threshold: float = 0.85) -> dict[str, Any]:
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
                "status": "not_implemented",
                "message": "Similar article deduplication requires pairwise comparison of all embeddings",
                "recommendation": "Use content_hash-based deduplication for exact duplicates instead",
            }

        except Exception as e:
            logger.error(f"Failed to dedupe similar articles: {e}")
            return {"status": "error", "message": str(e)}

    async def find_similar_sigma_rules(
        self, query: str, top_k: int = 10, threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        """
        Embedding-based similarity search over Sigma rules (logsource_embedding / embedding).

        Args:
            query: Search query text
            top_k: Max rows to return (best matches first even if below threshold)
            threshold: Cutoff for ``meets_threshold`` on each row

        Returns:
            Rule dicts with ``similarity``, ``meets_threshold``, etc.
        """
        try:
            logger.warning("Sigma text query: embedding similarity only (not novelty engine)")

            query_embedding = self.sigma_embedding_service.generate_embedding(query)
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

            async with self.db_manager.get_session() as session:
                stmt = text("""
                    SELECT
                        sr.id,
                        sr.rule_id,
                        sr.title,
                        sr.description,
                        sr.tags,
                        sr.level,
                        sr.status,
                        sr.file_path,
                        CASE
                            WHEN sr.logsource_embedding IS NOT NULL
                                THEN 1 - (sr.logsource_embedding <=> :query_vector)
                            WHEN sr.embedding IS NOT NULL
                                THEN 1 - (sr.embedding <=> :query_vector)
                            ELSE 0.0
                        END AS signature_sim
                    FROM sigma_rules sr
                    WHERE sr.logsource_embedding IS NOT NULL OR sr.embedding IS NOT NULL
                    ORDER BY signature_sim DESC
                    LIMIT :limit
                """)

                result = await session.execute(
                    stmt,
                    {"query_vector": embedding_str, "limit": top_k},
                )

                rules = []
                all_results = []
                for row in result.mappings():
                    signature_sim = float(row["signature_sim"] or 0.0)
                    all_results.append((row["title"], signature_sim))
                    meets = signature_sim >= threshold
                    rules.append(
                        {
                            "id": row["id"],
                            "rule_id": row["rule_id"],
                            "title": row["title"],
                            "description": row["description"],
                            "tags": row["tags"] if row["tags"] else [],
                            "level": row["level"],
                            "status": row["status"],
                            "file_path": row["file_path"],
                            "similarity": signature_sim,
                            "meets_threshold": meets,
                            "novelty_label": "NOVEL",
                            "novelty_score": 1.0 - signature_sim,
                        }
                    )

                if all_results:
                    logger.info(f"Top SIGMA rule matches (threshold={threshold}): {all_results[:3]}")
                    n_meet = sum(1 for r in rules if r["meets_threshold"])
                    if n_meet == 0 and rules:
                        logger.info(
                            "Sigma search: no rules >= threshold=%s; returning %s best matches anyway "
                            "(best similarity=%.3f)",
                            threshold,
                            len(rules),
                            rules[0]["similarity"],
                        )
                logger.info(f"Returning {len(rules)} Sigma rule rows for query: '{query[:50]}...'")
                return rules

        except Exception as e:
            logger.exception("Failed to find similar Sigma rules")
            raise RuntimeError(f"Sigma vector search failed: {e}") from e

    async def find_unified_results(
        self,
        query: str,
        top_k_articles: int = 10,
        top_k_rules: int = 5,
        threshold: float = 0.7,
        source_id: int | None = None,
        use_chunks: bool = True,
        context_length: int = 2000,
        min_hunt_score: float | None = None,
    ) -> dict[str, Any]:
        """
        Find both similar articles and Sigma rules in unified search.

        Args:
            query: Search query text
            top_k_articles: Number of article results to return
            top_k_rules: Number of Sigma rule results to return
            threshold: Minimum similarity threshold
            source_id: Filter by source ID
            use_chunks: Whether to use chunk-level search for articles
            context_length: Maximum context length per article result
            min_hunt_score: Minimum threat hunting score filter

        Returns:
            Dictionary with 'articles' and 'rules' keys
        """
        try:
            articles, rules = await asyncio.gather(
                self.find_similar_content(
                    query=query,
                    top_k=top_k_articles,
                    threshold=threshold,
                    source_id=source_id,
                    use_chunks=use_chunks,
                    context_length=context_length,
                    min_hunt_score=min_hunt_score,
                ),
                self.find_similar_sigma_rules(query=query, top_k=top_k_rules, threshold=threshold),
                return_exceptions=True,
            )

            partial_errors: list[str] = []
            if isinstance(articles, BaseException):
                logger.exception("Unified search: article leg failed")
                partial_errors.append(f"articles: {articles}")
                articles = []
            if isinstance(rules, BaseException):
                logger.exception("Unified search: sigma leg failed")
                partial_errors.append(f"sigma_rules: {rules}")
                rules = []

            out: dict[str, Any] = {
                "articles": articles,
                "rules": rules,
                "total_articles": len(articles),
                "total_rules": len(rules),
            }
            if partial_errors:
                out["partial_errors"] = partial_errors
            return out

        except Exception as e:
            logger.error(f"Failed to find unified results: {e}")
            return {"articles": [], "rules": [], "total_articles": 0, "total_rules": 0, "error": str(e)}

    async def semantic_search(self, query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
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
            source_id = filters.get("source_id") if filters else None
            top_k = filters.get("top_k", 10) if filters else 10
            threshold = filters.get("threshold", 0.7) if filters else 0.7

            # Perform search
            results = await self.find_similar_articles(
                query=query, top_k=top_k, threshold=threshold, source_id=source_id
            )

            # Get embedding stats for context
            stats = await self.db_manager.get_article_embedding_stats()

            return {
                "query": query,
                "results": results,
                "total_results": len(results),
                "filters_applied": filters or {},
                "embedding_stats": stats,
                "search_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return {
                "query": query,
                "results": [],
                "total_results": 0,
                "error": str(e),
                "search_timestamp": datetime.now().isoformat(),
            }

    async def get_embedding_coverage(self) -> dict[str, Any]:
        """
        Article embedding stats plus ``sigma_corpus`` (see ``get_sigma_rule_embedding_stats``).
        Excludes ``sigma_rule_queue`` rows.
        """
        try:
            articles = await self.db_manager.get_article_embedding_stats()
            sigma_corpus = await self.db_manager.get_sigma_rule_embedding_stats()
            return {**articles, "sigma_corpus": sigma_corpus}
        except Exception as e:
            logger.error(f"Failed to get embedding coverage: {e}")
            return {
                "total_articles": 0,
                "embedded_count": 0,
                "embedding_coverage_percent": 0.0,
                "pending_embeddings": 0,
                "source_stats": [],
                "sigma_corpus": {
                    "total_sigma_rules": 0,
                    "sigma_rules_with_rag_embedding": 0,
                    "sigma_embedding_coverage_percent": 0.0,
                    "sigma_rules_pending_rag_embedding": 0,
                },
                "error": str(e),
            }

    async def find_related_techniques(self, technique: str, top_k: int = 5) -> list[dict[str, Any]]:
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
                source_id=None,
            )

            # Extract unique techniques (simplified - in practice you'd want more sophisticated extraction)
            related_techniques = []
            seen_techniques = set()

            for article in similar_articles:
                # Simple technique extraction - look for common threat technique patterns
                text = (article["title"] + " " + article["content"]).lower()

                # Common technique keywords (simplified)
                technique_keywords = [
                    "persistence",
                    "privilege escalation",
                    "defense evasion",
                    "credential access",
                    "discovery",
                    "lateral movement",
                    "collection",
                    "command and control",
                    "exfiltration",
                    "impact",
                    "initial access",
                    "execution",
                ]

                for keyword in technique_keywords:
                    if keyword in text and keyword not in seen_techniques:
                        related_techniques.append(
                            {
                                "technique": keyword,
                                "similarity": article["similarity"],
                                "source_article": article["title"],
                                "content_preview": article["content"][:200] + "...",
                                "source_name": article["source_name"],
                            }
                        )
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
_rag_service: RAGService | None = None


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
async def semantic_search_articles(query: str, top_k: int = 10, threshold: float = 0.7) -> list[dict[str, Any]]:
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


async def get_sigma_context(techniques: list[str], top_k: int = 5) -> dict[str, list[dict[str, Any]]]:
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
