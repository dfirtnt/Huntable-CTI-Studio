"""MCP tools for browsing CTI sources and database stats."""

import logging

from mcp.server.fastmcp import FastMCP

from src.database.async_manager import AsyncDatabaseManager
from src.models.source import SourceFilter

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    """Register source and stats tools on the MCP server."""

    @mcp.tool()
    async def list_sources(active_only: bool = True) -> str:
        """List all CTI intelligence sources.

        Shows the feed/site registry: source names, URLs, article counts,
        health status, and check frequency.

        Args:
            active_only: If true, only show active sources (default true)
        """
        try:
            filter_params = SourceFilter(active=True) if active_only else None
            sources = await db.list_sources(filter_params=filter_params)

            if not sources:
                return "No sources found."

            lines = [f"{'Active' if active_only else 'All'} sources ({len(sources)}):\n"]
            for s in sources:
                last_check = s.last_check.isoformat() if s.last_check else "never"
                lines.append(
                    f"- **{s.name}** (ID: {s.id})\n"
                    f"  URL: {s.url}\n"
                    f"  RSS: {s.rss_url or 'N/A'}\n"
                    f"  Articles: {s.total_articles} | "
                    f"Active: {s.active} | "
                    f"Last check: {last_check}\n"
                    f"  Failures: {s.consecutive_failures} | "
                    f"Avg response: {s.average_response_time:.1f}s\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"list_sources failed: {e}")
            return f"Error listing sources: {e}"

    @mcp.tool()
    async def get_stats() -> str:
        """Get database statistics and embedding coverage.

        Returns total article counts, embedding coverage percentages,
        and source counts for a quick health overview.
        """
        try:
            stats = await db.get_article_embedding_stats()

            all_sources = await db.list_sources()
            active_sources = [s for s in all_sources if s.active]

            total = stats.get("total_articles", 0)
            embedded = stats.get("embedded_count", 0)
            coverage = stats.get("embedding_coverage_percent", 0)

            return (
                f"## Database Statistics\n\n"
                f"**Articles:** {total} total, {embedded} with embeddings ({coverage:.1f}% coverage)\n"
                f"**Sources:** {len(active_sources)} active / {len(all_sources)} total\n"
            )
        except Exception as e:
            logger.error(f"get_stats failed: {e}")
            return f"Error getting stats: {e}"
