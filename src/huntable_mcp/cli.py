"""Shared launcher for the MCP server, used by both entry points.

`python -m src.huntable_mcp` and the repo-root `run_mcp.py` both call `main()`
so the transport flags stay identical no matter which one a client invokes.
"""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="huntable-mcp")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("HUNTABLE_MCP_TRANSPORT", "stdio"),
        help="stdio (default) for desktop MCP clients; http for Docker MCP Gateway.",
    )
    parser.add_argument("--host", default=None, help="HTTP bind address (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default 8009).")
    args = parser.parse_args(argv)

    if args.transport == "http":
        from src.huntable_mcp.http_server import run as run_http

        run_http(host=args.host, port=args.port)
        return

    from src.huntable_mcp.stdio_server import mcp

    mcp.run()
