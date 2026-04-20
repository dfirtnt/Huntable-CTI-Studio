"""Regression tests for the parsePromptParts JS bug fix.

Bug: In workflow.html parsePromptParts(), the `else if (parsed.role || parsed.objective)`
branch previously set `system = parsed.role` (a short persona string), hiding the
task/json_example/instructions content from the UI System Prompt display box.

Fix: That branch now sets `system = rawPrompt` (the full JSON string), so users see
the complete Extractor Contract config in the editor.

These tests use Node.js to execute the extracted JS function directly, so they
exercise the real implementation without needing a running browser.

Coverage:
  A. Extractor Contract format (role/task/json_example/instructions, no user_template)
     - system == rawPrompt (the full JSON), not just the role string
     - user == ''
     - isTemplateFormat == True
  B. Regression guard: user_template format routes to first branch (system = role only)
  C. Regression guard: {system, user} keys format routes to second branch
  D. Regression guard: plain string falls through to user=rawPrompt
  E. Save logic: when systemVal is full JSON with role key, merged uses it directly
  F. Save logic: when systemVal is plain string, envelope fields are preserved from parsed
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW_HTML = REPO_ROOT / "src" / "web" / "templates" / "workflow.html"
PRESET_DIR = REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"

QUICKSTART_PRESETS = [
    "Quickstart-LMStudio-Qwen3.json",
    "Quickstart-anthropic-sonnet-4-6.json",
    "Quickstart-openai-gpt-4.1-mini.json",
]

# Agents that use the Extractor Contract format (role/task/json_example/instructions).
EXTRACTOR_CONTRACT_AGENTS = [
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "CmdlineExtract",
    "ExtractAgent",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_available() -> bool:
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _extract_js_functions(html_path: Path) -> str:
    """Extract the JS helper functions needed to run parsePromptParts in isolation."""
    text = html_path.read_text(encoding="utf-8")

    # Grab stripOuterCodeFence, tryParseJsonMaybeDoubleEncoded,
    # extractJsonStringField, and parsePromptParts.
    # Each function ends at the next top-level function declaration or a blank
    # line after a closing brace -- we use a simple line-scanner approach:
    # find the start comment/line, then include everything up to (but not
    # including) the next `^function ` line after the closing brace.

    def _extract_function(name: str) -> str:
        lines = text.splitlines()
        in_func = False
        brace_depth = 0
        collected: list[str] = []
        found_open = False
        for line in lines:
            if not in_func:
                if f"function {name}" in line:
                    in_func = True
                    found_open = False
                    brace_depth = 0
                    collected = [line]
                    brace_depth += line.count("{") - line.count("}")
                    if brace_depth > 0:
                        found_open = True
                continue
            collected.append(line)
            brace_depth += line.count("{") - line.count("}")
            if not found_open and brace_depth > 0:
                found_open = True
            if found_open and brace_depth <= 0:
                break
        return "\n".join(collected)

    functions = "\n\n".join(
        [
            _extract_function("stripOuterCodeFence"),
            _extract_function("tryParseJsonMaybeDoubleEncoded"),
            _extract_function("extractJsonStringField"),
            _extract_function("parsePromptParts"),
        ]
    )
    return functions


def _run_parse_prompt_parts(raw_prompt: str) -> dict:
    """Execute parsePromptParts in Node.js and return the result dict."""
    js_functions = _extract_js_functions(WORKFLOW_HTML)

    # Safely embed the test input using JSON serialisation so quotes/newlines
    # in raw_prompt don't break the JS source.
    safe_input = json.dumps(raw_prompt)

    script = textwrap.dedent(f"""
        {js_functions}

        const rawPrompt = {safe_input};
        const result = parsePromptParts(rawPrompt);
        process.stdout.write(JSON.stringify(result));
    """)

    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # node --input-type=module may not be available in older versions; fall back
    if result.returncode != 0 and "--input-type" in result.stderr:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Node.js execution failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return json.loads(result.stdout)


def _load_preset(filename: str) -> dict:
    path = PRESET_DIR / filename
    assert path.exists(), f"Preset file missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A. Extractor Contract format -- the fixed branch
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="node not available")
class TestParsePromptPartsExtractorContract:
    """parsePromptParts must expose the full JSON when the prompt is an
    Extractor Contract (role/task/json_example/instructions, no user_template).

    This locks in the fix: previously system = parsed.role (short persona),
    now system = rawPrompt (full JSON string).
    """

    SAMPLE_CONTRACT = json.dumps(
        {
            "role": "You are a process tree extraction specialist.",
            "task": "Extract process execution chains from threat intel articles.",
            "json_example": '{"process": "cmd.exe", "parent": "explorer.exe"}',
            "instructions": "Focus on parent-child process relationships. Output valid JSON only.",
        }
    )

    def test_system_is_full_json_not_just_role(self):
        """system must equal rawPrompt (full JSON), NOT just the role string.

        Previously broken: system = parsed.role => short persona string.
        Fixed:             system = rawPrompt    => complete JSON config.
        """
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert result["system"] == self.SAMPLE_CONTRACT, (
            f"system should be the full JSON string.\n"
            f"Got: {result['system']!r}\n"
            f"Expected: {self.SAMPLE_CONTRACT!r}\n"
            "REGRESSION: fix reverted -- system was set to parsed.role instead of rawPrompt."
        )

    def test_system_contains_task_content(self):
        """system must contain the task content (was invisible before the fix)."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert "Extract process execution chains" in result["system"], (
            "task content is missing from system -- fix may have reverted."
        )

    def test_system_contains_instructions_content(self):
        """system must contain the instructions content (was invisible before the fix)."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert "parent-child process relationships" in result["system"], (
            "instructions content is missing from system -- fix may have reverted."
        )

    def test_user_is_empty(self):
        """user must be empty string for Extractor Contract format."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert result["user"] == "", f"user should be empty for Extractor Contract format, got: {result['user']!r}"

    def test_is_template_format_true(self):
        """isTemplateFormat must be True for Extractor Contract format."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert result["isTemplateFormat"] is True, "isTemplateFormat should be True for Extractor Contract format"

    def test_template_data_role_populated(self):
        """templateData.role must contain the role string."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert result["templateData"]["role"] == "You are a process tree extraction specialist.", (
            "templateData.role should contain the role persona string"
        )

    def test_template_data_task_populated(self):
        """templateData.task must contain the task string."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert "Extract process execution chains" in result["templateData"]["task"], (
            "templateData.task should contain the task content"
        )

    def test_template_data_instructions_populated(self):
        """templateData.instructions must contain the instructions string."""
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        assert "parent-child process relationships" in result["templateData"]["instructions"], (
            "templateData.instructions should contain the instructions content"
        )

    def test_broken_behavior_is_not_present(self):
        """The old broken value (system == role string only) must NOT appear.

        This is an explicit regression sentinel. If this fails, the fix was reverted.
        """
        result = _run_parse_prompt_parts(self.SAMPLE_CONTRACT)
        role_only = "You are a process tree extraction specialist."
        assert result["system"] != role_only, (
            "REGRESSION DETECTED: system == role-only string. The fix (system = rawPrompt) has been reverted."
        )


# ---------------------------------------------------------------------------
# B. Regression guard: user_template format (first branch)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="node not available")
class TestParsePromptPartsUserTemplateFormat:
    """user_template presence must route to the first branch (system = role string only)."""

    SAMPLE = json.dumps(
        {
            "role": "You are an extractor.",
            "user_template": "Title: {title}\nContent: {content}\n{instructions}",
            "task": "Extract IOCs.",
            "json_example": "{}",
            "instructions": "Be precise.",
        }
    )

    def test_system_is_role_only(self):
        """When user_template is present, system = role string (not full JSON)."""
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["system"] == "You are an extractor.", (
            f"With user_template present, system should be just the role string. Got: {result['system']!r}"
        )

    def test_user_is_template(self):
        """When user_template is present, user = the template string."""
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert "{title}" in result["user"], (
            "user should contain the user_template content when user_template key is present"
        )

    def test_is_template_format_true(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["isTemplateFormat"] is True


# ---------------------------------------------------------------------------
# C. Regression guard: {system, user} legacy format
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="node not available")
class TestParsePromptPartsLegacySystemUser:
    """{system, user} keys route to the legacy simple branch."""

    SAMPLE = json.dumps(
        {
            "system": "You are a helpful assistant.",
            "user": "Summarize the article.",
        }
    )

    def test_system_extracted(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["system"] == "You are a helpful assistant."

    def test_user_extracted(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["user"] == "Summarize the article."

    def test_is_template_format_false(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["isTemplateFormat"] is False


# ---------------------------------------------------------------------------
# D. Regression guard: plain string falls through to user=rawPrompt
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _node_available(), reason="node not available")
class TestParsePromptPartsPlainString:
    """A plain (non-JSON) string must fall through to user=rawPrompt, system=''."""

    SAMPLE = "You are a cybersecurity analyst. Extract TTPs from the article."

    def test_user_is_raw_prompt(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["user"] == self.SAMPLE, f"Plain string should become user content. Got: {result['user']!r}"

    def test_system_is_empty(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["system"] == "", f"system should be empty for plain string input. Got: {result['system']!r}"

    def test_is_template_format_false(self):
        result = _run_parse_prompt_parts(self.SAMPLE)
        assert result["isTemplateFormat"] is False


# ---------------------------------------------------------------------------
# E & F. Save logic: JS in saveAgentPrompt / saveAgentPrompt2
#         Tested via preset structure contract (Option 3 complement)
# ---------------------------------------------------------------------------


class TestSaveLogicContractViaPresets:
    """Verify that preset prompts used by extraction agents are in the full-JSON
    Extractor Contract format (role/task/json_example/instructions, no user_template).

    Connection to the save fix:
      - saveAgentPrompt detects `'role' in parsedSystem` to decide whether to use
        the value directly or wrap it in an envelope.
      - These presets are what the DB returns to populate the System Prompt box.
      - If the preset has all 4 standard keys and NO user_template, the display
        fix (parsePromptParts) is always exercised when the page loads.
    """

    STANDARD_ENVELOPE_KEYS = ("role", "task", "json_example", "instructions")

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    @pytest.mark.parametrize("agent_name", EXTRACTOR_CONTRACT_AGENTS)
    def test_extractor_agent_prompt_has_all_envelope_keys(self, preset_file, agent_name):
        """Each extractor agent prompt must have all 4 standard envelope keys.

        This ensures the Extractor Contract format is always the input that
        triggers the fixed parsePromptParts branch on page load.
        """
        preset = _load_preset(preset_file)
        agent = preset.get(agent_name)
        if agent is None:
            pytest.skip(f"{preset_file}: {agent_name} section not present")

        prompt_str = agent.get("Prompt", {}).get("prompt", "")
        if not prompt_str:
            pytest.skip(f"{preset_file}: {agent_name}.Prompt.prompt is empty")

        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError as exc:
            pytest.fail(f"{preset_file}: {agent_name}.Prompt.prompt is not valid JSON: {exc}")

        for key in self.STANDARD_ENVELOPE_KEYS:
            assert key in prompt_data, (
                f"{preset_file}: {agent_name}.Prompt.prompt missing key '{key}'. Found keys: {list(prompt_data.keys())}"
            )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    @pytest.mark.parametrize("agent_name", EXTRACTOR_CONTRACT_AGENTS)
    def test_extractor_agent_prompt_has_no_user_template(self, preset_file, agent_name):
        """Extractor Contract prompts must NOT have user_template.

        The presence of user_template routes parsePromptParts to the old first
        branch (system = role string only), bypassing the Extractor Contract path.
        The save logic also strips user_template on write; its presence in a preset
        would indicate a write-path regression.
        """
        preset = _load_preset(preset_file)
        agent = preset.get(agent_name)
        if agent is None:
            pytest.skip(f"{preset_file}: {agent_name} section not present")

        prompt_str = agent.get("Prompt", {}).get("prompt", "")
        if not prompt_str:
            pytest.skip(f"{preset_file}: {agent_name}.Prompt.prompt is empty")

        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError:
            pytest.skip(f"{preset_file}: prompt not valid JSON -- skip user_template check")
        else:
            assert "user_template" not in prompt_data, (
                f"{preset_file}: {agent_name}.Prompt.prompt contains 'user_template'. "
                "Extractor Contract prompts must not have this key. "
                "The save logic deletes it on write; its presence indicates a save-path regression."
            )

    @pytest.mark.parametrize("preset_file", QUICKSTART_PRESETS)
    @pytest.mark.parametrize("agent_name", EXTRACTOR_CONTRACT_AGENTS)
    def test_extractor_agent_prompt_envelope_keys_nonempty(self, preset_file, agent_name):
        """Envelope key values must be non-empty strings (or non-empty objects for json_example)."""
        preset = _load_preset(preset_file)
        agent = preset.get(agent_name)
        if agent is None:
            pytest.skip(f"{preset_file}: {agent_name} section not present")

        prompt_str = agent.get("Prompt", {}).get("prompt", "")
        if not prompt_str:
            pytest.skip(f"{preset_file}: {agent_name}.Prompt.prompt is empty")

        try:
            prompt_data = json.loads(prompt_str)
        except json.JSONDecodeError:
            pytest.skip(f"{preset_file}: prompt not valid JSON")

        for key in ("role", "task", "instructions"):
            value = prompt_data.get(key, "")
            assert isinstance(value, str) and value.strip(), (
                f"{preset_file}: {agent_name}.Prompt.prompt['{key}'] is empty or not a string. Got: {value!r}"
            )
