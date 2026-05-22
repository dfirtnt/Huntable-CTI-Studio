"""
Regression test: all cloud model pickers must use the same UI code (shared
macro) and draw models from the same catalog (config/provider_model_catalog.json
processed through load_catalog()).

Covers:
  - Catalog file structure: valid JSON, both providers present and non-empty
  - No duplicate model IDs within a provider in the raw catalog file
  - load_catalog() filter pipeline produces non-empty results for both providers
  - load_catalog() result has no duplicate model IDs
  - No stale deprecated model IDs survive the filter pipeline
  - No hardcoded <option value="gpt-..."> or <option value="claude-..."> in
    any page template (model lists must come from the catalog API, not server HTML)
  - Every template that calls provider_model_grid imports provider_model_macros.html
    (no inline bespoke provider picker HTML)
  - workflow.html cloud model inputs are all text fields (use_select omitted/false),
    not dropdowns, consistent with LMStudio-only select behavior in the macro
  - settings.html diagnosis picker uses use_select=true (catalog-driven dropdowns)
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "config" / "provider_model_catalog.json"
TEMPLATE_DIR = REPO_ROOT / "src" / "web" / "templates"

# All page templates that could contain a model picker.
PAGE_TEMPLATES = list(TEMPLATE_DIR.glob("*.html"))

# Templates known to import + call provider_model_grid.
MACRO_USING_TEMPLATES = {
    "workflow.html",
    "settings.html",
}

# Model IDs that were previously hardcoded and must not return.
BANNED_HARDCODED_MODELS = [
    "gpt-4-turbo",
    "gpt-4",
    "claude-sonnet-4-5",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
]

# ─── Catalog file integrity ───────────────────────────────────────────────────


@pytest.mark.unit
class TestCatalogFileIntegrity:
    """The raw provider_model_catalog.json must be structurally sound."""

    @pytest.fixture(scope="class")
    def raw_catalog(self) -> dict:
        assert CATALOG_PATH.exists(), f"Catalog file missing: {CATALOG_PATH}"
        return json.loads(CATALOG_PATH.read_text())

    def test_catalog_has_openai_key(self, raw_catalog):
        assert "openai" in raw_catalog, "Catalog must contain 'openai' key"

    def test_catalog_has_anthropic_key(self, raw_catalog):
        assert "anthropic" in raw_catalog, "Catalog must contain 'anthropic' key"

    def test_openai_list_non_empty(self, raw_catalog):
        assert raw_catalog["openai"], "Catalog openai list must not be empty"

    def test_anthropic_list_non_empty(self, raw_catalog):
        assert raw_catalog["anthropic"], "Catalog anthropic list must not be empty"

    def test_no_duplicate_openai_models(self, raw_catalog):
        models = raw_catalog["openai"]
        dupes = [m for m in models if models.count(m) > 1]
        assert not dupes, f"Duplicate OpenAI model IDs in catalog: {sorted(set(dupes))}"

    def test_no_duplicate_anthropic_models(self, raw_catalog):
        models = raw_catalog["anthropic"]
        dupes = [m for m in models if models.count(m) > 1]
        assert not dupes, f"Duplicate Anthropic model IDs in catalog: {sorted(set(dupes))}"

    def test_all_entries_are_strings(self, raw_catalog):
        for provider in ("openai", "anthropic"):
            for entry in raw_catalog.get(provider, []):
                assert isinstance(entry, str) and entry.strip(), (
                    f"Non-string or blank model ID in catalog['{provider}']: {entry!r}"
                )


# ─── load_catalog() filter pipeline ──────────────────────────────────────────


@pytest.mark.unit
class TestLoadCatalogFilterPipeline:
    """
    load_catalog() applies Anthropic-family dedup and OpenAI-allowlist filters.
    Both providers must survive the pipeline with usable models.
    """

    @pytest.fixture(scope="class")
    def loaded(self) -> dict:
        from src.services.provider_model_catalog import load_catalog

        return load_catalog()

    def test_openai_non_empty_after_filters(self, loaded):
        assert loaded.get("openai"), (
            "load_catalog() filtered out ALL OpenAI models -- allowlist or filter is too aggressive"
        )

    def test_anthropic_non_empty_after_filters(self, loaded):
        assert loaded.get("anthropic"), (
            "load_catalog() filtered out ALL Anthropic models -- family-dedup filter is too aggressive"
        )

    def test_no_duplicate_openai_after_filters(self, loaded):
        models = loaded.get("openai", [])
        dupes = [m for m in models if models.count(m) > 1]
        assert not dupes, f"load_catalog() produced duplicate OpenAI IDs: {sorted(set(dupes))}"

    def test_no_duplicate_anthropic_after_filters(self, loaded):
        models = loaded.get("anthropic", [])
        dupes = [m for m in models if models.count(m) > 1]
        assert not dupes, f"load_catalog() produced duplicate Anthropic IDs: {sorted(set(dupes))}"

    def test_all_entries_are_non_blank_strings(self, loaded):
        for provider in ("openai", "anthropic"):
            for m in loaded.get(provider, []):
                assert isinstance(m, str) and m.strip(), (
                    f"Blank or non-string model in loaded catalog['{provider}']: {m!r}"
                )

    @pytest.mark.parametrize("banned", BANNED_HARDCODED_MODELS)
    def test_banned_stale_model_not_in_filtered_catalog(self, loaded, banned):
        all_models = loaded.get("openai", []) + loaded.get("anthropic", [])
        assert banned not in all_models, (
            f"Stale deprecated model '{banned}' survived the load_catalog() filter pipeline"
        )


# ─── No hardcoded model <option> in agent_models[] selects ───────────────────

# Matches a <select ... name="agent_models[...]" ...> block including its content.
_AGENT_MODEL_SELECT_BLOCK = re.compile(
    r'(<select\b[^>]*name=["\']agent_models\[[^\]]*\]["\'][^>]*>)(.*?)</select>',
    re.IGNORECASE | re.DOTALL,
)
# Within such a block, a hardcoded cloud-model <option value>.
_CLOUD_MODEL_OPTION = re.compile(
    r'<option\b[^>]*value=["\'](?:gpt-|claude-|o\d-)[^"\']*["\']',
    re.IGNORECASE,
)


@pytest.mark.unit
class TestNoHardcodedModelOptions:
    """
    agent_models[] selects must not contain hardcoded cloud model <option> values
    server-side.  Model lists must come from the /api/provider-model-catalog
    endpoint via JS.  Non-agent selects (e.g. sigma validate modal) are excluded.
    """

    @pytest.mark.parametrize("tmpl_path", PAGE_TEMPLATES, ids=lambda p: p.name)
    def test_no_hardcoded_model_option_in_agent_selects(self, tmpl_path):
        src = tmpl_path.read_text()
        violations = []
        for m in _AGENT_MODEL_SELECT_BLOCK.finditer(src):
            inner = m.group(2)
            cloud_options = _CLOUD_MODEL_OPTION.findall(inner)
            if cloud_options:
                violations.append((m.group(1)[:80], cloud_options[:3]))
        assert not violations, (
            f"{tmpl_path.name} has hardcoded cloud model <option> elements inside "
            f"agent_models[] selects -- model lists must come from the catalog API: "
            f"{violations}"
        )


# ─── All picker templates use the shared macro ───────────────────────────────


@pytest.mark.unit
class TestAllPickersUseSharedMacro:
    """
    Any template that calls provider_model_grid must import it from the shared
    macro file.  This prevents a future template from reimplementing the picker
    inline and drifting out of sync.
    """

    @pytest.mark.parametrize("tmpl_name", sorted(MACRO_USING_TEMPLATES))
    def test_macro_import_present(self, tmpl_name):
        src = (TEMPLATE_DIR / tmpl_name).read_text()
        assert "provider_model_macros.html" in src, (
            f"{tmpl_name} calls provider_model_grid but does not import components/provider_model_macros.html"
        )

    @pytest.mark.parametrize("tmpl_name", sorted(MACRO_USING_TEMPLATES))
    def test_macro_call_present(self, tmpl_name):
        src = (TEMPLATE_DIR / tmpl_name).read_text()
        assert "provider_model_grid(" in src, (
            f"{tmpl_name} imports provider_model_macros.html but never calls provider_model_grid()"
        )

    def test_no_rogue_inline_provider_select(self):
        """
        No page template outside the known macro-using set should contain a
        bare <select> with name matching the agent_models[] pattern for providers.
        This catches a new template that reimplements the picker without the macro.
        """
        agent_model_select = re.compile(r'<select[^>]+name=["\']agent_models\[[^\]]*_provider\]["\']', re.IGNORECASE)
        violations = []
        for tmpl_path in PAGE_TEMPLATES:
            if tmpl_path.name in MACRO_USING_TEMPLATES:
                continue
            src = tmpl_path.read_text()
            if agent_model_select.search(src):
                violations.append(tmpl_path.name)
        assert not violations, (
            f"Templates with inline agent_models provider selects (not using shared macro): "
            f"{violations} -- add them to MACRO_USING_TEMPLATES or refactor to use the macro"
        )


# ─── workflow.html cloud inputs are text fields (not dropdowns) ───────────────


@pytest.mark.unit
class TestWorkflowCloudInputType:
    """
    workflow.html agents use the macro without use_select, so cloud provider
    model fields render as <input type='text'>, not <select>.  The JS populates
    them from LM Studio; cloud models are typed by the user.

    This is intentional and different from settings.html diagnosis (use_select=true).
    Guard the distinction so a future edit doesn't silently flip it.
    """

    @pytest.fixture(scope="class")
    def workflow_src(self) -> str:
        return (TEMPLATE_DIR / "workflow.html").read_text()

    def test_workflow_does_not_pass_use_select_true(self, workflow_src):
        """None of the workflow.html macro calls should pass use_select=true."""
        # Find every provider_model_grid call and check none has use_select=true.
        calls = re.findall(r"provider_model_grid\([^)]+\)", workflow_src, re.DOTALL)
        for call in calls:
            assert "use_select=true" not in call, (
                f"workflow.html macro call passes use_select=true -- "
                f"workflow cloud pickers should be text inputs, not dropdowns: {call[:120]}"
            )

    def test_settings_diagnosis_uses_select_true(self):
        """settings.html diagnosis call must explicitly pass use_select=true."""
        src = (TEMPLATE_DIR / "settings.html").read_text()
        assert "provider_model_grid('diagnosis'" in src
        # Extract the diagnosis call and verify use_select=true is present.
        m = re.search(r"provider_model_grid\('diagnosis'[^)]+\)", src, re.DOTALL)
        assert m, "Could not locate provider_model_grid('diagnosis'...) call in settings.html"
        assert "use_select=true" in m.group(0), (
            "settings.html diagnosis picker must pass use_select=true so cloud fields "
            "render as catalog-driven dropdowns, not free-text inputs"
        )
