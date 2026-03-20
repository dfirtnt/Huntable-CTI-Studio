#!/usr/bin/env python3
"""Launcher for the Huntable CTI Studio MCP server.

Can be invoked from any working directory — sets up sys.path automatically.
Usage:  python /path/to/Huntable-CTI-Studio/run_mcp.py
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.huntable_mcp.stdio_server import mcp  # noqa: E402

mcp.run()
