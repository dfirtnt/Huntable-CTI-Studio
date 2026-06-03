"""Unit tests for MCP server environment/default DB behavior."""

from importlib import import_module, reload
from unittest.mock import patch

import pytest

# All tests patch load_dotenv to prevent the real .env file from overriding
# monkeypatched env vars. The module uses override=True so .env wins over the
# process environment — correct for production, but we stub it in tests.
_no_dotenv = patch("dotenv.load_dotenv")


@pytest.mark.unit
def test_mcp_server_forces_non_test_app_env(monkeypatch):
    """MCP server should not run in test APP_ENV by default."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    assert mod.os.environ.get("APP_ENV") == "development"


@pytest.mark.unit
def test_mcp_server_default_database_url_points_to_main_db(monkeypatch):
    """When DATABASE_URL is unset, MCP defaults to localhost:5432/cti_scraper."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    assert mod.os.environ.get("DATABASE_URL") == "postgresql+asyncpg://cti_user:pw123@localhost:5432/cti_scraper"


@pytest.mark.unit
def test_mcp_server_respects_explicit_database_url(monkeypatch):
    """Explicit DATABASE_URL should not be overwritten."""
    explicit = "postgresql+asyncpg://cti_user:explicit@localhost:5439/custom_db"
    monkeypatch.setenv("DATABASE_URL", explicit)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    assert mod.os.environ.get("DATABASE_URL") == explicit


@pytest.mark.unit
def test_mcp_server_sets_url_built_flag_when_assembled_from_password(monkeypatch):
    """_url_built_from_pw flag is True when DATABASE_URL is built from POSTGRES_PASSWORD."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    assert mod._url_built_from_pw is True


@pytest.mark.unit
def test_mcp_server_url_built_flag_false_when_url_explicit(monkeypatch):
    """_url_built_from_pw flag is False when DATABASE_URL was already set."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cti_user:explicit@localhost:5432/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    assert mod._url_built_from_pw is False
