"""The MCP streamable-HTTP endpoint must fail closed and demand a bearer token.

This transport puts `execute_sql` and the audited write tools on a TCP port, so
the interesting cases are the negative ones: no token configured, a weak token,
a missing header, a wrong header, and the wrong scheme.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.huntable_mcp.http_server import (
    HEALTH_PATH,
    MIN_TOKEN_LENGTH,
    TOKEN_ENV_VAR,
    BearerTokenMiddleware,
    MissingTokenError,
    load_token,
)

pytestmark = pytest.mark.unit

GOOD_TOKEN = "t" * MIN_TOKEN_LENGTH


def _guarded_client(token: str = GOOD_TOKEN) -> TestClient:
    """Wrap a stand-in ASGI app so these tests never import the real server stack."""

    async def _ok(_request):
        return JSONResponse({"reached": True})

    async def _health(_request):
        return JSONResponse({"status": "ok"})

    inner = Starlette(routes=[Route("/mcp", _ok, methods=["GET", "POST"]), Route(HEALTH_PATH, _health)])
    return TestClient(BearerTokenMiddleware(inner, token))


def test_load_token_rejects_missing_token():
    with pytest.raises(MissingTokenError) as exc:
        load_token({})
    assert TOKEN_ENV_VAR in str(exc.value)


def test_load_token_rejects_blank_token():
    with pytest.raises(MissingTokenError):
        load_token({TOKEN_ENV_VAR: "   "})


def test_load_token_rejects_short_token():
    with pytest.raises(MissingTokenError) as exc:
        load_token({TOKEN_ENV_VAR: "short"})
    assert str(MIN_TOKEN_LENGTH) in str(exc.value)


def test_load_token_accepts_and_strips_a_usable_token():
    assert load_token({TOKEN_ENV_VAR: f"  {GOOD_TOKEN}  "}) == GOOD_TOKEN


def test_request_without_authorization_header_is_rejected():
    response = _guarded_client().post("/mcp", json={})
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


@pytest.mark.parametrize(
    "header",
    [
        "Bearer wrong-token",
        f"Basic {GOOD_TOKEN}",
        GOOD_TOKEN,
        "Bearer",
        f"Bearer {GOOD_TOKEN}x",
        f"Bearer {GOOD_TOKEN[:-1]}",
    ],
)
def test_wrong_credentials_are_rejected(header):
    response = _guarded_client().post("/mcp", headers={"Authorization": header}, json={})
    assert response.status_code == 401


def test_correct_bearer_token_reaches_the_mcp_app():
    response = _guarded_client().post("/mcp", headers={"Authorization": f"Bearer {GOOD_TOKEN}"}, json={})
    assert response.status_code == 200
    assert response.json() == {"reached": True}


def test_bearer_scheme_is_matched_case_insensitively():
    response = _guarded_client().post("/mcp", headers={"Authorization": f"bearer {GOOD_TOKEN}"}, json={})
    assert response.status_code == 200


def test_health_endpoint_needs_no_token():
    response = _guarded_client().get(HEALTH_PATH)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_401_response_does_not_leak_token_shape():
    response = _guarded_client().post("/mcp", json={})
    body = response.text
    assert GOOD_TOKEN not in body
    assert "WWW-Authenticate" not in response.headers
