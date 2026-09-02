"""Contract tests: every shipped extractor prompt must satisfy the in-app validator.

Regression context
-----------------
RegistryExtract and ServicesExtract carried a full VERIFICATION CHECKLIST section
whose items had drifted from ``- [ ] `` checkboxes to plain ``- `` bullets. The
client-side validator (``_collectPromptIssues``) tests for the literal ``[ ]``
token, so both agents warned "missing expected token for VERIFICATION CHECKLIST
(sec 12)". The drift was present in all 12 quickstart presets and both on-disk
seeds simultaneously, so there was no clean copy to diff against, and it survived
until a manual dogfood pass clicked Validate three panels deep.

The same class of drift previously hit CmdlineExtract with *seven* missing tokens
at once. Guarding only the one token that happened to break would test the symptom
rather than the class, so these tests assert the **whole** validator contract
against every shipped prompt.

The token lists are parsed out of ``prompt-editor.js`` rather than restated here:
if someone adds a required token to the validator, these tests must start
enforcing it automatically instead of silently lagging behind.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.utils.workflow_html_source import read_workflow_src

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_QUICKSTART_DIR = _REPO_ROOT / "config" / "presets" / "AgentConfigs" / "quickstart"
_QUICKSTART_PRESETS = sorted(_QUICKSTART_DIR.glob("*.json"))
_PROMPT_EDITOR_JS = _REPO_ROOT / "src" / "web" / "static" / "js" / "workflow" / "prompt-editor.js"
_PROMPTS_DIR = _REPO_ROOT / "src" / "prompts"

# Mirrors EXTRACT_SUB_AGENTS; asserted against the JS source below so a new
# extractor cannot be added to the app without being covered here.
_EXTRACTORS = [
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
    "NetworkIndicatorExtract",
]

_TRACEABILITY_FIELDS = ["value", "source_evidence", "extraction_justification", "confidence_score"]
_TRACEABILITY_REQUIRED = ["source_evidence", "extraction_justification", "confidence_score"]


# ---------------------------------------------------------------------------
# Parse the validator's own token lists
# ---------------------------------------------------------------------------


def _parse_token_list(js: str, const_name: str) -> list[tuple[str, str]]:
    """Extract [['token', 'label'], ...] pairs from a JS const array literal."""
    match = re.search(
        rf"const\s+{re.escape(const_name)}\s*=\s*\[(.*?)\n\s*\];",
        js,
        re.DOTALL,
    )
    assert match, f"{const_name} not found in prompt-editor.js -- validator refactored?"
    pairs = re.findall(r"\[\s*'((?:[^'\\]|\\.)*)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\]", match.group(1))
    return [(tok.replace("\\'", "'"), label.replace("\\'", "'")) for tok, label in pairs]


@pytest.fixture(scope="module")
def js_source() -> str:
    return _PROMPT_EDITOR_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def system_tokens(js_source: str) -> list[tuple[str, str]]:
    return _parse_token_list(js_source, "_SYSTEM_WARN_TOKENS")


@pytest.fixture(scope="module")
def instruction_tokens(js_source: str) -> list[tuple[str, str]]:
    return _parse_token_list(js_source, "_INSTRUCTIONS_WARN_TOKENS")


class TestTokenParsingIsNotVacuous:
    """A regex that quietly matches nothing would make every test below pass.

    tests/utils/workflow_html_source.py documents this exact hazard, so the
    parsed lists are pinned rather than merely checked for truthiness.
    """

    def test_system_tokens_parsed(self, system_tokens):
        tokens = [t for t, _ in system_tokens]
        assert len(tokens) == 5, f"expected 5 system tokens, parsed {tokens}"
        assert "[ ]" in tokens, "sec-12 checklist token missing from parsed list"
        assert "LITERAL TEXT EXTRACTOR" in tokens

    def test_instruction_tokens_parsed(self, instruction_tokens):
        tokens = [t for t, _ in instruction_tokens]
        assert len(tokens) == 3, f"expected 3 instruction tokens, parsed {tokens}"
        assert "When in doubt, OMIT" in tokens

    def test_extractor_list_matches_app(self):
        # EXTRACT_SUB_AGENTS lives in workflow.html, not the extracted JS modules,
        # which is exactly the split read_workflow_src() exists to paper over.
        match = re.search(r"const\s+EXTRACT_SUB_AGENTS\s*=\s*\[(.*?)\];", read_workflow_src(), re.DOTALL)
        assert match, "EXTRACT_SUB_AGENTS not found in the workflow JS surface"
        found = re.findall(r"'([^']+)'", match.group(1))
        assert sorted(found) == sorted(_EXTRACTORS), (
            f"extractor roster drifted: app has {sorted(found)}, test covers {sorted(_EXTRACTORS)}"
        )


# ---------------------------------------------------------------------------
# Port of _collectPromptIssues for extractor envelopes
# ---------------------------------------------------------------------------


def _collect_issues(prompt_str: str, system_tokens, instruction_tokens) -> list[str]:
    """Python port of the extractor branch of _collectPromptIssues.

    Returns human-readable issue strings; empty means "Validation passed".
    """
    issues: list[str] = []
    if not prompt_str.strip():
        return ["error: system prompt is empty"]

    try:
        parsed = json.loads(prompt_str)
    except ValueError:
        return issues  # plain role text is a valid shape; envelope rules do not apply
    if not isinstance(parsed, dict):
        return issues

    if "user_template" in parsed:
        issues.append("error: 'user_template' must not be present (sec 5)")

    role = (parsed.get("system") or parsed.get("role") or "").strip()
    if not role:
        issues.append("error: missing 'role'/'system' (sec 1)")

    instructions = (parsed.get("instructions") or "").strip()
    if not instructions:
        issues.append("error: missing 'instructions' (sec 2)")

    example = parsed.get("json_example")
    if example is None:
        issues.append("error: missing 'json_example' (sec 4)")
    else:
        parsed_example = example
        if isinstance(example, str):
            try:
                parsed_example = json.loads(example)
            except ValueError:
                issues.append("error: 'json_example' is not valid JSON (sec 4)")
                parsed_example = None
        if isinstance(parsed_example, dict):
            items = next(
                (v for v in parsed_example.values() if isinstance(v, list) and v and isinstance(v[0], dict)),
                None,
            )
            if items:
                keys = set(items[0])
                missing = [f for f in _TRACEABILITY_REQUIRED if f not in keys]
                if missing:
                    issues.append(f"error: json_example missing traceability fields: {', '.join(missing)}")
                has_domain_fields = any(f not in _TRACEABILITY_FIELDS for f in keys)
                if not has_domain_fields and "value" not in keys:
                    issues.append("error: json_example items missing 'value'")

    if role:
        issues += [f"warn: role missing {label}: {token!r}" for token, label in system_tokens if token not in role]
    if instructions:
        issues += [
            f"warn: instructions missing {label}: {token!r}"
            for token, label in instruction_tokens
            if token not in instructions
        ]
    return issues


def _preset_prompt(preset: dict, agent: str) -> str:
    block = preset.get(agent, {})
    prompt_block = block.get("Prompt", {}) if isinstance(block, dict) else {}
    return str(prompt_block.get("prompt", "")) if isinstance(prompt_block, dict) else ""


# ---------------------------------------------------------------------------
# The shipped data must satisfy that contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_preset_extractor_prompts_pass_validation(preset_path, system_tokens, instruction_tokens):
    """Every extractor in every shipped preset must validate clean."""
    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    for agent in _EXTRACTORS:
        prompt = _preset_prompt(preset, agent)
        if not prompt:
            continue  # absence is covered by test_quickstart_base_agent_prompts_complete
        for issue in _collect_issues(prompt, system_tokens, instruction_tokens):
            failures.append(f"{agent}: {issue}")

    assert not failures, f"{preset_path.name} ships prompts the in-app validator flags:\n" + "\n".join(
        f"  - {f}" for f in failures
    )


@pytest.mark.parametrize("agent", _EXTRACTORS)
def test_seed_extractor_prompts_pass_validation(agent, system_tokens, instruction_tokens):
    """The src/prompts seeds the presets are built from must validate clean too."""
    prompt = (_PROMPTS_DIR / agent).read_text(encoding="utf-8")
    issues = _collect_issues(prompt, system_tokens, instruction_tokens)
    assert not issues, f"src/prompts/{agent} would be flagged by the in-app validator:\n" + "\n".join(
        f"  - {i}" for i in issues
    )


class TestPortDetectsRealDrift:
    """The port must actually fail on the drift it exists to catch.

    Without these, a port bug that returns [] for everything would make the two
    tests above pass no matter what shipped.
    """

    def test_detects_checklist_marker_drift(self, system_tokens, instruction_tokens):
        """The exact RegistryExtract/ServicesExtract regression: '- [ ] ' -> '- '."""
        healthy = (_PROMPTS_DIR / "RegistryExtract").read_text(encoding="utf-8")
        assert _collect_issues(healthy, system_tokens, instruction_tokens) == []

        degraded = json.loads(healthy)
        degraded["role"] = degraded["role"].replace("- [ ] ", "- ")
        issues = _collect_issues(json.dumps(degraded), system_tokens, instruction_tokens)

        assert any("VERIFICATION CHECKLIST" in i for i in issues), issues
        assert len(issues) == 1, f"marker drift should raise exactly the sec-12 warning, got {issues}"

    def test_detects_multi_token_drift(self, system_tokens, instruction_tokens):
        """The CmdlineExtract failure mode: a stub role losing many tokens at once."""
        envelope = json.loads((_PROMPTS_DIR / "CmdlineExtract").read_text(encoding="utf-8"))
        envelope["role"] = "You extract command lines."
        issues = _collect_issues(json.dumps(envelope), system_tokens, instruction_tokens)
        assert len(issues) == len(system_tokens), issues

    def test_detects_missing_required_keys(self, system_tokens, instruction_tokens):
        envelope = json.loads((_PROMPTS_DIR / "ServicesExtract").read_text(encoding="utf-8"))
        del envelope["json_example"]
        envelope["instructions"] = ""
        issues = _collect_issues(json.dumps(envelope), system_tokens, instruction_tokens)
        assert any("json_example" in i for i in issues), issues
        assert any("instructions" in i for i in issues), issues

    def test_plain_role_text_is_not_flagged(self, system_tokens, instruction_tokens):
        """Non-JSON prompts are a valid shape; flagging them would be a false alarm."""
        assert _collect_issues("You are a literal extractor.", system_tokens, instruction_tokens) == []
