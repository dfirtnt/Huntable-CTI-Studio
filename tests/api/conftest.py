"""
API test configuration. Session-scoped event loop and client only when
USE_ASGI_CLIENT=1 so in-process app's async_db_manager stays on one loop.
When USE_ASGI_CLIENT is not set (e.g. smoke), root conftest's function-scoped
fixtures are used so smoke and live-server runs keep passing.
"""

import asyncio
import contextlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager

_WORKFLOW_CONFIG_TEST_LOCK_KEY = 8412772
_SIGMA_QUEUE_TEST_LOCK_KEY = 8412773
_AUTO_TRIGGER_THRESHOLD_KEY = "AUTO_TRIGGER_HUNT_SCORE_THRESHOLD"


def _use_asgi_client() -> bool:
    return os.getenv("USE_ASGI_CLIENT", "").lower() in ("1", "true", "yes")


def _snapshot_ids(session, table_name: str) -> set[int]:
    rows = session.execute(text(f"SELECT id FROM {table_name}"))
    return {int(row[0]) for row in rows}


def _delete_new_rows(session, table_name: str, original_ids: set[int]) -> None:
    if original_ids:
        session.execute(text(f"DELETE FROM {table_name} WHERE id != ALL(:ids)"), {"ids": list(original_ids)})
    else:
        session.execute(text(f"DELETE FROM {table_name}"))


@contextmanager
def _locked_test_session(lock_key: int) -> Iterator[Session]:
    """Hold a session-level PostgreSQL lock on one checked-out connection."""
    connection = DatabaseManager().engine.connect()
    session = Session(bind=connection)
    try:
        session.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
        session.commit()
        yield session
    finally:
        session.rollback()
        with contextlib.suppress(Exception):
            session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            session.commit()
        session.close()
        connection.close()


@pytest.fixture
def preserve_sigma_queue_state():
    """Remove queue rows created by an API test, including failed tests."""
    with _locked_test_session(_SIGMA_QUEUE_TEST_LOCK_KEY) as session:
        original_ids = _snapshot_ids(session, "sigma_rule_queue")
        session.rollback()

        try:
            yield
        finally:
            session.rollback()
            _delete_new_rows(session, "sigma_rule_queue", original_ids)
            session.commit()


@pytest.fixture
def preserve_workflow_config_state(ensure_workflow_config_schema):
    """Restore config-related tables to their exact pre-test row set."""
    with _locked_test_session(_WORKFLOW_CONFIG_TEST_LOCK_KEY) as session:
        config_rows = {
            int(row.id): {
                "is_active": bool(row.is_active),
                "auto_trigger_hunt_score_threshold": row.auto_trigger_hunt_score_threshold,
            }
            for row in session.execute(
                text("SELECT id, is_active, auto_trigger_hunt_score_threshold FROM agentic_workflow_config")
            ).mappings()
        }
        prompt_version_ids = _snapshot_ids(session, "agent_prompt_versions")
        preset_rows = []
        for row in session.execute(
            text("SELECT id, name, description, config_json, created_at, updated_at FROM workflow_config_presets")
        ).mappings():
            preset = dict(row)
            preset["config_json"] = json.dumps(preset["config_json"])
            preset_rows.append(preset)
        threshold_row = (
            session.execute(
                text(
                    "SELECT id, value, description, category, created_at, updated_at FROM app_settings WHERE key = :key"
                ),
                {"key": _AUTO_TRIGGER_THRESHOLD_KEY},
            )
            .mappings()
            .first()
        )
        session.rollback()

        try:
            yield
        finally:
            session.rollback()
            _delete_new_rows(session, "agent_prompt_versions", prompt_version_ids)
            _delete_new_rows(session, "workflow_config_presets", {int(row["id"]) for row in preset_rows})
            for row in preset_rows:
                session.execute(
                    text(
                        "INSERT INTO workflow_config_presets "
                        "(id, name, description, config_json, created_at, updated_at) "
                        "VALUES (:id, :name, :description, CAST(:config_json AS jsonb), :created_at, :updated_at) "
                        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
                        "description = EXCLUDED.description, config_json = EXCLUDED.config_json, "
                        "created_at = EXCLUDED.created_at, updated_at = EXCLUDED.updated_at"
                    ),
                    row,
                )
            _delete_new_rows(session, "agentic_workflow_config", set(config_rows))

            session.execute(text("UPDATE agentic_workflow_config SET is_active = false"))
            for row_id, state in config_rows.items():
                session.execute(
                    text(
                        "UPDATE agentic_workflow_config "
                        "SET is_active = :is_active, "
                        "auto_trigger_hunt_score_threshold = :auto_trigger_hunt_score_threshold "
                        "WHERE id = :id"
                    ),
                    {"id": row_id, **state},
                )

            if threshold_row is None:
                session.execute(
                    text("DELETE FROM app_settings WHERE key = :key"),
                    {"key": _AUTO_TRIGGER_THRESHOLD_KEY},
                )
            else:
                session.execute(
                    text(
                        "UPDATE app_settings SET value = :value, description = :description, "
                        "category = :category, created_at = :created_at, updated_at = :updated_at "
                        "WHERE id = :id"
                    ),
                    dict(threshold_row),
                )

            session.commit()


# Only override with session-scoped fixtures when using in-process ASGI client.
# Otherwise smoke and other runs use root conftest (function-scoped) and avoid
# "Event loop is closed" from mixing session loop with default function-scoped test loop.
if _use_asgi_client():

    @pytest_asyncio.fixture(scope="session")
    def event_loop():
        """One event loop for all API tests (required when USE_ASGI_CLIENT=1)."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest_asyncio.fixture(scope="session")
    async def async_client(ensure_workflow_config_schema):
        """Session-scoped HTTP client when USE_ASGI_CLIENT=1."""
        from httpx import ASGITransport

        from src.web.modern_main import app

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=httpx.Timeout(60.0))
        try:
            yield client
        finally:
            await client.aclose()
