"""
Regression test: the Diagnosis agent provider/model selector in settings.html
must render via the shared provider_model_macros.html Jinja2 macro, producing
the same structural contract (IDs, data-attributes, onchange handlers) as the
workflow.html agents.

Covers:
  - Macro renders correct element IDs for diagnosis prefix
  - use_select=true renders <select> dropdowns for cloud providers
  - Cloud model options match the curated lists
  - settings.html imports and calls the macro
  - JS uses onAgentProviderChange (not the old onDiagnosisProviderChange)
"""

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "src" / "web" / "templates"
SETTINGS_TEMPLATE = TEMPLATE_DIR / "settings.html"

OPENAI_MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4"]
ANTHROPIC_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5",
]


@pytest.fixture(scope="module")
def jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


@pytest.fixture(scope="module")
def rendered_diagnosis(jinja_env) -> str:
    """Render the diagnosis provider_model_grid macro with use_select=true."""
    tmpl = jinja_env.from_string(
        '{% from "components/provider_model_macros.html" import provider_model_grid %}'
        "{{ provider_model_grid('diagnosis', 'diagnosis_provider', 'diagnosis_model',"
        "    validate=false, use_select=true,"
        "    openai_models=openai_models,"
        "    anthropic_models=anthropic_models) }}"
    )
    return tmpl.render(
        openai_models=[{"value": m, "label": m} for m in OPENAI_MODELS],
        anthropic_models=[{"value": m, "label": m} for m in ANTHROPIC_MODELS],
    )


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
        # Find the openai model element
        m = re.search(r'id="diagnosis-model-openai"', rendered_diagnosis)
        assert m
        # The element before the id should be a <select, not <input
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

    @pytest.mark.parametrize("model", OPENAI_MODELS)
    def test_openai_model_option_present(self, rendered_diagnosis, model):
        assert f'value="{model}"' in rendered_diagnosis, f"Missing OpenAI model option: {model}"

    @pytest.mark.parametrize("model", ANTHROPIC_MODELS)
    def test_anthropic_model_option_present(self, rendered_diagnosis, model):
        assert f'value="{model}"' in rendered_diagnosis, f"Missing Anthropic model option: {model}"

    def test_onchange_handler(self, rendered_diagnosis):
        assert "onAgentProviderChange('diagnosis')" in rendered_diagnosis


@pytest.mark.unit
class TestSettingsTemplateUsesSharedMacro:
    """settings.html must import and use the shared macro."""

    def test_macro_import_present(self, settings_raw_text):
        assert "provider_model_macros.html" in settings_raw_text

    def test_macro_call_present(self, settings_raw_text):
        assert "provider_model_grid('diagnosis'" in settings_raw_text

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
