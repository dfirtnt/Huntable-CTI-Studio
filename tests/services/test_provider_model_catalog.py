"""Unit tests for src.services.provider_model_catalog."""

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

from src.services import provider_model_catalog as catalog_module
from src.services.provider_model_catalog import (
    DEFAULT_CATALOG,
    load_catalog,
    save_catalog,
    update_provider_models,
)


class TestLoadCatalog:
    """load_catalog: read catalog from path or default; apply openai/anthropic filters."""

    def test_missing_path_returns_default_with_filters_applied(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        with patch.object(catalog_module, "CATALOG_PATH", path):
            out = load_catalog()
        assert "openai" in out
        assert "anthropic" in out
        # OpenAI: no dated variants
        for m in out["openai"]:
            assert "-2024-" not in m and "-2025-" not in m
        # OpenAI: project allowlist applied — only workflow-relevant models survive
        from src.utils.model_validation import PROJECT_OPENAI_ALLOWLIST

        assert set(out["openai"]) <= PROJECT_OPENAI_ALLOWLIST
        # Anthropic: one per family (filter applied)
        assert isinstance(out["anthropic"], list)
        assert len(out["anthropic"]) <= len(DEFAULT_CATALOG["anthropic"])

    def test_valid_json_applies_filters(self, tmp_path):
        path = tmp_path / "catalog.json"
        raw = {
            "openai": ["gpt-4o", "gpt-4o-2024-05-13"],
            "anthropic": ["claude-sonnet-4-5", "claude-sonnet-4-5-20250929"],
        }
        path.write_text(json.dumps(raw))
        with patch.object(catalog_module, "CATALOG_PATH", path):
            out = load_catalog()
        assert "gpt-4o" in out["openai"]
        assert "gpt-4o-2024-05-13" not in out["openai"]
        assert len(out["anthropic"]) == 1
        assert "claude-sonnet-4-5" in out["anthropic"]

    def test_load_catalog_drops_non_allowlisted_chat_models(self, tmp_path):
        """Valid chat models not in the project allowlist should be filtered out."""
        path = tmp_path / "catalog.json"
        raw = {
            "openai": [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4.1",
                "gpt-4.1-mini",
                "o3-mini",
                "o4-mini",
                # valid chat models but NOT in project allowlist:
                "gpt-5",
                "gpt-5-mini",
                "gpt-4-turbo",
                "o1",
                "o3-pro",
                "codex-mini",
                "gpt-3.5-turbo",
            ],
            "anthropic": [],
        }
        path.write_text(json.dumps(raw))
        with patch.object(catalog_module, "CATALOG_PATH", path):
            out = load_catalog()
        from src.utils.model_validation import PROJECT_OPENAI_ALLOWLIST

        assert set(out["openai"]) == PROJECT_OPENAI_ALLOWLIST

    def test_load_catalog_default_catalog_yields_only_allowlisted(self, tmp_path):
        """DEFAULT_CATALOG includes non-chat entries (realtime, tts, etc.)
        — load_catalog must filter them all out."""
        path = tmp_path / "nonexistent.json"
        with patch.object(catalog_module, "CATALOG_PATH", path):
            out = load_catalog()
        from src.utils.model_validation import PROJECT_OPENAI_ALLOWLIST

        # Every surviving OpenAI model must be in the allowlist
        assert set(out["openai"]) <= PROJECT_OPENAI_ALLOWLIST
        # Specifically, non-chat models from DEFAULT_CATALOG must be gone
        for noise in (
            "gpt-4o-realtime-preview-2024-12-17",
            "gpt-4o-mini-tts",
            "gpt-4o-mini-transcribe",
            "o3-mini-high",
            "o3-mini-low",
            "codex-mini-latest",
            "gpt-4.1-realtime-preview",
            "gpt-4.1-nano",
            "gpt-4.1-turbo",
            "o4",
            "o1",
            "o1-mini",
            "o1-preview",
            "o1-lite",
        ):
            assert noise not in out["openai"], f"{noise} should have been filtered"

    def test_invalid_json_raises_http_exception(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text("{ invalid }")
        with patch.object(catalog_module, "CATALOG_PATH", path), pytest.raises(HTTPException) as exc_info:
            load_catalog()
        assert exc_info.value.status_code == 500
        assert "Invalid provider catalog" in exc_info.value.detail


class TestSaveCatalog:
    """save_catalog: write catalog JSON to path."""

    def test_writes_indented_sorted_json(self, tmp_path):
        path = tmp_path / "catalog.json"
        with patch.object(catalog_module, "CATALOG_PATH", path):
            save_catalog({"openai": ["gpt-4o"], "anthropic": ["claude-3-opus"]})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["openai"] == ["gpt-4o"]
        assert data["anthropic"] == ["claude-3-opus"]

    def test_creates_parent_dir(self, tmp_path):
        path = tmp_path / "sub" / "catalog.json"
        with patch.object(catalog_module, "CATALOG_PATH", path):
            save_catalog({"openai": []})
        assert path.parent.exists()
        assert path.exists()


class TestUpdateProviderModels:
    """update_provider_models: load, set provider list, save, return catalog."""

    def test_updates_provider_and_returns_catalog(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps({"openai": ["gpt-4o"], "anthropic": []}))
        with patch.object(catalog_module, "CATALOG_PATH", path):
            result = update_provider_models("openai", ["gpt-4o", "o1"])
        assert result["openai"] == ["gpt-4o", "o1"]
        assert json.loads(path.read_text())["openai"] == ["gpt-4o", "o1"]

    def test_round_trip_filters_on_reload(self, tmp_path):
        """update_provider_models saves raw; reloading applies the project allowlist."""
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps({"openai": [], "anthropic": []}))
        with patch.object(catalog_module, "CATALOG_PATH", path):
            # Save a broad list (raw, unfiltered)
            update_provider_models("openai", ["gpt-4o", "o1", "gpt-5", "o4-mini"])
            # Reload — filter chain should narrow
            reloaded = load_catalog()
        assert set(reloaded["openai"]) == {"gpt-4o", "o4-mini"}

    def test_new_provider_key_added(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps({"openai": []}))
        with patch.object(catalog_module, "CATALOG_PATH", path):
            result = update_provider_models("custom", ["model-a"])
        assert result["custom"] == ["model-a"]
        assert json.loads(path.read_text())["custom"] == ["model-a"]
