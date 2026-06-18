"""Permission helper contract for enterprise route authorization."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.web.security.identity import RequestIdentity, local_dev_identity, unauthenticated
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


def test_require_authenticated_raises_for_unauthenticated_identity():
    with pytest.raises(HTTPException) as exc_info:
        require_authenticated(_request_with_identity(unauthenticated("trusted_header")))

    assert exc_info.value.status_code == 401


def test_require_role_returns_dependency_that_yields_identity_for_matching_role():
    dep = require_role("admin")
    ident = local_dev_identity()
    assert dep(_request_with_identity(ident)) is ident


def test_require_role_rejects_missing_role():
    dep = require_role("admin")
    ident = RequestIdentity(
        is_authenticated=True,
        user_id="u1",
        email="user@example.com",
        display_name="User",
        groups=(),
        roles=("analyst",),
        auth_mode="trusted_header",
    )

    with pytest.raises(HTTPException) as exc_info:
        dep(_request_with_identity(ident))

    assert exc_info.value.status_code == 403


def test_admin_role_satisfies_other_role_dependencies():
    dep = require_role("operator")
    ident = local_dev_identity()
    assert dep(_request_with_identity(ident)) is ident


def test_require_any_role_returns_dependency_that_yields_identity_for_matching_role():
    dep = require_any_role("operator", "admin")
    ident = local_dev_identity()
    assert dep(_request_with_identity(ident)) is ident


def test_require_any_role_rejects_unrelated_role():
    dep = require_any_role("operator", "admin")
    ident = RequestIdentity(
        is_authenticated=True,
        user_id="u1",
        email="user@example.com",
        display_name="User",
        groups=(),
        roles=("analyst",),
        auth_mode="trusted_header",
    )

    with pytest.raises(HTTPException) as exc_info:
        dep(_request_with_identity(ident))

    assert exc_info.value.status_code == 403
