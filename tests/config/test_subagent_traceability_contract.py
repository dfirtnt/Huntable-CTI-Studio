"""Cross-agent traceability contract tests for extract sub-agents.

Locks in the unified prompt-field schema (source_evidence + extraction_justification
+ confidence_score) across the five extract sub-agents after the
raw_text_snippet -> source_evidence migration.

These are data-contract tests: they read prompt files and preset files and
assert invariants. They do not invoke any LLM, worker, or web code.

Scope distinction:
- ALL extract sub-agents (5) must use the unified field names and must NOT use
  the deprecated raw_text_snippet / confidence_level.
- Three agents (RegistryExtract, ServicesExtract, ProcTreeExtract) were
  migrated to the new template envelope (role / user_template / task /
  json_example / instructions). The remaining two (CmdlineExtract,
  HuntQueriesExtract) are already field-compliant but retain their current
  envelope style; envelope-shape tests target only the migrated set to avoid
  coupling this contract to an unrelated refactor.
- Preset sync is asserted only for agents whose prompt files were regenerated
  in this migration; pre-existing preset/source drift for other agents is not
  in scope here.

Why these tests exist:
- The runtime _traceability_block in src/services/llm_service.py requires every
  extracted item to carry value, source_evidence, extraction_justification, and
  confidence_score. Prompts that name different fields give the model
  contradictory instructions (schema vs. appended block).
- Quickstart presets embed a stringified copy of each prompt file at snapshot
  time. If a prompt is edited without regenerating presets, fresh installs
  diverge from the source-of-truth prompt file.
- raw_text_snippet and confidence_level are legacy names; reintroducing them
  silently breaks downstream UI which only renders source_evidence +
  extraction_justification.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = REPO_ROOT / "src" / "prompts"
PRESET_DIR = REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"
LLM_SERVICE_PATH = REPO_ROOT / "src" / "services" / "llm_service.py"

# All extract sub-agents, with their expected top-level output key.
EXTRACT_AGENTS: list[tuple[str, str]] = [
    ("CmdlineExtract", "cmdline_items"),
    ("ProcTreeExtract", "process_lineage"),
    ("HuntQueriesExtract", "queries"),
    ("RegistryExtract", "registry_artifacts"),
    ("ServicesExtract", "windows_services"),
]
ALL_EXTRACT_NAMES = [a for a, _ in EXTRACT_AGENTS]

# Agents whose prompt files were rewritten in this migration. Envelope-shape
# and preset-sync checks apply only to these.
MIGRATED_EXTRACT_AGENTS: list[str] = [
    "RegistryExtract",
    "ServicesExtract",
    "ProcTreeExtract",
]

# QA prompts that were migrated alongside their extract agents.
MIGRATED_QA_AGENTS: list[str] = ["RegistryQA", "ServicesQA"]

REQUIRED_TRACEABILITY_FIELDS = (
    "source_evidence",
    "extraction_justification",
    "confidence_score",
)

DEPRECATED_FIELDS = ("raw_text_snippet", "confidence_level")


def _load_prompt(agent_name: str) -> dict:
    path = PROMPT_DIR / agent_name
    assert path.exists(), f"Prompt file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _prompt_text(agent_name: str) -> str:
    """Full raw file contents -- used for field-mention checks that should
    succeed regardless of envelope style."""
    return (PROMPT_DIR / agent_name).read_text(encoding="utf-8")


# ===========================================================================
# Prompt JSON validity
# ===========================================================================


class TestPromptJsonValidity:
    """Every subject prompt file parses as valid JSON."""

    @pytest.mark.parametrize("agent_name", ALL_EXTRACT_NAMES + MIGRATED_QA_AGENTS)
    def test_prompt_file_is_valid_json(self, agent_name):
        path = PROMPT_DIR / agent_name
        assert path.exists(), f"Prompt file missing: {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{agent_name} must be a JSON object at root"


# ===========================================================================
# Deprecated field absence -- applies to ALL migrated prompts
# ===========================================================================


class TestNoDeprecatedFields:
    """Legacy field names must not appear in any extract or migrated QA prompt."""

    @pytest.mark.parametrize("agent_name", ALL_EXTRACT_NAMES + MIGRATED_QA_AGENTS)
    @pytest.mark.parametrize("field", DEPRECATED_FIELDS)
    def test_no_deprecated_field(self, agent_name, field):
        text = _prompt_text(agent_name)
        assert field not in text, (
            f"Deprecated field '{field}' found in {agent_name}. "
            f"Use source_evidence + extraction_justification + confidence_score instead."
        )


# ===========================================================================
# Traceability field presence -- applies to ALL extract agents regardless of envelope
# ===========================================================================


class TestTraceabilityFieldPresence:
    """Every extract prompt must reference the three traceability fields somewhere in its content."""

    @pytest.mark.parametrize("agent_name", ALL_EXTRACT_NAMES)
    @pytest.mark.parametrize("field", REQUIRED_TRACEABILITY_FIELDS)
    def test_prompt_mentions_field(self, agent_name, field):
        text = _prompt_text(agent_name)
        assert field in text, (
            f"{agent_name} prompt file does not mention '{field}'. "
            f"Runtime _traceability_block requires this field on every item."
        )


# ===========================================================================
# Envelope uniformity -- applies ONLY to agents migrated in this change set
# ===========================================================================


class TestMigratedExtractPromptEnvelope:
    """Migrated extract prompts use the shared template envelope."""

    ENVELOPE_KEYS = ("role", "user_template", "task", "json_example", "instructions")

    @pytest.mark.parametrize("agent_name", MIGRATED_EXTRACT_AGENTS)
    @pytest.mark.parametrize("key", ENVELOPE_KEYS)
    def test_envelope_key_present(self, agent_name, key):
        data = _load_prompt(agent_name)
        assert key in data, f"{agent_name} missing envelope key '{key}'"
        assert data[key], f"{agent_name} envelope key '{key}' is empty"

    @pytest.mark.parametrize("agent_name", MIGRATED_EXTRACT_AGENTS)
    def test_user_template_has_content_placeholder(self, agent_name):
        data = _load_prompt(agent_name)
        assert "{content}" in data["user_template"], f"{agent_name} user_template missing {{content}} placeholder"

    @pytest.mark.parametrize("agent_name", MIGRATED_EXTRACT_AGENTS)
    def test_user_template_has_instructions_placeholder(self, agent_name):
        data = _load_prompt(agent_name)
        assert "{instructions}" in data["user_template"], (
            f"{agent_name} user_template missing {{instructions}} placeholder"
        )

    @pytest.mark.parametrize("agent_name", MIGRATED_EXTRACT_AGENTS)
    @pytest.mark.parametrize("field", REQUIRED_TRACEABILITY_FIELDS)
    def test_json_example_contains_field(self, agent_name, field):
        """Migrated agents must carry the traceability fields in json_example as well as instructions."""
        data = _load_prompt(agent_name)
        raw = data["json_example"]
        example = json.loads(raw) if isinstance(raw, str) else raw
        assert field in json.dumps(example), f"{agent_name} json_example missing '{field}' in any item"

    @pytest.mark.parametrize("agent_name,top_key", [(a, k) for a, k in EXTRACT_AGENTS if a in MIGRATED_EXTRACT_AGENTS])
    def test_json_example_has_expected_top_level_key(self, agent_name, top_key):
        data = _load_prompt(agent_name)
        raw = data["json_example"]
        example = json.loads(raw) if isinstance(raw, str) else raw
        assert top_key in example, f"{agent_name} json_example missing top-level key '{top_key}'"
        assert "count" in example, f"{agent_name} json_example missing 'count' key"


# ===========================================================================
# QA prompt field references
# ===========================================================================


class TestQAPromptFields:
    """Migrated QA prompts validate against the new traceability field names."""

    @pytest.mark.parametrize("qa_name", MIGRATED_QA_AGENTS)
    def test_qa_validation_references_source_evidence(self, qa_name):
        data = _load_prompt(qa_name)
        criteria_blob = json.dumps(data.get("evaluation_criteria", []))
        assert "source_evidence" in criteria_blob, f"{qa_name} evaluation_criteria must reference source_evidence"

    @pytest.mark.parametrize("qa_name", MIGRATED_QA_AGENTS)
    def test_qa_validation_references_extraction_justification(self, qa_name):
        data = _load_prompt(qa_name)
        criteria_blob = json.dumps(data.get("evaluation_criteria", []))
        assert "extraction_justification" in criteria_blob, (
            f"{qa_name} evaluation_criteria must reference extraction_justification"
        )

    @pytest.mark.parametrize("qa_name", MIGRATED_QA_AGENTS)
    def test_qa_has_no_deprecated_fields(self, qa_name):
        text = _prompt_text(qa_name)
        for field in DEPRECATED_FIELDS:
            assert field not in text, f"Deprecated field '{field}' reintroduced in {qa_name}."


# ===========================================================================
# Preset / prompt-file sync -- only for agents regenerated in this migration
# ===========================================================================


class TestPresetsSyncedWithPrompts:
    """Quickstart presets embed a stringified copy of each extract prompt. That
    copy must match the source file for the agents whose prompts were rewritten."""

    @pytest.fixture(scope="class")
    def preset_paths(self) -> list[Path]:
        if not PRESET_DIR.exists():
            pytest.skip("Quickstart preset directory not present")
        presets = sorted(PRESET_DIR.glob("*.json"))
        if not presets:
            pytest.skip("No Quickstart preset files found")
        return presets

    @pytest.mark.parametrize("agent_name", MIGRATED_EXTRACT_AGENTS)
    def test_preset_prompt_has_no_deprecated_fields(self, agent_name, preset_paths):
        for preset_path in preset_paths:
            preset = json.loads(preset_path.read_text(encoding="utf-8"))
            agent_entry = preset.get(agent_name)
            assert agent_entry, f"{agent_name} missing from {preset_path.name}"
            prompt_str = agent_entry.get("Prompt", {}).get("prompt", "")
            for field in DEPRECATED_FIELDS:
                assert field not in prompt_str, (
                    f"Deprecated '{field}' in {preset_path.name} -> {agent_name}.Prompt.prompt. "
                    f"Re-run preset regeneration."
                )

    @pytest.mark.parametrize("agent_name", MIGRATED_EXTRACT_AGENTS)
    def test_preset_prompt_parses_and_matches_source(self, agent_name, preset_paths):
        source = _load_prompt(agent_name)
        for preset_path in preset_paths:
            preset = json.loads(preset_path.read_text(encoding="utf-8"))
            agent_entry = preset.get(agent_name, {})
            prompt_str = agent_entry.get("Prompt", {}).get("prompt", "")
            assert prompt_str, f"{agent_name}.Prompt.prompt missing in {preset_path.name}"
            embedded = json.loads(prompt_str)
            assert embedded == source, (
                f"{preset_path.name} -> {agent_name}.Prompt.prompt drifted from src/prompts/{agent_name}. "
                f"Re-run preset regeneration."
            )

    @pytest.mark.parametrize("qa_name", MIGRATED_QA_AGENTS)
    def test_preset_qa_prompt_synced(self, qa_name, preset_paths):
        """QA prompts embed as <BaseAgent>.QAPrompt.prompt."""
        base_for_qa = {"RegistryQA": "RegistryExtract", "ServicesQA": "ServicesExtract"}
        base_agent = base_for_qa[qa_name]
        source = _load_prompt(qa_name)
        for preset_path in preset_paths:
            preset = json.loads(preset_path.read_text(encoding="utf-8"))
            qa_entry = preset.get(base_agent, {}).get("QAPrompt", {})
            prompt_str = qa_entry.get("prompt", "")
            assert prompt_str, f"{base_agent}.QAPrompt.prompt missing in {preset_path.name}"
            embedded = json.loads(prompt_str)
            assert embedded == source, (
                f"{preset_path.name} -> {base_agent}.QAPrompt.prompt drifted from src/prompts/{qa_name}."
            )


# ===========================================================================
# Runtime contract match
# ===========================================================================


class TestRuntimeContractMatch:
    """The runtime _traceability_block in llm_service.py enforces the same fields the prompts promise.

    If someone edits prompts to use different field names without updating the block
    (or vice versa), models get contradictory instructions. These tests catch that drift.
    """

    def test_traceability_block_requires_contract_fields(self):
        src = LLM_SERVICE_PATH.read_text(encoding="utf-8")
        assert "TRACEABILITY (REQUIRED)" in src, (
            "llm_service.py no longer contains the TRACEABILITY block. If this was intentional, "
            "remove this test and document why prompts are now self-sufficient."
        )
        for field in REQUIRED_TRACEABILITY_FIELDS:
            assert field in src, f"Runtime _traceability_block must still reference '{field}' to match prompt schemas."
        assert '"value" field' in src, (
            "Runtime _traceability_block must require a 'value' field on each extracted item."
        )

    def test_traceability_block_agent_list_matches_extract_agents(self):
        """Every sub-agent in EXTRACT_AGENTS must appear in llm_service.py so the traceability block is appended."""
        src = LLM_SERVICE_PATH.read_text(encoding="utf-8")
        for agent_name in ALL_EXTRACT_NAMES:
            assert f'"{agent_name}"' in src, (
                f"{agent_name} must appear in llm_service.py so the traceability block is appended to its prompt."
            )

    def test_traceability_block_includes_sigextract(self):
        """SigExtract keeps parity with the other extract agents for traceability fields."""
        src = LLM_SERVICE_PATH.read_text(encoding="utf-8")
        assert '"SigExtract"' in src, "SigExtract must remain in the traceability block allowlist."
