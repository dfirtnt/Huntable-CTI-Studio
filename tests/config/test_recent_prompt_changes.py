"""Contract tests for prompt and preset changes from the current dev session.

Covers gaps not already locked in by test_subagent_traceability_contract.py:

A. QAAgentCMD seed compliance
   - Valid JSON
   - Non-empty 'instructions' key (was missing before this session)
   - 'evaluation_criteria' is a non-empty list
   - ASCII-only content (no Unicode emoji)
   - Passes _validate_qa_prompt_config end-to-end

B. Quickstart preset compliance (all three presets)
   - RankAgent.QAEnabled == false
   - HuntQueriesExtract.Prompt.prompt parses as JSON with
     standard keys: role, task, json_example, instructions

C. Qwen3-specific QA prompt compliance
   - HuntQueriesExtract.QAPrompt.prompt has non-empty evaluation_criteria list
   - ProcTreeExtract.QAPrompt.prompt has non-empty evaluation_criteria list

D. Seed contract keys for newly rewritten agents
   - HuntQueriesExtract seed has standard 4 envelope keys
   - ExtractAgent seed has standard 4 envelope keys
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = REPO_ROOT / "src" / "prompts"
PRESET_DIR = REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"

QUICKSTART_PRESETS = [
    "Quickstart-LMStudio-Qwen3.json",
    "Quickstart-anthropic-sonnet-4-6.json",
    "Quickstart-openai-gpt-4.1-mini.json",
]

STANDARD_ENVELOPE_KEYS = ("role", "task", "json_example", "instructions")


# ===========================================================================
# Helpers
# ===========================================================================


def _load_prompt(name: str) -> dict:
    path = PROMPT_DIR / name
    assert path.exists(), f"Prompt file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_preset(filename: str) -> dict:
    path = PRESET_DIR / filename
    assert path.exists(), f"Preset file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _is_ascii_only(text: str) -> bool:
    """Return True if every character in text is within the ASCII range."""
    return all(ord(c) < 128 for c in text)


# ===========================================================================
# A. QAAgentCMD seed compliance
# ===========================================================================


class TestQAAgentCMDSeed:
    """Lock in the QAAgentCMD seed (loaded as QAAgent) structural requirements."""

    @pytest.fixture(scope="class")
    def seed(self) -> dict:
        return _load_prompt("QAAgentCMD")

    def test_is_valid_json(self):
        """QAAgentCMD must parse as a JSON object at root."""
        data = _load_prompt("QAAgentCMD")
        assert isinstance(data, dict)

    def test_has_nonempty_instructions(self, seed):
        """'instructions' key added this session; must be present and non-empty."""
        assert "instructions" in seed, "QAAgentCMD missing 'instructions' key"
        assert seed["instructions"].strip(), "QAAgentCMD 'instructions' is empty"

    def test_evaluation_criteria_is_nonempty_list(self, seed):
        """evaluation_criteria must be a non-empty list -- required by _validate_qa_prompt_config."""
        criteria = seed.get("evaluation_criteria")
        assert isinstance(criteria, list), (
            f"QAAgentCMD 'evaluation_criteria' must be a list, got {type(criteria).__name__}"
        )
        assert len(criteria) > 0, "QAAgentCMD 'evaluation_criteria' is an empty list"

    def test_has_role_key(self, seed):
        """QAAgent needs a system/role for _validate_qa_prompt_config to pass."""
        has_role = bool((seed.get("role") or seed.get("system") or "").strip())
        assert has_role, "QAAgentCMD missing non-empty 'role' or 'system' key"

    def test_ascii_only_no_emoji(self):
        """No Unicode emoji or non-ASCII characters -- project ASCII-only rule."""
        raw = (PROMPT_DIR / "QAAgentCMD").read_text(encoding="utf-8")
        assert _is_ascii_only(raw), (
            "QAAgentCMD contains non-ASCII characters. "
            "Replace emoji/Unicode with ASCII equivalents ([PASS]/[WARN]/[FAIL])."
        )

    def test_passes_validate_qa_prompt_config(self, seed):
        """_validate_qa_prompt_config must not raise with the live seed."""
        from src.services.llm_service import _validate_qa_prompt_config

        # Should not raise
        _validate_qa_prompt_config("QAAgent", seed)


# ===========================================================================
# B. Quickstart preset compliance -- all three presets
# ===========================================================================


class TestQuickstartPresetCompliance:
    """All three quickstart presets must satisfy baseline structural invariants."""

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    def test_rank_agent_qa_disabled(self, preset_file):
        """RankAgent.QAEnabled must be false in every quickstart preset."""
        preset = _load_preset(preset_file)
        rank = preset.get("RankAgent", {})
        assert "QAEnabled" in rank, f"{preset_file}: RankAgent missing QAEnabled key"
        assert rank["QAEnabled"] is False, (
            f"{preset_file}: RankAgent.QAEnabled must be false, got {rank['QAEnabled']!r}"
        )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    def test_hunt_queries_prompt_has_standard_envelope(self, preset_file):
        """HuntQueriesExtract.Prompt.prompt must parse as JSON with standard 4 keys."""
        preset = _load_preset(preset_file)
        hunt = preset.get("HuntQueriesExtract", {})
        assert hunt, f"{preset_file}: HuntQueriesExtract section missing"

        prompt_str = hunt.get("Prompt", {}).get("prompt", "")
        assert prompt_str, f"{preset_file}: HuntQueriesExtract.Prompt.prompt is empty"

        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{preset_file}: HuntQueriesExtract.Prompt.prompt is not valid JSON: {exc}")

        for key in STANDARD_ENVELOPE_KEYS:
            assert key in prompt_data, (
                f"{preset_file}: HuntQueriesExtract.Prompt.prompt missing key '{key}'. "
                f"Found keys: {list(prompt_data.keys())}"
            )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    def test_hunt_queries_prompt_no_old_keys(self, preset_file):
        """Rewritten prompt must NOT use the old envelope keys (objective/exclusions/output_format)."""
        preset = _load_preset(preset_file)
        prompt_str = preset.get("HuntQueriesExtract", {}).get("Prompt", {}).get("prompt", "")
        if not prompt_str:
            pytest.skip(f"{preset_file}: no HuntQueriesExtract prompt to inspect")
        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError:
            pytest.skip(f"{preset_file}: prompt not valid JSON")

        old_keys = ("objective", "exclusions", "output_format")
        for key in old_keys:
            assert key not in prompt_data, (
                f"{preset_file}: HuntQueriesExtract.Prompt.prompt still contains old key '{key}'. "
                "Rewrite to standard envelope (role/task/json_example/instructions)."
            )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    def test_extract_agent_prompt_has_standard_envelope(self, preset_file):
        """ExtractAgent.Prompt.prompt must parse as JSON with standard 4 keys."""
        preset = _load_preset(preset_file)
        prompt_str = preset.get("ExtractAgent", {}).get("Prompt", {}).get("prompt", "")
        assert prompt_str, f"{preset_file}: ExtractAgent.Prompt.prompt is empty"

        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{preset_file}: ExtractAgent.Prompt.prompt is not valid JSON: {exc}")

        for key in STANDARD_ENVELOPE_KEYS:
            assert key in prompt_data, (
                f"{preset_file}: ExtractAgent.Prompt.prompt missing key '{key}'. Found keys: {list(prompt_data.keys())}"
            )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    def test_extract_agent_prompt_no_user_turn_content(self, preset_file):
        """ExtractAgent.Prompt.prompt must not contain user-turn template content.

        The user message scaffold is code-owned in llm_service._EXTRACT_BEHAVIORS_TEMPLATE.
        It must not be baked into the preset system prompt.
        """
        preset = _load_preset(preset_file)
        prompt_str = preset.get("ExtractAgent", {}).get("Prompt", {}).get("prompt", "")
        if not prompt_str:
            pytest.skip(f"{preset_file}: no ExtractAgent prompt to inspect")

        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError:
            pytest.skip(f"{preset_file}: prompt not valid JSON")

        instructions = prompt_data.get("instructions", "")
        forbidden = ("USER: Title:", "{title}", "{url}", "{content}")
        for token in forbidden:
            assert token not in instructions, (
                f"{preset_file}: ExtractAgent.Prompt.prompt.instructions contains "
                f"user-turn content '{token}'. User scaffold is code-owned in "
                "_EXTRACT_BEHAVIORS_TEMPLATE -- remove it from the preset."
            )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    def test_extract_agent_prompt_no_old_keys(self, preset_file):
        """ExtractAgent.Prompt.prompt must not use pre-migration envelope keys."""
        preset = _load_preset(preset_file)
        prompt_str = preset.get("ExtractAgent", {}).get("Prompt", {}).get("prompt", "")
        if not prompt_str:
            pytest.skip(f"{preset_file}: no ExtractAgent prompt to inspect")
        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError:
            pytest.skip(f"{preset_file}: prompt not valid JSON")

        old_keys = ("objective", "exclusions", "output_format", "platform_coverage", "constraints", "output_schema")
        for key in old_keys:
            assert key not in prompt_data, (
                f"{preset_file}: ExtractAgent.Prompt.prompt still contains old key '{key}'. "
                "Rewrite to standard envelope (role/task/json_example/instructions)."
            )


# ===========================================================================
# C. Qwen3-specific QA prompt compliance
# ===========================================================================


class TestQwen3QAPromptCompliance:
    """Qwen3 preset QA prompts that were filled this session must have valid evaluation_criteria."""

    QWEN3_PRESET = "Quickstart-LMStudio-Qwen3.json"

    @pytest.fixture(scope="class")
    def qwen3(self) -> dict:
        return _load_preset(self.QWEN3_PRESET)

    def _get_qa_prompt(self, preset: dict, agent_name: str) -> dict:
        """Parse <agent>.QAPrompt.prompt from preset."""
        agent = preset.get(agent_name, {})
        prompt_str = agent.get("QAPrompt", {}).get("prompt", "")
        assert prompt_str, f"{self.QWEN3_PRESET}: {agent_name}.QAPrompt.prompt is empty"
        try:
            return json.loads(prompt_str)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{self.QWEN3_PRESET}: {agent_name}.QAPrompt.prompt is not valid JSON: {exc}") from exc

    def test_hunt_queries_qa_prompt_has_nonempty_evaluation_criteria(self, qwen3):
        """HuntQueriesExtract.QAPrompt.prompt must have a non-empty evaluation_criteria list."""
        qa_data = self._get_qa_prompt(qwen3, "HuntQueriesExtract")
        criteria = qa_data.get("evaluation_criteria")
        assert isinstance(criteria, list), (
            f"HuntQueriesExtract.QAPrompt.evaluation_criteria must be a list, got {type(criteria).__name__}"
        )
        assert len(criteria) > 0, "HuntQueriesExtract.QAPrompt.evaluation_criteria is empty"

    def test_proc_tree_qa_prompt_has_nonempty_evaluation_criteria(self, qwen3):
        """ProcTreeExtract.QAPrompt.prompt must have a non-empty evaluation_criteria list."""
        qa_data = self._get_qa_prompt(qwen3, "ProcTreeExtract")
        criteria = qa_data.get("evaluation_criteria")
        assert isinstance(criteria, list), (
            f"ProcTreeExtract.QAPrompt.evaluation_criteria must be a list, got {type(criteria).__name__}"
        )
        assert len(criteria) > 0, "ProcTreeExtract.QAPrompt.evaluation_criteria is empty"

    def test_hunt_queries_qa_prompt_has_role(self, qwen3):
        """QA prompt must have role or system key for _validate_qa_prompt_config."""
        qa_data = self._get_qa_prompt(qwen3, "HuntQueriesExtract")
        has_role = bool((qa_data.get("role") or qa_data.get("system") or "").strip())
        assert has_role, "HuntQueriesExtract.QAPrompt.prompt missing non-empty role/system"

    def test_proc_tree_qa_prompt_has_role(self, qwen3):
        """QA prompt must have role or system key for _validate_qa_prompt_config."""
        qa_data = self._get_qa_prompt(qwen3, "ProcTreeExtract")
        has_role = bool((qa_data.get("role") or qa_data.get("system") or "").strip())
        assert has_role, "ProcTreeExtract.QAPrompt.prompt missing non-empty role/system"

    def test_hunt_queries_qa_prompt_has_instructions(self, qwen3):
        """QA prompt must have a non-empty instructions key."""
        qa_data = self._get_qa_prompt(qwen3, "HuntQueriesExtract")
        assert qa_data.get("instructions", "").strip(), (
            "HuntQueriesExtract.QAPrompt.prompt missing non-empty 'instructions'"
        )

    def test_proc_tree_qa_prompt_has_instructions(self, qwen3):
        """QA prompt must have a non-empty instructions key."""
        qa_data = self._get_qa_prompt(qwen3, "ProcTreeExtract")
        assert qa_data.get("instructions", "").strip(), (
            "ProcTreeExtract.QAPrompt.prompt missing non-empty 'instructions'"
        )


# ===========================================================================
# D. Seed contract keys for newly rewritten agents
# ===========================================================================


class TestNewlyRewrittenSeedEnvelopes:
    """HuntQueriesExtract and ExtractAgent seeds must use the standard 4-key envelope."""

    @pytest.mark.parametrize("agent_name", ["HuntQueriesExtract", "ExtractAgent"])
    def test_seed_is_valid_json(self, agent_name):
        data = _load_prompt(agent_name)
        assert isinstance(data, dict), f"{agent_name} seed must be a JSON object at root"

    @pytest.mark.parametrize("agent_name", ["HuntQueriesExtract", "ExtractAgent"])
    @pytest.mark.parametrize("key", STANDARD_ENVELOPE_KEYS)
    def test_seed_has_envelope_key(self, agent_name, key):
        """Each seed must contain the standard key and it must be non-empty."""
        data = _load_prompt(agent_name)
        assert key in data, f"{agent_name} seed missing envelope key '{key}'"
        assert data[key], f"{agent_name} seed envelope key '{key}' is empty"

    @pytest.mark.parametrize("agent_name", ["HuntQueriesExtract", "ExtractAgent"])
    def test_seed_ascii_only(self, agent_name):
        """Seed file must contain only ASCII characters -- project rule."""
        raw = (PROMPT_DIR / agent_name).read_text(encoding="utf-8")
        assert _is_ascii_only(raw), f"{agent_name} seed contains non-ASCII characters. ASCII-only rule applies."

    @pytest.mark.parametrize("agent_name", ["HuntQueriesExtract", "ExtractAgent"])
    def test_seed_no_deprecated_keys(self, agent_name):
        """Rewritten seeds must not use old envelope keys."""
        data = _load_prompt(agent_name)
        old_keys = ("objective", "output_format", "user_template", "exclusions")
        for key in old_keys:
            assert key not in data, (
                f"{agent_name} seed still contains deprecated key '{key}'. "
                "Use standard envelope: role/task/json_example/instructions."
            )
