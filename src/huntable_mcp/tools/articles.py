"""MCP tools for searching and retrieving CTI articles."""

import logging
from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import ArticleAnnotationTable, ArticleTable
from src.huntable_mcp.tools.write_support import (
    confirmation_required_response,
    create_confirmation_request,
    record_mcp_audit,
)
from src.models.annotation import ALL_ANNOTATION_TYPES, ANNOTATION_MODE_TYPES, ANNOTATION_USAGE_VALUES
from src.services.audit_service import (
    ACTION_ANNOTATION_CREATED,
    ACTION_ANNOTATION_DELETED,
    ACTION_ANNOTATION_UPDATED,
    ACTION_ARTICLE_DELETE_REQUESTED,
)
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


def _resolve_annotation_usage(annotation_type: str, usage: str | None) -> str:
    if annotation_type in ANNOTATION_MODE_TYPES["observables"]:
        return (usage or "").lower()
    return usage or "train"


def _validate_annotation_payload(
    *,
    annotation_type: str,
    selected_text: str,
    start_position: int,
    end_position: int,
    usage: str,
) -> str | None:
    if annotation_type not in ALL_ANNOTATION_TYPES:
        return f"Unsupported annotation type '{annotation_type}'"
    if start_position < 0 or end_position < start_position:
        return "Annotation positions must be non-negative and end_position must be >= start_position"
    text_length = len(selected_text or "")
    if annotation_type in ANNOTATION_MODE_TYPES["huntability"] and (text_length < 950 or text_length > 1050):
        return f"Annotation text must be approximately 1000 characters for training purposes (current: {text_length})"
    if annotation_type in ANNOTATION_MODE_TYPES["observables"]:
        if text_length == 0:
            return "Annotation text is required for observable annotations"
        if usage not in ANNOTATION_USAGE_VALUES:
            return f"Unsupported annotation usage '{usage}'"
    return None


