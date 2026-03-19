"""Huntable CTI Studio MCP Server.

Exposes CTI database search, SIGMA rules, sources, and workflow status
as MCP tools for use by any LLM client (Claude Code, Claude Desktop, etc.).
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.database.async_manager import AsyncDatabaseManager
from src.mcp.tools import articles, sigma, sources, workflow
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "huntable-cti-studio",
    instructions=(
        "Huntable CTI Studio — a threat intelligence database with semantic search "
        "over articles, SIGMA detection rules, and workflow status. "
        "Use search_articles for natural language queries about threat techniques. "
        "Use search_unified to search both articles and SIGMA rules at once. "
        "Search results label **Article ID** (database primary key); use that with get_article, "
        "not the 1-based rank in the list. "
        "Use get_article to retrieve full article content by ID. "
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
sigma.register(mcp, _rag_svc)
sources.register(mcp, _db_svc)
workflow.register(mcp, _db_svc)

logger.info("Huntable CTI Studio MCP server ready — 9 tools registered.")
