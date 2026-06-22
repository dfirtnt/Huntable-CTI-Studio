"""The Chunk A permission stubs are inert pass-throughs (enforcement is Chunk B)."""

from starlette.requests import Request

from src.web.security.identity import local_dev_identity
from src.web.security.permissions import (
    require_any_role,
    require_authenticated,
    require_role,
)


def _request_with_identity(identity):
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    req.state.identity = identity
    return req


def test_require_authenticated_returns_identity():
    ident = local_dev_identity()
    assert require_authenticated(_request_with_identity(ident)) is ident


def test_require_role_returns_dependency_that_yields_identity():
    dep = require_role("admin")
    ident = local_dev_identity()
    assert dep(_request_with_identity(ident)) is ident


def test_require_any_role_returns_dependency_that_yields_identity():
    dep = require_any_role("operator", "admin")
    ident = local_dev_identity()
    assert dep(_request_with_identity(ident)) is ident
