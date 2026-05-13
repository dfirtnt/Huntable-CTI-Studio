"""
Regression test: the Diagnosis agent provider/model selector in settings.html
must render via the shared provider_model_macros.html Jinja2 macro, producing
the same structural contract (IDs, data-attributes, onchange handlers) as the
workflow.html agents.

Covers:
  - Macro renders correct element IDs for diagnosis prefix
  - use_select=true renders <select> dropdowns (not <input>) for cloud providers
  - Cloud selects carry data-catalog-provider attribute for JS population
  - No server-side model lists are injected (catalog population is JS-driven)
  - settings.html imports and calls the macro
  - Stale hardcoded model names not present in settings.html source
  - JS uses onAgentProviderChange (not the old onDiagnosisProviderChange)
  - settings.html JS has populateDiagnosisCloudModelSelects that fetches catalog
"""

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "src" / "web" / "templates"
SETTINGS_TEMPLATE = TEMPLATE_DIR / "settings.html"

# OpenAI models from the old hardcoded list that the project allowlist excludes.
# These must NOT appear hardcoded in settings.html source.
STALE_OPENAI_MODELS = ["gpt-4-turbo", "gpt-4"]
# Anthropic model IDs that were in the old stale hardcoded list and must not reappear.
STALE_ANTHROPIC_MODELS = ["claude-sonnet-4-5"]


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


@pytest.fixture(scope="module")
def rendered_diagnosis(jinja_env) -> str:
    """Render the diagnosis provider_model_grid macro with use_select=true (no server-side models)."""
    tmpl = jinja_env.from_string(
        '{% from "components/provider_model_macros.html" import provider_model_grid %}'
        "{{ provider_model_grid('diagnosis', 'diagnosis_provider', 'diagnosis_model',"
        "    validate=false, use_select=true) }}"
    )
    return tmpl.render()


@pytest.fixture(scope="module")
def settings_raw_text() -> str:
    return SETTINGS_TEMPLATE.read_text()


@pytest.mark.unit
class TestDiagnosisMacroRendering:
    """Rendered macro output must have correct IDs and structure."""

    def test_provider_select_id(self, rendered_diagnosis):
        assert 'id="diagnosis-provider"' in rendered_diagnosis

    def test_lmstudio_model_select_id(self, rendered_diagnosis):
        assert 'id="diagnosis-model"' in rendered_diagnosis

    def test_openai_model_select_id(self, rendered_diagnosis):
        assert 'id="diagnosis-model-openai"' in rendered_diagnosis

    def test_anthropic_model_select_id(self, rendered_diagnosis):
        assert 'id="diagnosis-model-anthropic"' in rendered_diagnosis

    def test_three_provider_branches(self, rendered_diagnosis):
        for provider in ("lmstudio", "openai", "anthropic"):
            needle = f'data-agent-prefix="diagnosis" data-provider="{provider}"'
            assert needle in rendered_diagnosis, f"Missing branch for provider '{provider}'"

    def test_openai_uses_select_not_input(self, rendered_diagnosis):
        """With use_select=true, OpenAI model should be a <select>, not <input>."""
        m = re.search(r'id="diagnosis-model-openai"', rendered_diagnosis)
        assert m
        start = max(0, m.start() - 200)
        context = rendered_diagnosis[start : m.end()]
        assert "<select" in context, "OpenAI model should be a <select> element"
        assert "<input" not in context, "OpenAI model should NOT be an <input> element"

    def test_anthropic_uses_select_not_input(self, rendered_diagnosis):
        """With use_select=true, Anthropic model should be a <select>, not <input>."""
        m = re.search(r'id="diagnosis-model-anthropic"', rendered_diagnosis)
        assert m
        start = max(0, m.start() - 200)
        context = rendered_diagnosis[start : m.end()]
        assert "<select" in context, "Anthropic model should be a <select> element"
        assert "<input" not in context, "Anthropic model should NOT be an <input> element"

    def test_openai_select_has_catalog_provider_attribute(self, rendered_diagnosis):
        """OpenAI select must carry data-catalog-provider so JS can find and populate it."""
        assert 'data-catalog-provider="openai"' in rendered_diagnosis

    def test_anthropic_select_has_catalog_provider_attribute(self, rendered_diagnosis):
        """Anthropic select must carry data-catalog-provider so JS can find and populate it."""
        assert 'data-catalog-provider="anthropic"' in rendered_diagnosis

    def test_openai_select_starts_empty(self, rendered_diagnosis):
        """No server-side <option> elements in the OpenAI select — JS populates from catalog API."""
        m = re.search(r'id="diagnosis-model-openai"[^>]*>(.*?)</select>', rendered_diagnosis, re.DOTALL)
        assert m, "Could not find openai select closing tag"
        assert "<option" not in m.group(1), "OpenAI select should have no server-rendered options"

    def test_anthropic_select_starts_empty(self, rendered_diagnosis):
        """No server-side <option> elements in the Anthropic select — JS populates from catalog API."""
        m = re.search(r'id="diagnosis-model-anthropic"[^>]*>(.*?)</select>', rendered_diagnosis, re.DOTALL)
        assert m, "Could not find anthropic select closing tag"
        assert "<option" not in m.group(1), "Anthropic select should have no server-rendered options"

    def test_onchange_handler(self, rendered_diagnosis):
        assert "onAgentProviderChange('diagnosis')" in rendered_diagnosis


