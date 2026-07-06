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


_STRONG_SECRET = "a-very-strong-secret-key-1234567890"


def test_production_trusted_header_ok():
    cfg = load_security_config(
        _env(
            APP_ENV="production",
            AUTH_MODE="trusted_header",
            TRUSTED_HOSTS="cti.example.com",
            CORS_ALLOWED_ORIGINS="https://cti.example.com",
            AUTH_TRUSTED_PROXY_IPS="10.0.0.1",
            SECRET_KEY=_STRONG_SECRET,
        )
    )
    assert cfg.auth_enabled is True
    assert cfg.trusted_hosts == ("cti.example.com",)
    assert cfg.csrf_active is True
    assert cfg.trusted_proxy_ips == ("10.0.0.1",)


def test_production_trusted_header_empty_proxy_ips_raises():
    # SRF-1: empty AUTH_TRUSTED_PROXY_IPS means any direct peer can forge
    # identity headers, so production startup must fail closed.
    with pytest.raises(InsecureConfigError, match="AUTH_TRUSTED_PROXY_IPS"):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="cti.example.com",
                CORS_ALLOWED_ORIGINS="https://cti.example.com",
                SECRET_KEY=_STRONG_SECRET,
            )
        )


def test_production_trusted_header_empty_proxy_ips_with_breakglass_ok():
    cfg = load_security_config(
        _env(
            APP_ENV="production",
            AUTH_MODE="trusted_header",
            TRUSTED_HOSTS="cti.example.com",
            CORS_ALLOWED_ORIGINS="https://cti.example.com",
            ALLOW_INSECURE_PRODUCTION_TRUSTED_PROXY_OPEN="true",
            SECRET_KEY=_STRONG_SECRET,
        )
    )
    assert cfg.auth_enabled is True
    assert cfg.trusted_proxy_ips == ()


def test_production_trusted_header_wildcard_proxy_ip_raises():
    # "*" has wildcard semantics for TRUSTED_HOSTS/CORS in the same file, but the
    # peer gate is exact-match: "*" can never match and would lock everyone out.
    with pytest.raises(InsecureConfigError, match="literal IP"):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="cti.example.com",
                CORS_ALLOWED_ORIGINS="https://cti.example.com",
                AUTH_TRUSTED_PROXY_IPS="*",
                SECRET_KEY=_STRONG_SECRET,
            )
        )


def test_production_trusted_header_cidr_proxy_ip_raises():
    with pytest.raises(InsecureConfigError, match="literal IP"):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="cti.example.com",
                CORS_ALLOWED_ORIGINS="https://cti.example.com",
                AUTH_TRUSTED_PROXY_IPS="10.0.0.0/8",
                SECRET_KEY=_STRONG_SECRET,
            )
        )


def test_dev_trusted_header_empty_proxy_ips_ok():
    # The fail-close is production-only; dev/test trusted_header stays usable
    # without a proxy allowlist.
    cfg = load_security_config(_env(AUTH_MODE="trusted_header", SECRET_KEY=_STRONG_SECRET))
    assert cfg.auth_enabled is True
    assert cfg.trusted_proxy_ips == ()


def test_production_trusted_header_missing_secret_key_raises():
    # auto-CSRF is active under trusted_header, so a missing SECRET_KEY fails closed.
    with pytest.raises(InsecureConfigError, match="SECRET_KEY"):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="cti.example.com",
                CORS_ALLOWED_ORIGINS="https://cti.example.com",
                AUTH_TRUSTED_PROXY_IPS="10.0.0.1",
            )
        )


def test_production_default_secret_key_rejected():
    with pytest.raises(InsecureConfigError, match="SECRET_KEY"):
        load_security_config(
            _env(
                APP_ENV="production",
                AUTH_MODE="trusted_header",
                TRUSTED_HOSTS="cti.example.com",
                CORS_ALLOWED_ORIGINS="https://cti.example.com",
                AUTH_TRUSTED_PROXY_IPS="10.0.0.1",
                SECRET_KEY="change-me",
            )
        )


def test_production_bearer_only_csrf_disabled_skips_secret_key():
    cfg = load_security_config(
        _env(
            APP_ENV="production",
            AUTH_MODE="trusted_header",
            TRUSTED_HOSTS="cti.example.com",
            CORS_ALLOWED_ORIGINS="https://cti.example.com",
            AUTH_TRUSTED_PROXY_IPS="10.0.0.1",
            CSRF_ENABLED="false",
        )
    )
    assert cfg.csrf_active is False
    assert cfg.auth_enabled is True


def test_csrf_auto_inactive_when_auth_disabled():
    cfg = load_security_config(_env())
    assert cfg.csrf_active is False


def test_csrf_explicit_true_activates_outside_production():
    cfg = load_security_config(_env(CSRF_ENABLED="true", SECRET_KEY=_STRONG_SECRET))
    assert cfg.csrf_active is True


def test_csv_parsing_trims_and_splits():
    cfg = load_security_config(_env(TRUSTED_HOSTS="a, b ,c"))
    assert cfg.trusted_hosts == ("a", "b", "c")


def test_invalid_auth_mode_raises():
    with pytest.raises(InsecureConfigError):
        load_security_config(_env(AUTH_MODE="banana"))
