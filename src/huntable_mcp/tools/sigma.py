"""MCP tools for searching SIGMA detection rules."""

import logging
import re

from mcp.server.fastmcp import FastMCP

from src.database.async_manager import AsyncDatabaseManager
from src.huntable_mcp.tools.articles import _article_db_id
from src.services.rag_service import RAGService

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def register(mcp: FastMCP, rag: RAGService, db: AsyncDatabaseManager | None = None) -> None:
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
            threshold: Similarity cutoff for labeling only; best matches are still returned below this
                (semantic scores are often modest—use get_stats to confirm sigma_rules are loaded).
        """
        try:
            rules = await rag.find_similar_sigma_rules(
                query=query,
                top_k=top_k,
                threshold=threshold,
            )

            if not rules:
                return (
                    "No SIGMA rules returned (no indexed rows with embeddings). "
                    "Call **get_stats** — look for **Sigma rules:** total and RAG embedding count. "
                    "If total is 0, run `./run_cli.sh sigma index` (or `index-metadata` then `index-embeddings`)."
                )

            n_meet = sum(1 for r in rules if r.get("meets_threshold", r.get("similarity", 0) >= threshold))
            head = f"Found {len(rules)} SIGMA rules (best semantic matches; {n_meet} at or above threshold {threshold}):\n"
            if n_meet == 0:
                head += (
                    f"(No rule reached {threshold}; scores below are still the closest in the corpus—"
                    "try a narrower technique-focused query or lower threshold for labeling only.)\n"
                )

            lines = [head]
            for i, r in enumerate(rules, 1):
                tags = ", ".join(r.get("tags", [])[:5]) or "none"
                flag = " ✓" if r.get("meets_threshold") else ""
                lines.append(
                    f"{i}. **{r.get('title', 'Untitled')}**{flag}\n"
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
    async def get_sigma_rule(rule_id: str) -> str:
        """Get full YAML and metadata for a single Sigma rule by its SigmaHQ UUID.

        Returns the complete rule definition including raw YAML, detection logic,
        tags, level, status, author, and source file path.

        Args:
            rule_id: SigmaHQ rule UUID (e.g. "5f1abf38-60ab-4f20-b0e2-e373f...").
                     Use the **Rule ID** value from search_sigma_rules results.
        """
        if not _UUID_RE.match(rule_id):
            return '{"error": "Invalid rule_id format"}'

        if db is None:
            return "Error: database not available for get_sigma_rule."

        try:
            rule = await db.get_sigma_rule_by_id(rule_id)
            if rule is None:
                return f'{{"error": "No rule found with ID {rule_id}"}}'

            tags = ", ".join(rule.get("tags", [])) or "none"
            refs = "\n".join(f"  - {r}" for r in rule.get("rule_references", [])) or "  none"
            fps = "\n".join(f"  - {f}" for f in rule.get("false_positives", [])) or "  none"

            date_val = rule.get("date")
            if date_val and hasattr(date_val, "strftime"):
                date_val = date_val.strftime("%Y-%m-%d")

            yaml_block = rule.get("raw_yaml") or "(raw YAML not stored — re-run `sigma index` to populate)"

            return (
                f"# {rule['title']}\n\n"
                f"**Rule ID:** {rule['rule_id']}\n"
                f"**Status:** {rule.get('status') or 'N/A'} | "
                f"**Level:** {rule.get('level') or 'N/A'}\n"
                f"**Author:** {rule.get('author') or 'N/A'}\n"
                f"**Date:** {date_val or 'N/A'}\n"
                f"**Tags:** {tags}\n"
                f"**Source File:** {rule.get('file_path') or 'N/A'}\n\n"
                f"## Description\n{rule.get('description') or 'No description.'}\n\n"
                f"## References\n{refs}\n\n"
                f"## False Positives\n{fps}\n\n"
                f"## Detection Rule (YAML)\n```yaml\n{yaml_block}\n```\n"
            )
        except Exception as e:
            logger.error(f"get_sigma_rule failed: {e}")
            return f"Error retrieving sigma rule {rule_id}: {e}"

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
            if results.get("partial_errors"):
                sections.append("## Search warnings\n" + "\n".join(results["partial_errors"]) + "\n")
            if results.get("error"):
                sections.append(f"## Error\n{results['error']}\n")

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
                sections.append(
                    "## SIGMA Rules\nNo rules returned — `sigma_rules` may be empty or lack embeddings. "
                    "See **get_stats** (Sigma rules line) and `./run_cli.sh sigma index` if needed.\n"
                )

            return "\n".join(sections)
        except Exception as e:
            logger.error(f"search_unified failed: {e}")
            return f"Error in unified search: {e}"
