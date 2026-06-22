# Enterprise Auth Chunk A — Secure Boundary & Request Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an env-driven, fail-closed security config plus request-ID and trusted-header identity middleware so the app refuses insecure production startup and attaches a verified `request.state.identity` to every request — with zero behavior change for local development.

**Architecture:** A dependency-light, unit-testable `src/web/security/` package: `config.py` (pure parse + fail-closed validation), `identity.py` (pure identity types + trusted-header parsing + group→role mapping), `middleware.py` (two Starlette `BaseHTTPMiddleware` classes), and a `permissions.py` stub (inert in Chunk A; enforcement lands in Chunk B). `modern_main.py` loads the config at import, gates CORS/TrustedHost to production, and registers the two middlewares.

**Tech Stack:** FastAPI/Starlette, `BaseHTTPMiddleware`, httpx `ASGITransport` for tests, pytest / pytest-asyncio, `run_tests.py` runner.

**Spec:** [`docs/superpowers/specs/2026-06-17-enterprise-auth-chunk-a-boundary-identity.md`](../specs/2026-06-17-enterprise-auth-chunk-a-boundary-identity.md)

**Key constraints discovered during planning (do not violate):**
- The runner sets `APP_ENV=test` (`tests_runner/runner.py:364`). Fail-closed logic triggers **only** when `APP_ENV=production`, so importing the app in tests must never raise.
- API tests hit the app over `http://testserver`. If `TrustedHostMiddleware` used the configured hosts in tests it would 400 every request. **Host/CORS tightening applies only in production**; non-production stays `["*"]` (preserves current dev behavior).
- `SECRET_KEY` fail-closed is intentionally **out of scope** here — it moves to Chunk B with CSRF. Do not add it.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/web/security/__init__.py` | Package marker (empty). |
| `src/web/security/config.py` | `SecurityConfig`, `AuthMode`, `InsecureConfigError`, `load_security_config()`. Pure; no FastAPI imports. |
| `src/web/security/identity.py` | `RequestIdentity`, `IdentityResult`, service-identity constants, `map_groups_to_roles`, `parse_trusted_identity`, `local_dev_identity`, `service_identity`, `unauthenticated`. Pure. |
| `src/web/security/middleware.py` | `RequestIDMiddleware`, `IdentityMiddleware`. |
| `src/web/security/permissions.py` | Inert `require_authenticated`/`require_role`/`require_any_role` stub (stable import target for Chunk B). |
| `src/web/modern_main.py` | Wire config + middleware; gate CORS/TrustedHost to production. |
| `.env.example`, `docs/guides/authentication.md` | Operator-facing config surface (Chunk A subset). |

---

### Task 1: Security config module

**Files:**
- Create: `src/web/security/__init__.py`, `src/web/security/config.py`
- Test: `tests/unit/test_security_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_security_config.py`:

```python
"""Unit tests for the fail-closed security config loader (Chunk A)."""

import pytest

from src.web.security.config import AuthMode, InsecureConfigError, load_security_config


def _env(**over):
    base = {"APP_ENV": "development", "AUTH_MODE": "disabled"}
    base.update(over)
    return base


def test_dev_defaults_load_without_error():
    cfg = load_security_config(_env())
    assert cfg.auth_mode is AuthMode.DISABLED
    assert cfg.is_production is False
    assert cfg.auth_enabled is False


def test_production_auth_disabled_raises():
    with pytest.raises(InsecureConfigError):
        load_security_config(_env(APP_ENV="production", AUTH_MODE="disabled"))


def test_production_auth_disabled_with_breakglass_ok():
    cfg = load_security_config(
        _env(
            APP_ENV="production",
            AUTH_MODE="disabled",
            ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED="true",
            TRUSTED_HOSTS="cti.example.com",
            CORS_ALLOWED_ORIGINS="https://cti.example.com",
        )
    )
    assert cfg.is_production is True


def test_production_wildcard_hosts_raises():
    with pytest.raises(InsecureConfigError):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="*",
                CORS_ALLOWED_ORIGINS="https://cti.example.com",
            )
        )


def test_production_wildcard_cors_raises():
    with pytest.raises(InsecureConfigError):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="cti.example.com",
                CORS_ALLOWED_ORIGINS="*",
            )
        )


def test_production_trusted_header_ok():
    cfg = load_security_config(
        _env(
            APP_ENV="production",
            AUTH_MODE="trusted_header",
            TRUSTED_HOSTS="cti.example.com",
            CORS_ALLOWED_ORIGINS="https://cti.example.com",
        )
    )
    assert cfg.auth_enabled is True
    assert cfg.trusted_hosts == ("cti.example.com",)


