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


def test_parse_with_marker_but_no_user_id_is_not_authenticated():
    res = parse_trusted_identity(
        {"X-Huntable-Verified": "true", "X-Huntable-Email": "u1@x.io"},
        "10.0.0.9",
        _cfg(),
    )
    assert res.identity.is_authenticated is False
    assert res.spoof_attempt is False
