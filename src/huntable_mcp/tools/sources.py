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

        Returns article and SigmaHQ rule counts, embedding coverage for RAG search,
        and source counts. MCP tools ``search_sigma_rules`` / unified SIGMA search need
        ``sigma_rules`` rows with ``logsource_embedding`` or ``embedding`` populated.
        """
        lines = ["## Database Statistics", ""]

        try:
            stats = await db.get_article_embedding_stats()
            total = int(stats.get("total_articles", 0) or 0)
            embedded = int(stats.get("embedded_count", 0) or 0)
            coverage = float(stats.get("embedding_coverage_percent", 0) or 0)
            lines.append(f"**Articles:** {total} total, {embedded} with embeddings ({coverage:.1f}% coverage)")
        except Exception as e:
            logger.exception("get_stats: article stats failed")
            lines.append(f"**Articles:** (unavailable: {e})")

        try:
            sigma_stats = await db.get_sigma_rule_embedding_stats()
            s_total = int(sigma_stats.get("total_sigma_rules", 0) or 0)
            s_emb = int(sigma_stats.get("sigma_rules_with_rag_embedding", 0) or 0)
            s_cov = float(sigma_stats.get("sigma_embedding_coverage_percent", 0.0) or 0.0)
            s_pend = int(sigma_stats.get("sigma_rules_pending_rag_embedding", 0) or 0)
            lines.append(
                f"**Sigma rules:** {s_total} total in DB, {s_emb} with RAG embeddings "
                f"({s_cov:.1f}% coverage; {s_pend} pending)"
            )
            if s_total == 0:
                lines.append("")
                lines.append(
                    "**SIGMA RAG:** No rows in `sigma_rules`. "
                    "Run `./run_cli.sh sigma index` (or `index-metadata` then `index-embeddings`)."
                )
            elif s_emb == 0:
                lines.append("")
                lines.append(
                    "**SIGMA RAG:** Rules exist but none have RAG vectors. "
                    "Run `./run_cli.sh sigma index-embeddings`. "
                    "Check `./run_cli.sh capabilities check`."
                )
        except Exception as e:
            logger.exception("get_stats: sigma stats failed")
            lines.append(f"**Sigma rules:** (unavailable: {e})")

        try:
            all_sources = await db.list_sources()
            active_sources = [s for s in all_sources if s.active]
            lines.append(f"**Sources:** {len(active_sources)} active / {len(all_sources)} total")
        except Exception as e:
            logger.exception("get_stats: list_sources failed")
            lines.append(f"**Sources:** (unavailable: {e})")

        out = "\n".join(lines)
        if not out.strip():
            return "get_stats: internal error (empty body); check MCP server stderr logs."
        return out
