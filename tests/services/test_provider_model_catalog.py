"""Unit tests for src.services.provider_model_catalog."""

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

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
        assert "gemini" in out
        # OpenAI: no dated variants
        for m in out["openai"]:
            assert "-2024-" not in m and "-2025-" not in m
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

    def test_new_provider_key_added(self, tmp_path):
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps({"openai": []}))
        with patch.object(catalog_module, "CATALOG_PATH", path):
            result = update_provider_models("custom", ["model-a"])
        assert result["custom"] == ["model-a"]
        assert json.loads(path.read_text())["custom"] == ["model-a"]
