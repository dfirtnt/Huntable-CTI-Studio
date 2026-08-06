"""Streamable-HTTP transport for the Huntable CTI Studio MCP server.

Docker MCP Gateway cannot launch this project's stdio server: the launcher shells
out to `docker compose run` on the host, and the Gateway runs inside its own
container. The Gateway does speak to *remote* MCP servers over streamable-HTTP,
so this module serves the exact same `FastMCP` instance — same tools, same
resources, same risk tiers — over HTTP instead of stdin/stdout.

The endpoint is bearer-protected and fails closed: without `HUNTABLE_MCP_TOKEN`
the app refuses to build rather than starting an unauthenticated server that
exposes `execute_sql` and the write tools to anything that can reach the port.
"""

from __future__ import annotations

import hmac
import logging
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from src.huntable_mcp.stdio_server import mcp

logger = logging.getLogger(__name__)

TOKEN_ENV_VAR = "HUNTABLE_MCP_TOKEN"
MIN_TOKEN_LENGTH = 32

# Open so a container healthcheck and the Gateway's reachability probe do not
# need the token. It reports liveness only — no database or corpus state.
HEALTH_PATH = "/healthz"


class MissingTokenError(RuntimeError):
    """Raised when the server is asked to start without a usable bearer token."""


def load_token(env: dict[str, str] | None = None) -> str:
    """Return the configured bearer token, or raise if it is unusable.

    A short token is rejected outright: this endpoint fronts `execute_sql` and
    the audited write tools, so a guessable secret is worse than no endpoint.
    """
    source = os.environ if env is None else env
    token = (source.get(TOKEN_ENV_VAR) or "").strip()
    if not token:
        raise MissingTokenError(
            f"{TOKEN_ENV_VAR} must be set to serve MCP over HTTP. Generate one with "
            "`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` and put it in .env."
        )
    if len(token) < MIN_TOKEN_LENGTH:
        raise MissingTokenError(f"{TOKEN_ENV_VAR} must be at least {MIN_TOKEN_LENGTH} characters; got {len(token)}.")
    return token


class BearerTokenMiddleware:
    """Reject any request to the MCP endpoint without the expected bearer token."""

    def __init__(self, app: ASGIApp, token: str, open_paths: frozenset[str] = frozenset({HEALTH_PATH})):
        self.app = app
        self._token = token
        self._open_paths = open_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self._open_paths:
            await self.app(scope, receive, send)
            return

        if not self._is_authorized(dict(scope.get("headers") or [])):
            # No WWW-Authenticate challenge details: an unauthenticated caller
            # learns only that a token is required, not how tokens are shaped.
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _is_authorized(self, headers: dict[bytes, bytes]) -> bool:
        raw = headers.get(b"authorization", b"").decode("latin-1")
        scheme, _, presented = raw.partition(" ")
        if scheme.lower() != "bearer":
            return False
        return hmac.compare_digest(presented.strip(), self._token)


async def _healthz(_request: Request) -> Response:
    return JSONResponse({"status": "ok", "server": "huntable-cti-studio", "transport": "streamable-http"})


def build_app(token: str | None = None) -> Starlette:
    """Build the bearer-protected streamable-HTTP ASGI app.

    Raises `MissingTokenError` before any socket is bound when no usable token
    is configured.
    """
    resolved = token if token is not None else load_token()

    app = mcp.streamable_http_app()
    app.router.routes.append(Route(HEALTH_PATH, _healthz, methods=["GET"]))

    logger.info(
        "MCP streamable-HTTP app built: endpoint %s, health %s, bearer auth enabled",
        mcp.settings.streamable_http_path,
        HEALTH_PATH,
    )
    return BearerTokenMiddleware(app, resolved)  # type: ignore[return-value]


def run(host: str | None = None, port: int | None = None) -> None:
    """Serve the MCP endpoint over streamable-HTTP."""
    import uvicorn

    resolved_host = host or os.environ.get("HUNTABLE_MCP_HOST", "127.0.0.1")
    resolved_port = port or int(os.environ.get("HUNTABLE_MCP_PORT", "8009"))

    app = build_app()
    logger.info("Serving Huntable MCP over streamable-HTTP on %s:%s", resolved_host, resolved_port)
    uvicorn.run(app, host=resolved_host, port=resolved_port, log_level="info")
