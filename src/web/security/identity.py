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
    has_identity_headers = any(lower.get(h.lower()) for h in (cfg.user_id_header, cfg.email_header, cfg.groups_header))

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
