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


class AuthMode(str, Enum):  # noqa: UP042 - keep (str, Enum); StrEnum changes __str__/__format__ used in this auth code
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
