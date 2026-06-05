"""Regression tests for scripts/maintenance/update_provider_model_catalogs.py.

Root-cause context: the daily catalog-refresh job silently fetched nothing for
months because it read the API key from the bare env var ``OPENAI_API_KEY``
(empty in this deployment) instead of the live key persisted in AppSettings
(``WORKFLOW_OPENAI_API_KEY``). With no key it logged "retaining existing list"
and returned ``[]`` every run, so the catalog froze and newly-released models
never surfaced in the dropdowns.

These tests pin the key-resolution contract so the regression cannot recur:
  - AppSettings (DB) key is preferred over the env var.
  - The env var is used only as a fallback.
  - An *empty* DB value is treated as absent (the exact original failure).
  - Provider configs carry the correct AppSettings key names.
  - ``fetch_models`` honors a DB-only key (does not early-return as "missing").
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

MODULE = "scripts.maintenance.update_provider_model_catalogs"


@pytest.fixture
def mod():
    return importlib.import_module(MODULE)


# ─── ProviderConfig wiring ───────────────────────────────────────────────────


class TestProviderConfigKeys:
    """Each provider must point at the AppSettings key the Settings page writes."""

    def test_openai_app_settings_key(self, mod):
        oa = next(p for p in mod.PROVIDERS if p.name == "openai")
        assert oa.app_settings_key == "WORKFLOW_OPENAI_API_KEY"
        assert oa.env_var == "OPENAI_API_KEY"

    def test_anthropic_app_settings_key(self, mod):
        an = next(p for p in mod.PROVIDERS if p.name == "anthropic")
        assert an.app_settings_key == "WORKFLOW_ANTHROPIC_API_KEY"
        assert an.env_var == "ANTHROPIC_API_KEY"


# ─── resolve_api_key: DB-first, env fallback ─────────────────────────────────


class TestResolveApiKey:
    """resolve_api_key() prefers the AppSettings key, falls back to env."""

    def _provider(self, mod):
        return mod.ProviderConfig(
            name="openai",
            env_var="OPENAI_API_KEY",
            app_settings_key="WORKFLOW_OPENAI_API_KEY",
            url="https://example/v1/models",
            headers_builder=lambda k: {},
            filter_fn=lambda x: x,
        )

    def test_db_key_preferred_over_env(self, mod, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        with patch.object(mod, "_load_app_settings_key", return_value="db-key"):
            assert mod.resolve_api_key(self._provider(mod)) == "db-key"

    def test_env_fallback_when_no_db_key(self, mod, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        with patch.object(mod, "_load_app_settings_key", return_value=None):
            assert mod.resolve_api_key(self._provider(mod)) == "env-key"

    def test_none_when_neither_present(self, mod, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with patch.object(mod, "_load_app_settings_key", return_value=None):
            assert mod.resolve_api_key(self._provider(mod)) is None


# ─── _load_app_settings_key: DB read semantics ───────────────────────────────


def _patch_db(mod, *, row_value, raises=False):
    """Patch the DB boundary _load_app_settings_key imports lazily.

    Returns a context manager stack configuring DatabaseManager().get_session()
    -> session.query(...).filter(...).one_or_none() to yield a row (or None).
    """
    session = MagicMock()
    if row_value is None:
        session.query.return_value.filter.return_value.one_or_none.return_value = None
    else:
        row = MagicMock()
        row.value = row_value
        session.query.return_value.filter.return_value.one_or_none.return_value = row

    db_instance = MagicMock()
    db_instance.get_session.return_value = session

    db_manager_cls = MagicMock()
    if raises:
        db_manager_cls.side_effect = RuntimeError("db down")
    else:
        db_manager_cls.return_value = db_instance

    return patch("src.database.manager.DatabaseManager", db_manager_cls), session


class TestLoadAppSettingsKey:
    """_load_app_settings_key() reads a single AppSettings row, defensively."""

    def test_reads_value_from_db(self, mod):
        ctx, session = _patch_db(mod, row_value="sk-proj-live")
        with ctx:
            assert mod._load_app_settings_key("WORKFLOW_OPENAI_API_KEY") == "sk-proj-live"
        session.close.assert_called_once()

    def test_empty_string_value_treated_as_absent(self, mod):
        """The original bug: an empty key must resolve to None, not ''."""
        ctx, _ = _patch_db(mod, row_value="")
        with ctx:
            assert mod._load_app_settings_key("WORKFLOW_OPENAI_API_KEY") is None

    def test_missing_row_returns_none(self, mod):
        ctx, _ = _patch_db(mod, row_value=None)
        with ctx:
            assert mod._load_app_settings_key("WORKFLOW_OPENAI_API_KEY") is None

    def test_blank_setting_key_short_circuits(self, mod):
        # No DB access should happen for an empty setting key.
        with patch("src.database.manager.DatabaseManager") as dbm:
            assert mod._load_app_settings_key("") is None
            dbm.assert_not_called()

    def test_db_exception_returns_none_gracefully(self, mod):
        ctx, _ = _patch_db(mod, row_value="ignored", raises=True)
        with ctx:
            assert mod._load_app_settings_key("WORKFLOW_OPENAI_API_KEY") is None


# ─── fetch_models honors a DB-only key ───────────────────────────────────────


class TestFetchModelsKeyResolution:
    """fetch_models() must use resolve_api_key, not os.getenv alone."""

    def _openai_provider(self, mod):
        return next(p for p in mod.PROVIDERS if p.name == "openai")

    def test_no_key_retains_existing_list(self, mod):
        with patch.object(mod, "resolve_api_key", return_value=None):
            assert mod.fetch_models(self._openai_provider(mod)) == []

    def test_db_only_key_triggers_fetch_and_filters(self, mod):
        """Regression: a key present only in the DB must NOT be seen as missing.

        Before the fix, fetch_models read the empty env var and bailed with [].
        """
        fake_resp = MagicMock()
        fake_resp.raise_for_status.return_value = None
        fake_resp.json.return_value = {
            "data": [
                {"id": "gpt-5.4"},
                {"id": "gpt-4o"},
                {"id": "gpt-4o-2024-05-13"},  # dated -> filtered out
                {"id": "text-embedding-3-large"},  # non-chat -> filtered out
            ]
        }
        with (
            patch.object(mod, "resolve_api_key", return_value="sk-proj-live"),
            patch.object(mod, "requests") as req,
        ):
            req.get.return_value = fake_resp
            result = mod.fetch_models(self._openai_provider(mod))

        # The fetch happened (not the empty early-return) and the project filter ran.
        assert req.get.called
        assert "gpt-5.4" in result
        assert "gpt-4o" in result
        assert "gpt-4o-2024-05-13" not in result
        assert "text-embedding-3-large" not in result
