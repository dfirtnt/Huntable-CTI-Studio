"""Entry point for running the MCP server: python3 -m src.huntable_mcp

Adds the project root to sys.path so the server can be launched from any
working directory (important for MCP clients that don't honour cwd).

Defaults to stdio, the transport every desktop MCP client speaks. Pass
`--transport http` (or set `HUNTABLE_MCP_TRANSPORT=http`) to serve the same
tools over a bearer-protected streamable-HTTP endpoint instead, which is how
Docker MCP Gateway connects — see `src/huntable_mcp/http_server.py`.
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

from src.huntable_mcp.cli import main  # noqa: E402

main()
