"""Request-ID and identity middleware (Chunk A)."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp

from src.database.async_manager import async_db_manager
from src.services.audit_service import (
    ACTION_AUTH_REQUEST_DENIED,
    STATUS_DENIED,
    AsyncAuditService,
    AuditEvent,
    build_actor_context,
)
from src.web.dependencies import logger
from src.web.security.config import AuthMode, SecurityConfig
from src.web.security.identity import (
    IdentityResult,
    local_dev_identity,
    parse_trusted_identity,
    unauthenticated,
)
from src.web.security.route_manifest import (
    RouteClassification,
    find_manifest_entry,
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


class AuthorizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, config: SecurityConfig) -> None:
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next):
        if not self.config.auth_enabled:
            return await call_next(request)

        manifest = getattr(request.app.state, "route_manifest", [])
        entry = find_manifest_entry(manifest, request.method, request.url.path)
        if entry and entry.classification is RouteClassification.PUBLIC:
            return await call_next(request)

        if entry is None and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self._deny(request, 403, "Route is not classified for unsafe access")

        identity = getattr(request.state, "identity", None)
        if not identity or not identity.is_authenticated:
            return await self._deny(request, 401, "Authentication required")

        if entry and entry.classification is RouteClassification.ROLES:
            if not self._has_any_role(identity.roles, entry.roles):
                return await self._deny(request, 403, "Insufficient role")

        return await call_next(request)

    @staticmethod
    def _has_any_role(identity_roles: tuple[str, ...], required_roles: tuple[str, ...]) -> bool:
        return "admin" in identity_roles or bool(set(identity_roles) & set(required_roles))

    async def _deny(self, request: Request, status_code: int, detail: str):
        await self._audit_denial(request, status_code, detail)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": detail}, status_code=status_code)
        return PlainTextResponse(detail, status_code=status_code)

    async def _audit_denial(self, request: Request, status_code: int, detail: str) -> None:
        try:
            identity = getattr(request.state, "identity", None)
            actor = build_actor_context(identity, request)
            event = AuditEvent(
                action=ACTION_AUTH_REQUEST_DENIED,
                target_type="route",
                target_id=f"{request.method.upper()} {request.url.path}",
                status=STATUS_DENIED,
                summary=detail,
                actor=actor,
                metadata={
                    "method": request.method.upper(),
                    "path": request.url.path,
                    "status_code": status_code,
                },
                error_code=str(status_code),
            )
            async with async_db_manager.get_session() as session:
                await AsyncAuditService.record_best_effort(session, event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to write denied-request audit event request_id=%s path=%s: %s",
                getattr(request.state, "request_id", "-"),
                request.url.path,
                exc,
            )
