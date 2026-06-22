"""Permission dependencies (Chunk A stub).

Enforcement (raising 401/403) is added in Chunk B. In Chunk A these are inert
pass-throughs so routes and tests have a stable import surface.
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.requests import Request

from src.web.security.identity import RequestIdentity, unauthenticated


def _identity(request: Request) -> RequestIdentity:
    return getattr(request.state, "identity", None) or unauthenticated("disabled")


def require_authenticated(request: Request) -> RequestIdentity:
    """Return the request identity. (Chunk B will enforce authentication.)"""
    return _identity(request)


def require_role(role: str) -> Callable[[Request], RequestIdentity]:
    """Return a dependency yielding the identity. (Chunk B will enforce the role.)"""

    def _dependency(request: Request) -> RequestIdentity:
        return _identity(request)

    return _dependency


def require_any_role(*roles: str) -> Callable[[Request], RequestIdentity]:
    """Return a dependency yielding the identity. (Chunk B will enforce the roles.)"""

    def _dependency(request: Request) -> RequestIdentity:
        return _identity(request)

    return _dependency
