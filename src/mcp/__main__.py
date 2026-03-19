"""Entry point for running the MCP server: python -m src.mcp

Adds the project root to sys.path so the server can be launched from any
working directory (important for MCP clients that don't honour cwd).
"""

import sys
from pathlib import Path

# Project root is three levels up from this file: src/mcp/__main__.py → repo root
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.mcp.server import mcp  # noqa: E402

mcp.run()
