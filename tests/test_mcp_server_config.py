"""Unit tests for MCP server environment/default DB behavior."""

import os
from importlib import import_module, reload
from unittest.mock import patch

import pytest

# All tests patch load_dotenv to prevent the real .env file from overriding
# monkeypatched env vars. The module uses override=True so .env wins over the
# process environment — correct for production, but we stub it in tests.
_no_dotenv = patch("dotenv.load_dotenv")


@pytest.fixture(autouse=True)
def _isolate_broker_env(monkeypatch):
    """stdio_server defaults REDIS_URL at import; keep that from leaking across tests."""
    for key in ("REDIS_URL", "CELERY_BROKER_URL"):
        monkeypatch.setenv(key, os.environ.get(key, ""))


@pytest.mark.unit
def test_mcp_server_defaults_broker_to_localhost_for_host_runs(monkeypatch):
    """A desktop client runs the server on the host with no REDIS_URL; the compose
    hostname celeryconfig falls back to does not resolve there, so default to the
    published localhost port the same way DATABASE_URL is assembled."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    # A first import in this process already ran the default; clear it before the reload under test.
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    with _no_dotenv:
        reload(mod)

    assert mod.os.environ.get("REDIS_URL") == "redis://localhost:6379/0"
    assert mod._redis_url_defaulted is True


@pytest.mark.unit
@pytest.mark.parametrize("key", ["REDIS_URL", "CELERY_BROKER_URL"])
def test_mcp_server_keeps_an_explicit_broker_url(monkeypatch, key):
    """Inside compose (or with an explicit broker) nothing is rewritten."""
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.setenv(key, "redis://redis:6379/0")
    with _no_dotenv:
        reload(mod)

    assert mod.os.environ.get(key) == "redis://redis:6379/0"
    assert mod._redis_url_defaulted is False
    if key == "CELERY_BROKER_URL":
        assert mod.os.environ.get("REDIS_URL") in (None, "")


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


@pytest.mark.unit
def test_mcp_server_registers_ambient_context_resources(monkeypatch):
    """The exported stdio MCP server should expose ambient context resources."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cti_user:explicit@localhost:5432/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    uris = {str(resource.uri) for resource in mod.mcp._resource_manager.list_resources()}

    assert "huntable://sigma-queue/status" in uris
    assert "huntable://sigma-queue/recent-rules" in uris
    assert "huntable://workflow/active-config" in uris


@pytest.mark.unit
def test_mcp_server_registers_eval_diagnosis_tools(monkeypatch):
    """The exported stdio MCP server should expose eval bundle and diagnosis tools."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://cti_user:explicit@localhost:5432/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw123")

    mod = import_module("src.huntable_mcp.stdio_server")
    with _no_dotenv:
        reload(mod)

    tool_names = {tool.name for tool in mod.mcp._tool_manager.list_tools()}

    assert "get_eval_bundle" in tool_names
    assert "list_eval_diagnoses" in tool_names
    assert "export_diagnosed_eval_bundles" in tool_names
    # Diagnosis is agent-authored over MCP: context out, validated diagnosis in.
    assert "get_eval_diagnosis_context" in tool_names
    assert "save_eval_diagnosis" in tool_names
    # The retired server-side LLM diagnosis tool must not come back.
    assert "diagnose_eval_bundle" not in tool_names
    assert "get_eval_bundles_by_config" in tool_names
    assert "get_article_eval_bundle" in tool_names
    assert "get_workflow_execution_trace" in tool_names
    assert "get_eval_run" in tool_names
    # Launching evals over MCP is a caller-attested write that bills the provider.
    assert "run_subagent_eval" in tool_names
    assert "get_subagent_eval_status" in tool_names