async def _update_annotation_count(session: Any, article_id: int) -> int:
    count_result = await session.execute(
        select(func.count(ArticleAnnotationTable.id)).where(ArticleAnnotationTable.article_id == article_id)
    )
    annotation_count = int(count_result.scalar() or 0)
    article_result = await session.execute(select(ArticleTable).where(ArticleTable.id == article_id).limit(1))
    article = article_result.scalar_one_or_none()
    if article is not None:
        metadata = dict(article.article_metadata or {})
        metadata["annotation_count"] = annotation_count
        article.article_metadata = metadata
        article.updated_at = datetime.now()
    return annotation_count


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
    async def delete_article(article_id: int) -> str:
        """Request human confirmation to delete an article.

        Risk tier: confirmation-required. MCP does not delete the article directly.

        Args:
            article_id: Database primary key ``articles.id``.
        """
        try:
            async with db.get_session() as session:
                result = await session.execute(select(ArticleTable).where(ArticleTable.id == article_id).limit(1))
                article = result.scalar_one_or_none()
                if article is None:
                    return f"Article {article_id} not found."
                confirmation = await create_confirmation_request(
                    session,
                    operation="delete_article",
                    target_type="article",
                    target_id=article_id,
                    requested_action=ACTION_ARTICLE_DELETE_REQUESTED,
                    payload={"article_id": article_id, "title": article.title},
                    summary=f"Requested confirmation to delete article {article_id}",
                    confirmation_instructions=(
                        f"Open article {article_id} in the web UI and delete it only after confirming "
                        "the article and dependent records should be removed."
                    ),
                )
                response = confirmation_required_response(confirmation)
                await session.commit()
                return response
        except Exception as e:
            logger.error(f"delete_article failed: {e}")
            return f"Error requesting delete confirmation for article {article_id}: {e}"

    @mcp.tool()
    async def create_annotation(
        article_id: int,
        annotation_type: str,
        selected_text: str,
        start_position: int,
        end_position: int,
        context_before: str | None = None,
        context_after: str | None = None,
        confidence_score: float = 1.0,
        usage: str | None = None,
    ) -> str:
        """Create an article annotation.

        Risk tier: auto-executable. Annotation writes are scoped and auditable.

        Args:
            article_id: Database primary key ``articles.id``.
            annotation_type: One supported annotation type.
            selected_text: Exact selected text span.
            start_position: Start offset in article content.
            end_position: End offset in article content.
            context_before: Optional surrounding context before the span.
            context_after: Optional surrounding context after the span.
            confidence_score: Confidence score for the annotation.
            usage: Required for observable annotations; defaults to train otherwise.
        """
        resolved_usage = _resolve_annotation_usage(annotation_type, usage)
        validation_error = _validate_annotation_payload(
            annotation_type=annotation_type,
            selected_text=selected_text,
            start_position=start_position,
            end_position=end_position,
            usage=resolved_usage,
        )
        if validation_error:
            return f"Annotation rejected: {validation_error}"
        try:
            async with db.get_session() as session:
                article_result = await session.execute(
                    select(ArticleTable).where(ArticleTable.id == article_id).limit(1)
                )
                if article_result.scalar_one_or_none() is None:
                    return f"Article {article_id} not found."

                annotation = ArticleAnnotationTable(
                    article_id=article_id,
                    user_id=None,
                    annotation_type=annotation_type,
                    selected_text=selected_text,
                    start_position=start_position,
                    end_position=end_position,
                    context_before=context_before,
                    context_after=context_after,
                    confidence_score=confidence_score,
                    usage=resolved_usage,
                    used_for_training=False,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                session.add(annotation)
                await session.flush()
                annotation_count = await _update_annotation_count(session, article_id)
                annotation_id = annotation.id
                await record_mcp_audit(
                    session,
                    ACTION_ANNOTATION_CREATED,
                    "annotation",
                    annotation_id,
                    f"Created {annotation_type} annotation {annotation_id} on article {article_id}",
                    {"article_id": article_id, "annotation_type": annotation_type, "usage": resolved_usage},
                )
                await session.commit()

            return f"Created annotation {annotation_id} on article {article_id}. Annotation count: {annotation_count}."
        except Exception as e:
            logger.error(f"create_annotation failed: {e}")
            return f"Error creating annotation for article {article_id}: {e}"

    @mcp.tool()
    async def update_annotation(
        annotation_id: int,
        annotation_type: str | None = None,
        selected_text: str | None = None,
        start_position: int | None = None,
        end_position: int | None = None,
        context_before: str | None = None,
        context_after: str | None = None,
        confidence_score: float | None = None,
    ) -> str:
        """Update an article annotation.

        Risk tier: auto-executable. Annotation writes are scoped and auditable.

        Args:
            annotation_id: Annotation database ID.
            annotation_type: Optional replacement annotation type.
            selected_text: Optional replacement selected text.
            start_position: Optional replacement start offset.
            end_position: Optional replacement end offset.
            context_before: Optional replacement context before the span.
            context_after: Optional replacement context after the span.
            confidence_score: Optional replacement confidence score.
        """
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable).where(ArticleAnnotationTable.id == annotation_id).limit(1)
                )
                annotation = result.scalar_one_or_none()
                if annotation is None:
                    return f"Annotation {annotation_id} not found."

                next_type = annotation_type or annotation.annotation_type
                next_text = selected_text if selected_text is not None else annotation.selected_text
                next_start = start_position if start_position is not None else annotation.start_position
                next_end = end_position if end_position is not None else annotation.end_position
                validation_error = _validate_annotation_payload(
                    annotation_type=next_type,
                    selected_text=next_text,
                    start_position=next_start,
                    end_position=next_end,
                    usage=annotation.usage,
                )
                if validation_error:
                    return f"Annotation update rejected: {validation_error}"

                changed_fields = []
                if annotation_type is not None:
                    annotation.annotation_type = annotation_type
                    changed_fields.append("annotation_type")
                if selected_text is not None:
                    annotation.selected_text = selected_text
                    changed_fields.append("selected_text")
                if start_position is not None:
                    annotation.start_position = start_position
                    changed_fields.append("start_position")
                if end_position is not None:
                    annotation.end_position = end_position
                    changed_fields.append("end_position")
                if context_before is not None:
                    annotation.context_before = context_before
                    changed_fields.append("context_before")
                if context_after is not None:
                    annotation.context_after = context_after
                    changed_fields.append("context_after")
                if confidence_score is not None:
                    annotation.confidence_score = confidence_score
                    changed_fields.append("confidence_score")
                if not changed_fields:
                    return f"No update fields supplied for annotation {annotation_id}."

                annotation.updated_at = datetime.now()
                article_id = annotation.article_id
                await record_mcp_audit(
                    session,
                    ACTION_ANNOTATION_UPDATED,
                    "annotation",
                    annotation_id,
                    f"Updated annotation {annotation_id}",
                    {"article_id": article_id, "changed_fields": changed_fields},
                )
                await session.commit()

            return f"Updated annotation {annotation_id}."
        except Exception as e:
            logger.error(f"update_annotation failed: {e}")
            return f"Error updating annotation {annotation_id}: {e}"

    @mcp.tool()
    async def delete_annotation(annotation_id: int) -> str:
        """Delete an article annotation.

        Risk tier: auto-executable. Annotation deletion is scoped and audited.

        Args:
            annotation_id: Annotation database ID.
        """
        try:
            async with db.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable).where(ArticleAnnotationTable.id == annotation_id).limit(1)
                )
                annotation = result.scalar_one_or_none()
                if annotation is None:
                    return f"Annotation {annotation_id} not found."

                article_id = annotation.article_id
                await session.delete(annotation)
                await session.flush()
                annotation_count = await _update_annotation_count(session, article_id)
                await record_mcp_audit(
                    session,
                    ACTION_ANNOTATION_DELETED,
                    "annotation",
                    annotation_id,
                    f"Deleted annotation {annotation_id}",
                    {"article_id": article_id},
                )
                await session.commit()

            return f"Deleted annotation {annotation_id}. Article {article_id} annotation count: {annotation_count}."
        except Exception as e:
            logger.error(f"delete_annotation failed: {e}")
            return f"Error deleting annotation {annotation_id}: {e}"

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
