"""
Unit tests for src/services/workflow_provider_options.py

Tests cover the four provider availability states from the task spec:
  - enabled/disabled
  - configured/unconfigured (API key present or absent)
  - LM Studio reachable/unreachable
  - saved model outside the current catalog
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.workflow_provider_options import (
    ProviderStatus,
    _is_embedding_model,
    _read_settings,
    get_provider_options,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper / unit-level tests
# ---------------------------------------------------------------------------


class TestIsEmbeddingModel:
    def test_chat_model_not_flagged(self):
        assert not _is_embedding_model("mistralai/mistral-7b-instruct-v0.3")

    def test_embedding_keyword_flagged(self):
        assert _is_embedding_model("nomic-ai/nomic-embed-text-v1.5")

    def test_bge_prefix_flagged(self):
        assert _is_embedding_model("BAAI/bge-small-en-v1.5")

    def test_gte_prefix_flagged(self):
        assert _is_embedding_model("thenlper/gte-large")

    def test_e5_base_flagged(self):
        assert _is_embedding_model("intfloat/e5-base-v2")

    def test_gpt_not_flagged(self):
        assert not _is_embedding_model("gpt-4o-mini")

    def test_claude_not_flagged(self):
        assert not _is_embedding_model("claude-sonnet-4-6")


class TestProviderStatusToDict:
    def test_round_trip(self):
        s = ProviderStatus(
            enabled=True,
            configured=True,
            reachable=True,
            has_models=True,
            models=["model-a"],
            default_model="model-a",
            reason_unavailable=None,
        )
        d = s.to_dict()
        assert d["enabled"] is True
        assert d["models"] == ["model-a"]
        assert d["reason_unavailable"] is None

    def test_reason_present_when_set(self):
        s = ProviderStatus(
            enabled=False,
            configured=False,
            reachable=False,
            has_models=False,
            reason_unavailable="Provider is not enabled in settings",
        )
        assert s.to_dict()["reason_unavailable"] == "Provider is not enabled in settings"


# ---------------------------------------------------------------------------
# _read_settings
# ---------------------------------------------------------------------------


class TestReadSettings:
    def _make_session(self, rows: list[tuple[str, str]]):
        """Return a mock DB session whose query returns AppSettingsTable-like rows."""
        mock_rows = []
        for key, value in rows:
            row = MagicMock()
            row.key = key
            row.value = value
            mock_rows.append(row)

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = mock_rows
        return session

    def test_reads_enabled_flags_from_db(self):
        session = self._make_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "true"),
                ("WORKFLOW_OPENAI_ENABLED", "false"),
                ("WORKFLOW_ANTHROPIC_ENABLED", "false"),
            ]
        )
        result = _read_settings(session)
        assert result["WORKFLOW_LMSTUDIO_ENABLED"] == "true"
        assert result["WORKFLOW_OPENAI_ENABLED"] == "false"

    def test_env_fallback_for_api_key(self, monkeypatch):
        session = self._make_session([])  # no DB rows
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        result = _read_settings(session)
        assert result.get("WORKFLOW_OPENAI_API_KEY") == "sk-test-key"

    def test_workflow_prefix_key_takes_priority(self, monkeypatch):
        session = self._make_session(
            [
                ("WORKFLOW_OPENAI_API_KEY", "sk-db-key"),
            ]
        )
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        result = _read_settings(session)
        assert result["WORKFLOW_OPENAI_API_KEY"] == "sk-db-key"

    def test_enabled_flag_defaults_false_when_missing(self, monkeypatch):
        session = self._make_session([])
        monkeypatch.delenv("WORKFLOW_LMSTUDIO_ENABLED", raising=False)
        result = _read_settings(session)
        assert result.get("WORKFLOW_LMSTUDIO_ENABLED", "false") == "false"


# ---------------------------------------------------------------------------
# get_provider_options -- integration of the full service function
# ---------------------------------------------------------------------------


def _make_db_session(settings_rows: list[tuple[str, str]]):
    mock_rows = []
    for key, value in settings_rows:
        row = MagicMock()
        row.key = key
        row.value = value
        mock_rows.append(row)
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = mock_rows
    return session


CATALOG_WITH_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini"],
    "anthropic": ["claude-sonnet-4-6", "claude-3-haiku-20240307"],
}


class TestGetProviderOptionsDisabledProviders:
    """All providers disabled -- reason_unavailable should explain it."""

    @pytest.mark.asyncio
    async def test_all_disabled_returns_reason(self, monkeypatch):
        session = _make_db_session([])
        monkeypatch.delenv("WORKFLOW_LMSTUDIO_ENABLED", raising=False)
        monkeypatch.delenv("WORKFLOW_OPENAI_ENABLED", raising=False)
        monkeypatch.delenv("WORKFLOW_ANTHROPIC_ENABLED", raising=False)

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=CATALOG_WITH_MODELS),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        providers = result["providers"]
        assert providers["lmstudio"]["enabled"] is False
        assert providers["openai"]["enabled"] is False
        assert providers["anthropic"]["enabled"] is False
        assert "not enabled" in providers["lmstudio"]["reason_unavailable"]
        assert result["default_provider"] == ""

    @pytest.mark.asyncio
    async def test_default_provider_empty_when_none_enabled(self, monkeypatch):
        session = _make_db_session([])
        monkeypatch.delenv("WORKFLOW_LMSTUDIO_ENABLED", raising=False)
        monkeypatch.delenv("WORKFLOW_OPENAI_ENABLED", raising=False)
        monkeypatch.delenv("WORKFLOW_ANTHROPIC_ENABLED", raising=False)

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value={}),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        assert result["default_provider"] == ""


class TestGetProviderOptionsLMStudio:
    """LM Studio reachable/unreachable state coverage."""

    @pytest.mark.asyncio
    async def test_lmstudio_enabled_and_reachable(self):
        session = _make_db_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "true"),
            ]
        )
        chat_models = ["mistral-7b-instruct", "llama3-8b"]

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value={}),
            patch(
                "src.services.workflow_provider_options._probe_lmstudio",
                new=AsyncMock(return_value=(True, chat_models)),
            ),
        ):
            result = await get_provider_options(session)

        lm = result["providers"]["lmstudio"]
        assert lm["enabled"] is True
        assert lm["reachable"] is True
        assert lm["has_models"] is True
        assert lm["models"] == chat_models
        assert lm["default_model"] == chat_models[0]
        assert lm["reason_unavailable"] is None
        assert result["default_provider"] == "lmstudio"

    @pytest.mark.asyncio
    async def test_lmstudio_enabled_but_unreachable(self):
        session = _make_db_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "true"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value={}),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        lm = result["providers"]["lmstudio"]
        assert lm["enabled"] is True
        assert lm["reachable"] is False
        assert lm["has_models"] is False
        assert "not reachable" in lm["reason_unavailable"]

    @pytest.mark.asyncio
    async def test_lmstudio_reachable_no_chat_models(self):
        """LM Studio responds but only has embedding models loaded."""
        session = _make_db_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "true"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value={}),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(True, []))),
        ):
            result = await get_provider_options(session)

        lm = result["providers"]["lmstudio"]
        assert lm["reachable"] is True
        assert lm["has_models"] is False
        assert lm["models"] == []
        assert "No chat models" in lm["reason_unavailable"]

    @pytest.mark.asyncio
    async def test_lmstudio_disabled_probe_not_called(self):
        """Probe must not fire when LM Studio is disabled."""
        session = _make_db_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "false"),
            ]
        )
        probe = AsyncMock(return_value=(True, ["model-x"]))

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value={}),
            patch("src.services.workflow_provider_options._probe_lmstudio", probe),
        ):
            await get_provider_options(session)

        probe.assert_not_called()


class TestGetProviderOptionsCommercial:
    """OpenAI / Anthropic configured/unconfigured state coverage."""

    @pytest.mark.asyncio
    async def test_openai_enabled_with_key(self):
        session = _make_db_session(
            [
                ("WORKFLOW_OPENAI_ENABLED", "true"),
                ("WORKFLOW_OPENAI_API_KEY", "sk-real-key"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=CATALOG_WITH_MODELS),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        oa = result["providers"]["openai"]
        assert oa["enabled"] is True
        assert oa["configured"] is True
        assert oa["has_models"] is True
        assert oa["reason_unavailable"] is None
        assert result["default_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_openai_enabled_without_key(self):
        session = _make_db_session(
            [
                ("WORKFLOW_OPENAI_ENABLED", "true"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=CATALOG_WITH_MODELS),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        oa = result["providers"]["openai"]
        assert oa["enabled"] is True
        assert oa["configured"] is False
        assert "API key" in oa["reason_unavailable"]

    @pytest.mark.asyncio
    async def test_anthropic_enabled_with_key(self):
        session = _make_db_session(
            [
                ("WORKFLOW_ANTHROPIC_ENABLED", "true"),
                ("WORKFLOW_ANTHROPIC_API_KEY", "sk-ant-key"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=CATALOG_WITH_MODELS),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        an = result["providers"]["anthropic"]
        assert an["enabled"] is True
        assert an["configured"] is True
        assert an["has_models"] is True
        assert an["reason_unavailable"] is None


class TestGetProviderOptionsSavedModelOutsideCatalog:
    """
    The saved model may not exist in the current catalog (e.g. catalog was
    updated, or a different catalog is active). The endpoint should still
    include the catalog list so the UI can detect the mismatch.
    """

    @pytest.mark.asyncio
    async def test_catalog_does_not_include_saved_model(self):
        """
        Simulate: openai enabled+keyed, but catalog has different models than
        what the agent config has saved. The endpoint returns the catalog as-is;
        the UI is responsible for showing the mismatch warning.
        """
        session = _make_db_session(
            [
                ("WORKFLOW_OPENAI_ENABLED", "true"),
                ("WORKFLOW_OPENAI_API_KEY", "sk-key"),
            ]
        )
        # Catalog has only new models; old saved model (gpt-4-turbo) is absent
        catalog = {"openai": ["gpt-4o", "gpt-4o-mini"], "anthropic": []}

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=catalog),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        oa = result["providers"]["openai"]
        assert oa["has_models"] is True
        assert "gpt-4-turbo" not in oa["models"]
        assert "gpt-4o" in oa["models"]


class TestGetProviderOptionsDefaultProviderPriority:
    """default_provider reflects the first enabled+has-models provider."""

    @pytest.mark.asyncio
    async def test_lmstudio_preferred_over_openai_when_both_enabled(self):
        session = _make_db_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "true"),
                ("WORKFLOW_OPENAI_ENABLED", "true"),
                ("WORKFLOW_OPENAI_API_KEY", "sk-key"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=CATALOG_WITH_MODELS),
            patch(
                "src.services.workflow_provider_options._probe_lmstudio",
                new=AsyncMock(return_value=(True, ["mistral-7b"])),
            ),
        ):
            result = await get_provider_options(session)

        assert result["default_provider"] == "lmstudio"

    @pytest.mark.asyncio
    async def test_falls_back_to_openai_when_lmstudio_unreachable(self):
        session = _make_db_session(
            [
                ("WORKFLOW_LMSTUDIO_ENABLED", "true"),
                ("WORKFLOW_OPENAI_ENABLED", "true"),
                ("WORKFLOW_OPENAI_API_KEY", "sk-key"),
            ]
        )

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value=CATALOG_WITH_MODELS),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        assert result["default_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_response_shape_has_all_three_providers(self):
        session = _make_db_session([])

        with (
            patch("src.services.workflow_provider_options.load_catalog", return_value={}),
            patch("src.services.workflow_provider_options._probe_lmstudio", new=AsyncMock(return_value=(False, []))),
        ):
            result = await get_provider_options(session)

        assert set(result["providers"].keys()) == {"lmstudio", "openai", "anthropic"}
        for provider_data in result["providers"].values():
            required_keys = {
                "enabled",
                "configured",
                "reachable",
                "has_models",
                "models",
                "default_model",
                "reason_unavailable",
            }
            assert required_keys == set(provider_data.keys())
