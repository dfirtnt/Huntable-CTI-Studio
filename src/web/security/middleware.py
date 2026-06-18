"""Request-ID and identity middleware (Chunk A)."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from src.web.dependencies import logger
from src.web.security.config import AuthMode, SecurityConfig
from src.web.security.identity import (
    IdentityResult,
    local_dev_identity,
    parse_trusted_identity,
    unauthenticated,
)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class IdentityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, config: SecurityConfig) -> None:
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next):
        result = self._resolve(request)
        request.state.identity = result.identity
        if result.spoof_attempt:
            logger.warning(
                "Rejected spoofed identity headers request_id=%s path=%s peer=%s",
                getattr(request.state, "request_id", "-"),
                request.url.path,
                request.client.host if request.client else None,
            )
        return await call_next(request)

    def _resolve(self, request: Request) -> IdentityResult:
        if self.config.auth_mode is AuthMode.DISABLED:
            return IdentityResult(local_dev_identity())
        if self.config.auth_mode is AuthMode.TRUSTED_HEADER:
            peer_ip = request.client.host if request.client else None
            return parse_trusted_identity(request.headers, peer_ip, self.config)
        # OIDC placeholder: treat as unauthenticated in Chunk A.
        return IdentityResult(unauthenticated(self.config.auth_mode.value))
