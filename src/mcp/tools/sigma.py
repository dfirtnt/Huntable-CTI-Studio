"""MCP tools for searching SIGMA detection rules."""

import logging

from mcp.server.fastmcp import FastMCP

from src.mcp.tools.articles import _article_db_id
from src.services.rag_service import RAGService

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, rag: RAGService) -> None:
    """Register SIGMA rule tools on the MCP server."""

    @mcp.tool()
    async def search_sigma_rules(
        query: str,
        top_k: int = 10,
        threshold: float = 0.5,
    ) -> str:
        """Search the SigmaHQ detection rule corpus by semantic similarity.

        Find SIGMA detection rules matching a natural language description of
        threat behavior, technique, or log source.

        Args:
            query: Natural language description (e.g. "PowerShell download cradle execution")
            top_k: Maximum number of results (default 10)
            threshold: Minimum similarity score 0.0-1.0 (default 0.5)
        """
        try:
            rules = await rag.find_similar_sigma_rules(
                query=query,
                top_k=top_k,
                threshold=threshold,
            )

            if not rules:
                return "No SIGMA rules found matching your query."

            lines = [f"Found {len(rules)} SIGMA rules:\n"]
            for i, r in enumerate(rules, 1):
                tags = ", ".join(r.get("tags", [])[:5]) or "none"
                lines.append(
                    f"{i}. **{r.get('title', 'Untitled')}**\n"
                    f"   Rule ID: {r.get('rule_id', 'N/A')} | "
                    f"Level: {r.get('level', 'N/A')} | "
                    f"Status: {r.get('status', 'N/A')}\n"
                    f"   Similarity: {r.get('similarity', 0):.2f}\n"
                    f"   Tags: {tags}\n"
                    f"   Description: {r.get('description', 'N/A')}\n"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"search_sigma_rules failed: {e}")
            return f"Error searching SIGMA rules: {e}"

    @mcp.tool()
    async def search_unified(
        query: str,
        top_k_articles: int = 10,
        top_k_rules: int = 5,
        threshold: float = 0.5,
    ) -> str:
        """Search both articles AND SIGMA rules in one call.

        The all-in-one search tool: finds both relevant threat intelligence articles
        and matching SIGMA detection rules for any natural language query.

        Args:
            query: Natural language search query
            top_k_articles: Maximum article results (default 10)
            top_k_rules: Maximum SIGMA rule results (default 5)
            threshold: Minimum similarity score 0.0-1.0 (default 0.5)
        """
        try:
            results = await rag.find_unified_results(
                query=query,
                top_k_articles=top_k_articles,
                top_k_rules=top_k_rules,
                threshold=threshold,
            )

            sections = []

            # Articles section
            articles = results.get("articles", [])
            if articles:
                lines = [f"## Articles ({len(articles)} found)\n"]
                lines.append(
                    "(Article rank numbers are display-only; use **Article ID** with get_article.)\n"
                )
                for i, r in enumerate(articles, 1):
                    db_id = _article_db_id(r)
                    id_line = f"   **Article ID:** {db_id}\n" if db_id is not None else ""
                    lines.append(
                        f"{i}. **{r.get('title', 'Untitled')}**\n"
                        f"{id_line}"
                        f"   Source: {r.get('source_name', 'Unknown')} | "
                        f"Similarity: {r.get('similarity', 0):.2f}\n"
                        f"   URL: {r.get('url', r.get('canonical_url', 'N/A'))}\n"
                        f"   Preview: {r.get('content', '')[:200]}...\n"
                    )
                sections.append("\n".join(lines))
            else:
                sections.append("## Articles\nNo matching articles found.\n")

            # SIGMA rules section
            rules = results.get("rules", [])
            if rules:
                lines = [f"## SIGMA Rules ({len(rules)} found)\n"]
                for i, r in enumerate(rules, 1):
                    tags = ", ".join(r.get("tags", [])[:5]) or "none"
                    lines.append(
                        f"{i}. **{r.get('title', 'Untitled')}**\n"
                        f"   Level: {r.get('level', 'N/A')} | "
                        f"Similarity: {r.get('similarity', 0):.2f}\n"
                        f"   Tags: {tags}\n"
                    )
                sections.append("\n".join(lines))
            else:
                sections.append("## SIGMA Rules\nNo matching rules found.\n")

            return "\n".join(sections)
        except Exception as e:
            logger.error(f"search_unified failed: {e}")
            return f"Error in unified search: {e}"
