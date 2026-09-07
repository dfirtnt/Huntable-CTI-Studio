"""Catalog-driven model capability resolution.

config/model_capabilities.json is the source of truth for which request parameters a
model accepts (temperature, top_p) and which reasoning-effort tiers it lists. The
name-prefix heuristics that used to be authoritative survive only as the fallback for
ids the file does not know. These tests pin that precedence and the file's shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.workflow_config_schema import VALID_EFFORT_LEVELS
from src.services import provider_model_catalog as catalog_module
from src.services.provider_model_catalog import (
    CAPABILITIES_PATH,
    CATALOG_PATH,
    ModelCapabilities,
    find_unclassified_models,
    get_model_capabilities,
    load_model_capabilities,
)
from src.utils.model_validation import heuristic_supports_variable_temperature, model_supports_variable_temperature

pytestmark = pytest.mark.unit


@pytest.fixture
def capabilities_file(tmp_path):
    """Point the resolver at a scratch capabilities file and reset its mtime cache."""

    def _write(models: dict) -> Path:
        path = tmp_path / "model_capabilities.json"
        path.write_text(json.dumps({"version": 1, "models": models}))
        catalog_module._capabilities_cache = None
        return path

    return _write


@pytest.fixture(autouse=True)
def _reset_cache():
    catalog_module._capabilities_cache = None
    yield
    catalog_module._capabilities_cache = None


class TestGetModelCapabilities:
    def test_catalog_entry_wins_over_prefix_heuristic(self, capabilities_file):
        # gpt-4o-fake would be "sampling supported" by prefix; the file says otherwise.
        path = capabilities_file(
            {
                "gpt-4o-fake": {
                    "supports_temperature": False,
                    "supports_top_p": False,
                    "effort_levels": ["low", "high"],
                    "default_effort": "low",
                }
            }
        )
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            caps = get_model_capabilities("openai", "gpt-4o-fake")
        assert caps == ModelCapabilities(False, False, ("low", "high"), "low", "catalog")

    def test_unknown_openai_reasoning_prefix_falls_back_to_heuristic(self, capabilities_file):
        path = capabilities_file({})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            caps = get_model_capabilities("openai", "o3-unreleased-preview")
        assert caps.source == "fallback"
        assert caps.supports_temperature is False
        assert caps.supports_top_p is False
        assert caps.effort_levels == ()
        assert caps.default_effort is None

    def test_unknown_sampling_model_falls_back_to_supported(self, capabilities_file):
        path = capabilities_file({})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            assert get_model_capabilities("openai", "gpt-4-turbo-unlisted").supports_temperature is True
            assert get_model_capabilities("anthropic", "claude-unlisted").supports_temperature is True
            assert get_model_capabilities("lmstudio", "qwen/qwen3-4b").supports_temperature is True

    def test_unknown_model_never_raises_and_has_no_effort_levels(self, capabilities_file):
        path = capabilities_file({})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            for provider, model in (("openai", "gpt-9"), ("anthropic", ""), (None, None), ("", "x")):
                caps = get_model_capabilities(provider, model)
                assert caps.effort_levels == ()
                assert caps.source == "fallback"

    def test_codex_is_always_live(self, capabilities_file):
        # Even if someone adds a codex-served id to the file, the adapter never sends
        # sampling parameters and its tiers come from model/list.
        path = capabilities_file({"gpt-5.6-luna": {"supports_temperature": True, "effort_levels": ["low"]}})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            caps = get_model_capabilities("codex", "gpt-5.6-luna")
        assert caps.source == "live"
        assert caps.supports_temperature is False
        assert caps.supports_top_p is False
        assert caps.effort_levels == ()

    def test_missing_file_degrades_to_fallback(self, tmp_path):
        with patch.object(catalog_module, "CAPABILITIES_PATH", tmp_path / "absent.json"):
            assert load_model_capabilities() == {}
            assert get_model_capabilities("anthropic", "claude-opus-5").source == "fallback"

    def test_corrupt_file_degrades_to_fallback(self, tmp_path):
        path = tmp_path / "model_capabilities.json"
        path.write_text("{ not json")
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            assert load_model_capabilities() == {}
            assert get_model_capabilities("openai", "gpt-5.6-luna").source == "fallback"

    def test_cache_refreshes_when_file_changes(self, capabilities_file):
        path = capabilities_file({"m": {"supports_temperature": True, "effort_levels": []}})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            assert get_model_capabilities("openai", "m").supports_temperature is True
            path.write_text(json.dumps({"models": {"m": {"supports_temperature": False, "effort_levels": []}}}))
            import os

            stat = path.stat()
            os.utime(path, (stat.st_atime, stat.st_mtime + 5))
            assert get_model_capabilities("openai", "m").supports_temperature is False

    def test_to_dict_shape(self):
        caps = ModelCapabilities(True, False, ("low",), "low", "catalog")
        assert caps.to_dict() == {
            "supports_temperature": True,
            "supports_top_p": False,
            "effort_levels": ["low"],
            "default_effort": "low",
            "source": "catalog",
        }


class TestModelSupportsVariableTemperatureDelegates:
    """model_supports_variable_temperature() keeps its signature but reads the catalog."""

    def test_anthropic_model_that_rejects_sampling_is_reported_false(self):
        # Prefix heuristics know nothing about Claude; only the catalog can say this.
        assert heuristic_supports_variable_temperature("claude-opus-5") is True
        assert model_supports_variable_temperature("claude-opus-5") is False

    def test_sampling_models_stay_true(self):
        for model in ("gpt-4o", "gpt-4.1-mini", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"):
            assert model_supports_variable_temperature(model) is True, model

    def test_openai_reasoning_models_stay_false(self):
        for model in ("gpt-5", "gpt-5.6-luna", "o3", "o4-mini"):
            assert model_supports_variable_temperature(model) is False, model

    def test_unknown_id_uses_prefix_heuristic(self, capabilities_file):
        path = capabilities_file({})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            assert model_supports_variable_temperature("gpt-5.9-unreleased") is False
            assert model_supports_variable_temperature("gpt-4-unreleased") is True
            assert model_supports_variable_temperature("") is True


class TestCommittedCapabilitiesFile:
    """The on-disk file must cover the on-disk catalog and follow the documented shape."""

    def _models(self) -> dict:
        data = json.loads(CAPABILITIES_PATH.read_text())
        assert data.get("version") == 1
        assert isinstance(data.get("verified_at"), str)
        assert isinstance(data.get("models"), dict) and data["models"]
        return data["models"]

    def test_every_catalog_model_is_classified(self):
        catalog = json.loads(CATALOG_PATH.read_text())
        assert find_unclassified_models(catalog) == {}

    def test_entries_have_documented_shape(self):
        for model, entry in self._models().items():
            assert set(entry) >= {"supports_temperature", "supports_top_p", "effort_levels", "default_effort"}, model
            assert set(entry) <= {"supports_temperature", "supports_top_p", "effort_levels", "default_effort", "note"}
            assert isinstance(entry["supports_temperature"], bool), model
            assert isinstance(entry["supports_top_p"], bool), model
            assert isinstance(entry["effort_levels"], list), model
            for level in entry["effort_levels"]:
                assert level in VALID_EFFORT_LEVELS, (model, level)
            assert len(entry["effort_levels"]) == len(set(entry["effort_levels"])), model
            default = entry["default_effort"]
            assert default is None or default in entry["effort_levels"], (model, default)

    def test_verified_provider_facts(self):
        """Pin the values verified against provider docs on 2026-09-04."""
        models = self._models()
        assert models["gpt-5.6-luna"]["effort_levels"] == ["none", "low", "medium", "high", "xhigh", "max"]
        assert models["gpt-5.6-luna"]["default_effort"] == "medium"
        assert models["gpt-5.1"]["default_effort"] == "none"
        assert models["gpt-4.1"]["effort_levels"] == [] and models["gpt-4.1"]["supports_temperature"] is True
        assert models["claude-opus-4-7"]["supports_temperature"] is False
        assert "xhigh" in models["claude-opus-4-7"]["effort_levels"]
        assert models["claude-sonnet-4-6"]["supports_temperature"] is True
        assert "xhigh" not in models["claude-sonnet-4-6"]["effort_levels"]
        assert models["claude-haiku-4-5-20251001"]["effort_levels"] == []


class TestFindUnclassifiedModels:
    def test_reports_gaps_per_provider_and_skips_codex(self, capabilities_file):
        path = capabilities_file({"gpt-4o": {"supports_temperature": True, "effort_levels": []}})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            gaps = find_unclassified_models(
                {"openai": ["gpt-4o", "gpt-9", "gpt-8"], "anthropic": ["claude-x"], "codex": ["gpt-9"]}
            )
        assert gaps == {"openai": ["gpt-8", "gpt-9"], "anthropic": ["claude-x"]}

    def test_fully_classified_catalog_reports_nothing(self, capabilities_file):
        path = capabilities_file({"gpt-4o": {"supports_temperature": True, "effort_levels": []}})
        with patch.object(catalog_module, "CAPABILITIES_PATH", path):
            assert find_unclassified_models({"openai": ["gpt-4o"], "anthropic": []}) == {}
