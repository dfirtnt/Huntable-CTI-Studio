"""ASGI-level tests for request-ID and identity middleware (Chunk A).

Uses a tiny throwaway Starlette app so no database or containers are needed.
"""

import httpx
import pytest
from httpx import ASGITransport
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.web.security.config import AuthMode, SecurityConfig
from src.web.security.middleware import IdentityMiddleware, RequestIDMiddleware


def _config(**over):
    base = dict(
        app_env="test",
        auth_mode=AuthMode.DISABLED,
        allow_insecure_prod_auth_disabled=False,
        trusted_hosts=("*",),
        cors_allowed_origins=("*",),
        trusted_proxy_header="X-Huntable-Verified",
        trusted_proxy_value="true",
        trusted_proxy_ips=(),
        user_id_header="X-Huntable-User-Id",
        email_header="X-Huntable-Email",
        name_header="X-Huntable-Name",
        groups_header="X-Huntable-Groups",
        group_role_map={"admin": ("cti-admins",), "operator": ("cti-ops",)},
    )
    base.update(over)
    return SecurityConfig(**base)


def _app(config):
    async def whoami(request):
        ident = request.state.identity
        return JSONResponse(
            {
                "auth": ident.is_authenticated,
                "user": ident.user_id,
                "roles": list(ident.roles),
                "rid": request.state.request_id,
            }
        )

    app = Starlette(routes=[Route("/whoami", whoami)])
    # IdentityMiddleware added first => RequestIDMiddleware wraps outermost (runs first).
    app.add_middleware(IdentityMiddleware, config=config)
    app.add_middleware(RequestIDMiddleware)
    return app


async def _get(config, path="/whoami", headers=None):
    transport = ASGITransport(app=_app(config))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path, headers=headers or {})


@pytest.mark.asyncio
async def test_disabled_mode_yields_local_dev_admin():
    r = await _get(_config())
    body = r.json()
    assert body["user"] == "local-dev"
    assert body["roles"] == ["admin"]
    assert r.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_request_id_is_generated_when_absent():
    r = await _get(_config())
    assert len(r.headers["X-Request-ID"]) >= 8


@pytest.mark.asyncio
async def test_request_id_is_echoed_when_provided():
    r = await _get(_config(), headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    assert r.json()["rid"] == "abc123"


@pytest.mark.asyncio
async def test_trusted_header_mode_authenticates_via_marker_and_groups():
    r = await _get(
        _config(auth_mode=AuthMode.TRUSTED_HEADER),
        headers={
            "X-Huntable-Verified": "true",
            "X-Huntable-User-Id": "u1",
            "X-Huntable-Groups": "cti-ops",
        },
    )
    body = r.json()
    assert body["auth"] is True
    assert body["user"] == "u1"
    assert body["roles"] == ["operator"]


@pytest.mark.asyncio
async def test_trusted_header_mode_ignores_headers_without_marker():
    r = await _get(
        _config(auth_mode=AuthMode.TRUSTED_HEADER),
        headers={"X-Huntable-User-Id": "attacker", "X-Huntable-Groups": "cti-admins"},
    )
    body = r.json()
    assert body["auth"] is False
    assert body["user"] is None
    assert body["roles"] == []
