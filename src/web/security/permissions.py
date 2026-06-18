"""Permission dependencies for enterprise route authorization."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, status
from starlette.requests import Request

from src.web.security.identity import RequestIdentity, unauthenticated


def _identity(request: Request) -> RequestIdentity:
    return getattr(request.state, "identity", None) or unauthenticated("disabled")


def _has_role(identity: RequestIdentity, role: str) -> bool:
    return "admin" in identity.roles or role in identity.roles


def require_authenticated(request: Request) -> RequestIdentity:
    """Return the request identity or raise 401."""
    identity = _identity(request)
    if not identity.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return identity


def require_role(role: str) -> Callable[[Request], RequestIdentity]:
    """Return a dependency requiring a single role.

    The `admin` role is intentionally treated as including every role in the
    initial enterprise model.
    """

    def _dependency(request: Request) -> RequestIdentity:
        identity = require_authenticated(request)
        if not _has_role(identity, role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return identity

    return _dependency


def require_any_role(*roles: str) -> Callable[[Request], RequestIdentity]:
    """Return a dependency requiring any listed role."""

    def _dependency(request: Request) -> RequestIdentity:
        identity = require_authenticated(request)
        if not any(_has_role(identity, role) for role in roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return identity

    return _dependency
