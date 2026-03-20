"""Entry point for running the MCP server: python3 -m src.huntable_mcp

Adds the project root to sys.path so the server can be launched from any
working directory (important for MCP clients that don't honour cwd).
"""

import logging
import sys
from pathlib import Path

# Configure logging before importing the app stack (stdio MCP: never log to stdout).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
    force=True,
)

# Project root is three levels up from this file: src/huntable_mcp/__main__.py → repo root
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.huntable_mcp.stdio_server import mcp  # noqa: E402

mcp.run()