@pytest.mark.unit
class TestSettingsTemplateUsesSharedMacro:
    """settings.html must import and use the shared macro."""

    def test_macro_import_present(self, settings_raw_text):
        assert "provider_model_macros.html" in settings_raw_text

    def test_macro_call_present(self, settings_raw_text):
        assert "provider_model_grid('diagnosis'" in settings_raw_text

    def test_macro_call_uses_use_select_true(self, settings_raw_text):
        """Diagnosis macro call must pass use_select=true so cloud fields render as dropdowns."""
        assert "use_select=true" in settings_raw_text

    def test_no_old_diagnosis_provider_id(self, settings_raw_text):
        """The old camelCase ID must not appear anywhere."""
        assert "diagnosisProvider" not in settings_raw_text, (
            "settings.html still references old 'diagnosisProvider' ID"
        )

    def test_no_old_diagnosis_change_function(self, settings_raw_text):
        """The old standalone function must be replaced."""
        assert "onDiagnosisProviderChange" not in settings_raw_text, (
            "settings.html still references old 'onDiagnosisProviderChange' function"
        )

    def test_uses_shared_onAgentProviderChange(self, settings_raw_text):
        """settings.html must define/use onAgentProviderChange."""
        assert "function onAgentProviderChange" in settings_raw_text

    def test_uses_shared_updateAgentProviderVisibility(self, settings_raw_text):
        """settings.html must define/use updateAgentProviderVisibility."""
        assert "function updateAgentProviderVisibility" in settings_raw_text

    def test_has_catalog_fetch_function(self, settings_raw_text):
        """settings.html must have populateDiagnosisCloudModelSelects for JS-driven catalog population."""
        assert "populateDiagnosisCloudModelSelects" in settings_raw_text

    def test_catalog_fetch_targets_correct_endpoint(self, settings_raw_text):
        """Catalog fetch must use the canonical /api/provider-model-catalog endpoint."""
        assert "provider-model-catalog" in settings_raw_text

    def test_no_hardcoded_stale_openai_models(self, settings_raw_text):
        """Stale OpenAI model values must not be hardcoded in the template."""
        for model in STALE_OPENAI_MODELS:
            assert f"'{model}'" not in settings_raw_text and f'"{model}"' not in settings_raw_text, (
                f"Stale OpenAI model '{model}' is still hardcoded in settings.html"
            )

    def test_no_hardcoded_stale_anthropic_models(self, settings_raw_text):
        """Stale Anthropic model values must not be hardcoded in the template."""
        for model in STALE_ANTHROPIC_MODELS:
            assert f"'{model}'" not in settings_raw_text and f'"{model}"' not in settings_raw_text, (
                f"Stale Anthropic model '{model}' is still hardcoded in settings.html"
            )

    def test_no_server_side_model_lists_in_macro_call(self, settings_raw_text):
        """Macro call must not pass openai_models or anthropic_models — catalog is JS-driven."""
        assert "openai_models=" not in settings_raw_text
        assert "anthropic_models=" not in settings_raw_text
