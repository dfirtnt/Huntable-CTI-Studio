"""Huntable CTI Studio MCP Server.

Exposes CTI database search, SIGMA rules, sources, and workflow status
as MCP tools for use by any LLM client (Claude Code, Claude Desktop, etc.).
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.database.async_manager import AsyncDatabaseManager
from src.huntable_mcp.tools import articles, sigma, sources, workflow
from src.services.rag_service import RAGService

# Load .env from the project root so POSTGRES_PASSWORD (and other vars) are available
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env", override=False)

# MCP should use the runtime app DB by default, not test DB.
# Prevent accidental test-environment bleed-through from client processes.
if os.environ.get("APP_ENV") == "test":
    logger = logging.getLogger(__name__)
    logger.warning("APP_ENV=test detected for MCP; overriding to APP_ENV=development")
    os.environ["APP_ENV"] = "development"

# Build DATABASE_URL from POSTGRES_PASSWORD if not already set explicitly.
if not os.environ.get("DATABASE_URL"):
    _pw = os.environ.get("POSTGRES_PASSWORD", "")
    if _pw:
        os.environ["DATABASE_URL"] = (
            f"postgresql+asyncpg://cti_user:{_pw}@localhost:5432/cti_scraper"
        )

# Stdio MCP: logs must go to stderr only — stdout is reserved for JSON-RPC.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
    force=True,
)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "huntable-cti-studio",
    instructions=(
        "Huntable CTI Studio — a threat intelligence database with semantic search "
        "over articles, SIGMA detection rules, and workflow status. "
        "Call get_stats first: it reports **articles** and **Sigma rules** (row count + RAG embedding coverage). "
        "Semantic article tools use **chunk** (annotation) embeddings; keyword search uses raw text — "
        "empty semantic hits do not prove article-level embeddings are missing. "
        "Do not assume the Sigma corpus is empty if search scores are low — threshold labels matches, not retrieval. "
        "Use search_articles for natural language queries about threat techniques. "
        "Use search_unified to search both articles and SIGMA rules at once. "
        "Search results label **Article ID** (database primary key); use that with get_article, "
        "not the 1-based rank in the list. "
        "Use get_article to retrieve full article content by ID. "
        "Use get_sigma_rule to fetch the full YAML and metadata for a Sigma rule by its UUID (Rule ID from search results). "
        "All tools are read-only."
    ),
)

# Shared service instances — initialized at import time so tools have references
_rag: RAGService | None = None
_db: AsyncDatabaseManager | None = None


def _get_services() -> tuple[RAGService, AsyncDatabaseManager]:
    """Get or create shared service instances."""
    global _rag, _db
    if _rag is None:
        logger.info("Initializing RAGService and AsyncDatabaseManager...")
        _rag = RAGService()
        _db = _rag.db_manager
        logger.info("Services initialized.")
    return _rag, _db


# Register all tool modules
_rag_svc, _db_svc = _get_services()
articles.register(mcp, _rag_svc, _db_svc)
sigma.register(mcp, _rag_svc, _db_svc)
sources.register(mcp, _db_svc)
workflow.register(mcp, _db_svc)

logger.info("Huntable CTI Studio MCP server ready — 10 tools registered.")