def test_csv_parsing_trims_and_splits():
    cfg = load_security_config(_env(TRUSTED_HOSTS="a, b ,c"))
    assert cfg.trusted_hosts == ("a", "b", "c")


def test_invalid_auth_mode_raises():
    with pytest.raises(InsecureConfigError):
        load_security_config(_env(AUTH_MODE="banana"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 run_tests.py unit --paths tests/unit/test_security_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.web.security'`.

- [ ] **Step 3: Create the package marker**

Create `src/web/security/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Write minimal implementation**

Create `src/web/security/config.py`:

```python
"""Security configuration for the web layer (Chunk A).

Pure parsing + fail-closed validation of security-relevant environment
variables. No FastAPI imports here so it stays trivially unit-testable.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

WILDCARD = "*"


class AuthMode(str, Enum):
    DISABLED = "disabled"
    TRUSTED_HEADER = "trusted_header"
    OIDC = "oidc"  # reserved no-op placeholder in Chunk A


class InsecureConfigError(RuntimeError):
    """Raised at startup when the production security posture is unsafe."""


def _split_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _as_bool(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes")


# role name -> env var holding the comma-separated IdP group list that grants it
_ROLE_ENV = {
    "admin": "AUTH_ADMIN_GROUPS",
    "operator": "AUTH_OPERATOR_GROUPS",
    "rule_reviewer": "AUTH_REVIEWER_GROUPS",
    "analyst": "AUTH_ANALYST_GROUPS",
}


@dataclass(frozen=True)
class SecurityConfig:
    app_env: str
    auth_mode: AuthMode
    allow_insecure_prod_auth_disabled: bool
    trusted_hosts: tuple[str, ...]
    cors_allowed_origins: tuple[str, ...]
    trusted_proxy_header: str
    trusted_proxy_value: str
    trusted_proxy_ips: tuple[str, ...]
    user_id_header: str
    email_header: str
    name_header: str
    groups_header: str
    group_role_map: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def auth_enabled(self) -> bool:
        return self.auth_mode is not AuthMode.DISABLED


def load_security_config(env: Mapping[str, str] | None = None) -> SecurityConfig:
    """Build and validate SecurityConfig from env (defaults to os.environ).

    Raises InsecureConfigError when APP_ENV=production and the posture is unsafe.
    """
    e = os.environ if env is None else env

    raw_mode = (e.get("AUTH_MODE", "disabled") or "disabled").strip().lower()
    try:
        auth_mode = AuthMode(raw_mode)
    except ValueError as exc:
        raise InsecureConfigError(f"Invalid AUTH_MODE: {raw_mode!r}") from exc

    group_role_map = {role: _split_csv(e.get(var)) for role, var in _ROLE_ENV.items()}

    cfg = SecurityConfig(
        app_env=e.get("APP_ENV", "development"),
        auth_mode=auth_mode,
        allow_insecure_prod_auth_disabled=_as_bool(e.get("ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED")),
        trusted_hosts=_split_csv(e.get("TRUSTED_HOSTS", "localhost,127.0.0.1")),
        cors_allowed_origins=_split_csv(e.get("CORS_ALLOWED_ORIGINS", "http://localhost:8001")),
        trusted_proxy_header=e.get("AUTH_TRUSTED_PROXY_HEADER", "X-Huntable-Verified"),
        trusted_proxy_value=e.get("AUTH_TRUSTED_PROXY_VALUE", "true"),
        trusted_proxy_ips=_split_csv(e.get("AUTH_TRUSTED_PROXY_IPS")),
        user_id_header=e.get("AUTH_USER_ID_HEADER", "X-Huntable-User-Id"),
        email_header=e.get("AUTH_EMAIL_HEADER", "X-Huntable-Email"),
        name_header=e.get("AUTH_NAME_HEADER", "X-Huntable-Name"),
        groups_header=e.get("AUTH_GROUPS_HEADER", "X-Huntable-Groups"),
        group_role_map=group_role_map,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: SecurityConfig) -> None:
    if not cfg.is_production:
        return
    if cfg.auth_mode is AuthMode.DISABLED and not cfg.allow_insecure_prod_auth_disabled:
        raise InsecureConfigError(
            "AUTH_MODE=disabled is not allowed in production. Set AUTH_MODE=trusted_header, "
            "or set ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true to override."
        )
    if WILDCARD in cfg.trusted_hosts:
        raise InsecureConfigError("Wildcard TRUSTED_HOSTS is not allowed in production.")
    if WILDCARD in cfg.cors_allowed_origins:
        raise InsecureConfigError("Wildcard CORS_ALLOWED_ORIGINS is not allowed in production.")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 run_tests.py unit --paths tests/unit/test_security_config.py -v`
Expected: PASS (8 passed).

- [ ] **Step 6: Commit**

```bash
git add src/web/security/__init__.py src/web/security/config.py tests/unit/test_security_config.py
git commit -m "feat(security): add fail-closed security config loader (Chunk A)"
```

---

### Task 2: Request identity types and pure helpers

**Files:**
- Create: `src/web/security/identity.py`
- Test: `tests/unit/test_request_identity.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_request_identity.py`:

```python
"""Unit tests for pure identity helpers (Chunk A)."""

from src.web.security.config import load_security_config
from src.web.security.identity import (
    SERVICE_CELERY_WORKER,
    local_dev_identity,
    map_groups_to_roles,
    parse_trusted_identity,
    service_identity,
)


def _cfg(**over):
    env = {
        "APP_ENV": "development",
        "AUTH_MODE": "trusted_header",
        "AUTH_ADMIN_GROUPS": "cti-admins",
        "AUTH_OPERATOR_GROUPS": "cti-ops",
        "AUTH_REVIEWER_GROUPS": "cti-reviewers",
        "AUTH_ANALYST_GROUPS": "cti-analysts",
    }
    env.update(over)
    return load_security_config(env)


def test_map_groups_to_roles_is_sorted_and_deduped():
    roles = map_groups_to_roles(("cti-ops", "cti-admins", "cti-ops"), _cfg())
    assert roles == ("admin", "operator")


def test_map_groups_unknown_group_yields_no_roles():
    assert map_groups_to_roles(("random",), _cfg()) == ()


def test_local_dev_identity_is_admin():
    ident = local_dev_identity()
    assert ident.is_authenticated is True
    assert ident.roles == ("admin",)
    assert ident.actor_type == "local-dev"


def test_service_identity_shape():
    ident = service_identity(SERVICE_CELERY_WORKER)
    assert ident.actor_type == "service"
    assert ident.user_id == "service:celery-worker"


def test_parse_missing_marker_is_unauthenticated_and_flags_spoof():
    res = parse_trusted_identity(
        {"X-Huntable-User-Id": "attacker", "X-Huntable-Groups": "cti-admins"},
        "10.0.0.9",
        _cfg(),
    )
    assert res.identity.is_authenticated is False
    assert res.spoof_attempt is True


def test_parse_with_marker_authenticates_and_maps_roles():
    res = parse_trusted_identity(
        {
            "X-Huntable-Verified": "true",
            "X-Huntable-User-Id": "u1",
            "X-Huntable-Email": "u1@x.io",
            "X-Huntable-Groups": "cti-ops",
        },
        "10.0.0.9",
        _cfg(),
    )
    assert res.identity.is_authenticated is True
    assert res.identity.roles == ("operator",)
    assert res.identity.email == "u1@x.io"
    assert res.spoof_attempt is False


def test_parse_untrusted_peer_rejected_even_with_marker():
    res = parse_trusted_identity(
        {"X-Huntable-Verified": "true", "X-Huntable-User-Id": "u1", "X-Huntable-Groups": "cti-ops"},
        "10.9.9.9",
        _cfg(AUTH_TRUSTED_PROXY_IPS="10.0.0.1"),
    )
    assert res.identity.is_authenticated is False
    assert res.spoof_attempt is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 run_tests.py unit --paths tests/unit/test_request_identity.py -v`
Expected: FAIL — `ImportError: cannot import name ... from 'src.web.security.identity'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/web/security/identity.py`:

```python
"""Request identity types and pure helpers (Chunk A)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.web.security.config import AuthMode, SecurityConfig

# Synthetic service identities (wired into worker/scheduler/CLI audit in Chunk C).
SERVICE_CELERY_WORKER = "service:celery-worker"
SERVICE_WORKFLOW_WORKER = "service:workflow-worker"
SERVICE_SCHEDULER = "service:scheduler"
SERVICE_CLI = "service:cli"


@dataclass(frozen=True)
class RequestIdentity:
    is_authenticated: bool
    user_id: str | None
    email: str | None
    display_name: str | None
    groups: tuple[str, ...]
    roles: tuple[str, ...]
    auth_mode: str
    actor_type: str = "human"  # human | service | local-dev | unknown


@dataclass(frozen=True)
class IdentityResult:
    identity: RequestIdentity
    spoof_attempt: bool = False


def local_dev_identity() -> RequestIdentity:
    return RequestIdentity(
        is_authenticated=True,
        user_id="local-dev",
        email=None,
        display_name="Local Dev",
        groups=(),
        roles=("admin",),
        auth_mode=AuthMode.DISABLED.value,
        actor_type="local-dev",
    )


def unauthenticated(auth_mode: str) -> RequestIdentity:
    return RequestIdentity(
        is_authenticated=False,
        user_id=None,
        email=None,
        display_name=None,
        groups=(),
        roles=(),
        auth_mode=auth_mode,
        actor_type="unknown",
    )


def service_identity(name: str) -> RequestIdentity:
    return RequestIdentity(
        is_authenticated=True,
        user_id=name,
        email=None,
        display_name=name,
        groups=(),
        roles=("operator",),
        auth_mode="service",
        actor_type="service",
    )


def map_groups_to_roles(groups: tuple[str, ...], cfg: SecurityConfig) -> tuple[str, ...]:
    """Deterministically map IdP groups to app roles (sorted, de-duplicated)."""
    group_set = {g.strip() for g in groups if g.strip()}
    roles: set[str] = set()
    for role, role_groups in cfg.group_role_map.items():
        if group_set & set(role_groups):
            roles.add(role)
    return tuple(sorted(roles))


def _split_groups(raw: str | None) -> list[str]:
    if not raw:
        return []
    # Groups header may be comma- or space-separated depending on the proxy.
    return [p for p in raw.replace(",", " ").split() if p]


def parse_trusted_identity(
    headers: Mapping[str, str],
    peer_ip: str | None,
    cfg: SecurityConfig,
) -> IdentityResult:
    """Parse a verified-identity request in trusted_header mode.

    Returns an unauthenticated identity with spoof_attempt=True when identity
    headers are present without the trusted proxy marker or from an untrusted peer.
    """
    lower = {k.lower(): v for k, v in headers.items()}

    marker = lower.get(cfg.trusted_proxy_header.lower())
    has_identity_headers = any(
        lower.get(h.lower()) for h in (cfg.user_id_header, cfg.email_header, cfg.groups_header)
    )

    marker_ok = marker is not None and marker == cfg.trusted_proxy_value
    peer_ok = (not cfg.trusted_proxy_ips) or (peer_ip in cfg.trusted_proxy_ips)

    if not (marker_ok and peer_ok):
        return IdentityResult(unauthenticated(cfg.auth_mode.value), spoof_attempt=has_identity_headers)

    groups = tuple(_split_groups(lower.get(cfg.groups_header.lower())))
    user_id = lower.get(cfg.user_id_header.lower())
    identity = RequestIdentity(
        is_authenticated=bool(user_id),
        user_id=user_id,
        email=lower.get(cfg.email_header.lower()),
        display_name=lower.get(cfg.name_header.lower()),
        groups=groups,
        roles=map_groups_to_roles(groups, cfg),
        auth_mode=cfg.auth_mode.value,
        actor_type="human",
    )
    return IdentityResult(identity, spoof_attempt=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 run_tests.py unit --paths tests/unit/test_request_identity.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/web/security/identity.py tests/unit/test_request_identity.py
git commit -m "feat(security): add request identity types and trusted-header parsing (Chunk A)"
```

---

### Task 3: Request-ID and identity middleware

**Files:**
- Create: `src/web/security/middleware.py`
- Test: `tests/unit/test_security_middleware.py` (uses a throwaway Starlette app over httpx ASGI — no DB, runs under `unit`)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_security_middleware.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 run_tests.py unit --paths tests/unit/test_security_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.web.security.middleware'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/web/security/middleware.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 run_tests.py unit --paths tests/unit/test_security_middleware.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/web/security/middleware.py tests/unit/test_security_middleware.py
git commit -m "feat(security): add request-ID and identity middleware (Chunk A)"
```

---

### Task 4: Permission helper stub

**Files:**
- Create: `src/web/security/permissions.py`
- Test: `tests/unit/test_permissions_stub.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_permissions_stub.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 run_tests.py unit --paths tests/unit/test_permissions_stub.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.web.security.permissions'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/web/security/permissions.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 run_tests.py unit --paths tests/unit/test_permissions_stub.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/web/security/permissions.py tests/unit/test_permissions_stub.py
git commit -m "feat(security): add inert permission-helper stub for Chunk B (Chunk A)"
```

---

### Task 5: Wire config and middleware into the app

**Files:**
- Modify: `src/web/modern_main.py:175-194`
- Test: `tests/api/test_app_security_wiring.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_app_security_wiring.py`:

```python
"""The real app loads a SecurityConfig and attaches X-Request-ID to responses."""

import httpx
import pytest


def test_app_exposes_security_config():
    from src.web.modern_main import SECURITY_CONFIG

    assert SECURITY_CONFIG.auth_mode.value in ("disabled", "trusted_header", "oidc")


@pytest.mark.api
@pytest.mark.asyncio
async def test_app_adds_request_id_header(async_client: httpx.AsyncClient):
    # A 404 path avoids any DB dependency; the middleware still stamps the header.
    response = await async_client.get("/api/__no_such_path__")
    assert response.status_code == 404
    assert response.headers.get("X-Request-ID")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 run_tests.py api --paths tests/api/test_app_security_wiring.py -v`
Expected: FAIL — `ImportError: cannot import name 'SECURITY_CONFIG'` and no `X-Request-ID` header.

- [ ] **Step 3: Add the imports**

In `src/web/modern_main.py`, add to the import block (after line 23, the `from src.web.routes import register_routes` line):

```python
from src.web.security.config import load_security_config
from src.web.security.middleware import IdentityMiddleware, RequestIDMiddleware
```

- [ ] **Step 4: Replace the middleware block**

In `src/web/modern_main.py`, replace this exact block (lines 182-190):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # nosemgrep
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
```

with:

```python
# Fail-closed security config: raises in production if the posture is unsafe.
SECURITY_CONFIG = load_security_config()
_prod = SECURITY_CONFIG.is_production

app.add_middleware(
    CORSMiddleware,
    # Lock origins to the configured allowlist in production; keep permissive
    # local-dev behavior otherwise.
    allow_origins=list(SECURITY_CONFIG.cors_allowed_origins) if _prod else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(SECURITY_CONFIG.trusted_hosts) if _prod else ["*"],
)
# IdentityMiddleware added before RequestIDMiddleware so request-ID wraps
# outermost and is available to identity logging and every response.
app.add_middleware(IdentityMiddleware, config=SECURITY_CONFIG)
app.add_middleware(RequestIDMiddleware)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 run_tests.py api --paths tests/api/test_app_security_wiring.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run a broader smoke + api regression to confirm no host/CORS breakage**

Run: `python3 run_tests.py smoke api -v`
Expected: PASS — existing API tests still reach the app over `http://testserver` (host/CORS stay permissive outside production).

- [ ] **Step 7: Commit**

```bash
git add src/web/modern_main.py tests/api/test_app_security_wiring.py
git commit -m "feat(security): wire fail-closed config and identity/request-ID middleware into app (Chunk A)"
```

---

### Task 6: Operator config surface (.env.example + auth doc)

**Files:**
- Modify: `.env.example` (confirm it exists with `ls .env.example` first; if absent, create it)
- Create: `docs/guides/authentication.md`

- [ ] **Step 1: Confirm the env example file exists**

Run: `ls .env.example`
Expected: the file path prints. (If "No such file", create it in Step 2 instead of appending.)

- [ ] **Step 2: Append the security block to `.env.example`**

Append:

```bash

# --- Security & Auth (Chunk A) ---
# Set APP_ENV=production to enable fail-closed startup checks.
APP_ENV=development
# disabled | trusted_header | oidc(reserved). production + disabled fails startup
# unless ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true.
AUTH_MODE=disabled
ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=false

# Host/CORS allowlists are enforced only when APP_ENV=production (wildcards rejected there).
TRUSTED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:8001

# Trusted-header SSO (used only when AUTH_MODE=trusted_header). The upstream
# proxy MUST strip client-supplied X-Huntable-* headers, then set verified ones.
AUTH_TRUSTED_PROXY_HEADER=X-Huntable-Verified
AUTH_TRUSTED_PROXY_VALUE=true
# Optional: restrict which immediate peer IPs may supply identity headers.
AUTH_TRUSTED_PROXY_IPS=
AUTH_USER_ID_HEADER=X-Huntable-User-Id
AUTH_EMAIL_HEADER=X-Huntable-Email
AUTH_NAME_HEADER=X-Huntable-Name
AUTH_GROUPS_HEADER=X-Huntable-Groups
# Map IdP group names to roles (comma-separated). Do not commit real customer groups.
AUTH_ADMIN_GROUPS=
AUTH_OPERATOR_GROUPS=
AUTH_REVIEWER_GROUPS=
AUTH_ANALYST_GROUPS=
```

- [ ] **Step 3: Create the authentication guide**

Create `docs/guides/authentication.md`:

```markdown
# Authentication (Phase A: Boundary & Identity)

This phase establishes a secure startup posture and a verified request identity.
Route authorization (who-can-do-what) and audit logging arrive in later chunks.

## Modes (`AUTH_MODE`)

| Mode | Use | Production |
|---|---|---|
| `disabled` | Local development. Every request gets a synthetic `local-dev` admin identity. | Rejected at startup unless `ALLOW_INSECURE_PRODUCTION_AUTH_DISABLED=true`. |
| `trusted_header` | An identity-aware proxy injects verified user headers. | Supported. |
| `oidc` | Reserved placeholder. Treated as unauthenticated for now. | Not yet. |

## Fail-closed startup (when `APP_ENV=production`)

Startup aborts if: `AUTH_MODE=disabled` (without the break-glass override),
`TRUSTED_HOSTS` is wildcard, or `CORS_ALLOWED_ORIGINS` is wildcard.

## Trusted-header contract

The app trusts identity headers **only** when the request carries the proxy
marker (`AUTH_TRUSTED_PROXY_HEADER` == `AUTH_TRUSTED_PROXY_VALUE`) and, if
`AUTH_TRUSTED_PROXY_IPS` is set, originates from a listed peer.

> **The proxy must strip then set.** It must remove any client-supplied
> `X-Huntable-*` headers before injecting verified identity headers, and direct
> network access to the app must be blocked. Application tests prove header
> parsing and spoof rejection; they cannot prove network isolation.

Requests presenting identity headers without the marker (or from an untrusted
peer) are treated as impersonation attempts: ignored and logged.

## Request IDs

Every response carries `X-Request-ID` (echoed from the proxy if provided, else
generated). It is attached to `request.state.request_id` for correlation.
```

- [ ] **Step 4: Verify the env keys landed**

Run: `grep -c "AUTH_MODE\|TRUSTED_HOSTS\|AUTH_TRUSTED_PROXY_HEADER" .env.example`
Expected: a count of `3` or greater.

- [ ] **Step 5: Commit**

```bash
git add .env.example docs/guides/authentication.md
git commit -m "docs(security): document Chunk A auth modes and env config"
```

---

## Final verification

- [ ] **Run the full Chunk A test set**

Run: `python3 run_tests.py unit api --paths tests/unit/test_security_config.py tests/unit/test_request_identity.py tests/unit/test_security_middleware.py tests/unit/test_permissions_stub.py tests/api/test_app_security_wiring.py -v`
Expected: all PASS (25 tests).

- [ ] **Run smoke to confirm app boots and serves**

Run: `python3 run_tests.py smoke -v`
Expected: PASS.

---

## Spec Coverage (self-review)

| Chunk A spec requirement | Task |
|---|---|
| `AUTH_MODE` + `APP_ENV` config | 1 |
| Env-driven `TRUSTED_HOSTS` / `CORS_ALLOWED_ORIGINS`; wildcards replaced in prod | 1, 5 |
| Fail-closed startup (auth-disabled / wildcard hosts / wildcard CORS) + break-glass | 1 |
| `RequestIdentity` shape | 2 |
| Trusted-header parsing + spoof rejection (marker + peer IP) | 2 |
| Synthetic local-dev identity for disabled mode | 2, 3 |
| Deterministic group→role mapping | 2 |
| Service-identity types (for Chunk C) | 2 |
| Request-ID middleware (accept/generate/return) | 3, 5 |
| Identity middleware attaches `request.state.identity` + logs spoof | 3, 5 |
| `permissions.py` stub (stable import for Chunk B) | 4 |
| `.env.example` + auth doc | 6 |
| **Deferred (not built here):** `SECRET_KEY` fail-closed → Chunk B; `auth.request_denied` audit event → Chunk C | — |

**Note for the implementer:** the parent build spec lists a `SECRET_KEY` fail-closed check under Slice 1 — it is deliberately excluded from this plan (no session/cookie/CSRF exists yet) and moves to Chunk B. Do not add it here.
