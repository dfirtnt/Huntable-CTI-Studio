"""MCP tools for searching and retrieving CTI articles."""

import logging

from mcp.server.fastmcp import FastMCP

from src.database.async_manager import AsyncDatabaseManager
from src.services.rag_service import RAGService

logger = logging.getLogger(__name__)


def _article_db_id(record: dict) -> int | None:
    """Resolve `articles.id` from a search row.

    Chunk-level RAG rows use ``article_id`` (and may set ``id`` to a chunk id).
    Article-level and lexical rows use ``id`` as the article primary key.
    """
    aid = record.get("article_id")
    if aid is not None:
        return int(aid)
    rid = record.get("id")
    if rid is not None:
        return int(rid)
    return None


def register(mcp: FastMCP, rag: RAGService, db: AsyncDatabaseManager) -> None:
    """Register article tools on the MCP server."""

    @mcp.tool()
    async def search_articles(
        query: str,
        top_k: int = 10,
        threshold: float = 0.5,
        min_hunt_score: float | None = None,
        source_name: str | None = None,
    ) -> str:
        """Search CTI articles using semantic similarity.

        Find threat intelligence articles matching a natural language query.
        Uses vector embeddings to find semantically similar content, not just keyword matches.

        Args:
            query: Natural language search query (e.g. "suspicious parent-child process relationships")
            top_k: Maximum number of results to return (default 10)
            threshold: Minimum similarity score 0.0-1.0 (default 0.5)
            min_hunt_score: Minimum threat hunting relevance score 0-100 (optional)
            source_name: Filter results to a specific source name (optional)
        """
        try:
            # Resolve source_name to source_id if provided
            source_id = None
            if source_name:
                sources = await db.list_sources()
                for s in sources:
                    if source_name.lower() in s.name.lower():
                        source_id = s.id
                        break

            results = await rag.find_similar_content(
                query=query,
                top_k=top_k,
                threshold=threshold,
                min_hunt_score=min_hunt_score,
                source_id=source_id,
                use_chunks=True,
                context_length=2000,
            )

            if not results:
                return "No articles found matching your query."

            lines = [
                f"Found {len(results)} articles:\n"
                "(Rank numbers are for display only; use **Article ID** with get_article.)\n"
            ]
            for i, r in enumerate(results, 1):
                hunt = r.get("hunt_score", "N/A")
                db_id = _article_db_id(r)
                id_line = f"   **Article ID:** {db_id}\n" if db_id is not None else ""
                lines.append(
                    f"{i}. **{r.get('title', 'Untitled')}**\n"
                    f"{id_line}"
                    f"   Source: {r.get('source_name', 'Unknown')} | "
                    f"Similarity: {r.get('similarity', 0):.2f} | "
                    f"Hunt Score: {hunt}\n"
                    f"   URL: {r.get('url', r.get('canonical_url', 'N/A'))}\n"
                    f"   Published: {r.get('published_at', 'N/A')}\n"
                    f"   Preview: {r.get('content', '')[:300]}...\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"search_articles failed: {e}")
            return f"Error searching articles: {e}"

    @mcp.tool()
    async def get_article(article_id: int) -> str:
        """Get full details for a specific article by ID.

        Returns the complete article content, metadata, and source information.

        Args:
            article_id: Database primary key ``articles.id`` (see **Article ID** in
                search_articles / search_articles_by_keywords / search_unified).
                This is not the 1-based rank in search result lists.
        """
        try:
            article = await db.get_article_by_id(article_id)
            if not article:
                return f"Article {article_id} not found."

            published = article.get("published_at")
            if published and hasattr(published, "isoformat"):
                published = published.isoformat()

            return (
                f"# {article['title']}\n\n"
                f"**Source:** {article.get('source_name', 'Unknown')}\n"
                f"**Published:** {published}\n"
                f"**URL:** {article.get('canonical_url', 'N/A')}\n\n"
                f"## Summary\n{article.get('summary') or 'No summary available.'}\n\n"
                f"## Content\n{article.get('content', 'No content.')}\n"
            )
        except Exception as e:
            logger.error(f"get_article failed: {e}")
            return f"Error retrieving article {article_id}: {e}"

    @mcp.tool()
    async def search_articles_by_keywords(
        keywords: list[str],
        limit: int = 20,
    ) -> str:
        """Search articles by exact keyword matching in title and content.

        Use this when you need exact term matches rather than semantic similarity.
        Good for searching specific malware names, CVE IDs, tool names, etc.

        Args:
            keywords: List of keywords to search for (OR logic)
            limit: Maximum number of results (default 20)
        """
        try:
            results = await db.search_articles_by_lexical_terms(
                terms=keywords,
                limit=limit,
            )

            if not results:
                return f"No articles found matching keywords: {', '.join(keywords)}"

            lines = [
                f"Found {len(results)} articles matching keywords {keywords}:\n"
                "(Rank numbers are for display only; use **Article ID** with get_article.)\n"
            ]
            for i, r in enumerate(results, 1):
                db_id = _article_db_id(r)
                id_line = f"   **Article ID:** {db_id}\n" if db_id is not None else ""
                lines.append(
                    f"{i}. **{r.get('title', 'Untitled')}**\n"
                    f"{id_line}"
                    f"   Source: {r.get('source_name', 'Unknown')} | "
                    f"Published: {r.get('published_at', 'N/A')}\n"
                    f"   URL: {r.get('canonical_url', 'N/A')}\n"
                    f"   Preview: {r.get('content', '')[:300]}...\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"search_articles_by_keywords failed: {e}")
            return f"Error searching by keywords: {e}"
