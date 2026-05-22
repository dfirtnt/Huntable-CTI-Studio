"""
Data-quality invariant tests for quickstart preset files.

Guards against regressions in the JSON files themselves (not the loader):
- QA agent temperatures must be uniform within each preset.
- Base agent temperatures must all be 0.0.
- Descriptions must not be the stale "Exported preset" export artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config.workflow_config_loader import load_workflow_config
from src.web.routes.workflow_config import _scan_preset_prompts_for_warnings, _v2_to_legacy_preset_dict

pytestmark = pytest.mark.unit

_QUICKSTART_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
_QUICKSTART_PRESETS = sorted(_QUICKSTART_DIR.glob("*.json"))

# Only RankAgent retains a QA block; extractor QA was removed.
_QA_SECTIONS = [
    "RankAgent",
]

# Sections whose top-level Temperature must be deterministic (0.0).
# ExtractAgent is intentionally excluded: it no longer carries a Prompt field;
# it only provides model/provider/temperature fallback defaults for sub-agents.
_BASE_AGENT_SECTIONS = [
    "RankAgent",
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
    "SigmaAgent",
]


def _load(preset_path: Path) -> dict:
    return json.loads(preset_path.read_text())


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_loads_without_error(preset_path: Path):
    """Preset must pass the full load_workflow_config round-trip without error.

    Exercises Pydantic schema validation, migration logic, and required-field
    enforcement -- the same path the app uses at runtime.
    """
    data = _load(preset_path)
    load_workflow_config(data)


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_no_import_warnings(preset_path: Path):
    """Preset must produce zero warnings when scanned by the import-time prompt scanner.

    Runs the exact same scanner the /config/preset/import endpoint runs, so a
    quickstart preset that passes this test will import cleanly with no orange
    warnings in the UI.  Catches: empty prompts, invalid JSON, missing
    json_example, missing traceability fields.
    """
    data = _load(preset_path)
    config = load_workflow_config(data)
    agent_prompts = {
        name: {"prompt": pc.prompt, "instructions": pc.instructions} for name, pc in config.Prompts.items()
    }
    warnings = _scan_preset_prompts_for_warnings(agent_prompts)
    assert not warnings, f"{preset_path.name} would show import warnings:\n" + "\n".join(f"  - {w}" for w in warnings)


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_base_agent_prompts_complete(preset_path: Path):
    """Every base agent section must have a non-empty Prompt.prompt string."""
    data = _load(preset_path)
    empty: list[str] = []

    for section in _BASE_AGENT_SECTIONS:
        block = data.get(section, {})
        if not isinstance(block, dict):
            continue
        prompt_block = block.get("Prompt", {})
        prompt_str = prompt_block.get("prompt", "") if isinstance(prompt_block, dict) else ""
        if not str(prompt_str).strip():
            empty.append(section)

    assert not empty, f"{preset_path.name}: base agent Prompt.prompt is empty for: {', '.join(empty)}"


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_description_not_stale(preset_path: Path):
    """Description must not be the stale 'Exported preset' default."""
    data = _load(preset_path)
    desc = data.get("Metadata", {}).get("Description", "")
    assert desc != "Exported preset", (
        f"{preset_path.name}: Description is the stale export default 'Exported preset'; "
        "update it to describe the preset."
    )
    assert desc, f"{preset_path.name}: Description is empty."


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_qa_temperatures_uniform(preset_path: Path):
    """All QA agent temperatures within a preset must be the same value (no one-offs)."""
    data = _load(preset_path)
    temps: dict[str, float] = {}
    for section in _QA_SECTIONS:
        block = data.get(section, {})
        qa = block.get("QA")
        if qa and isinstance(qa, dict) and "Temperature" in qa:
            temps[section] = float(qa["Temperature"])

    if len(temps) < 2:
        return

    unique = set(temps.values())
    assert len(unique) == 1, (
        f"{preset_path.name}: QA temperatures are not uniform across agents. Values by section: {temps}"
    )


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_base_agent_temperatures_deterministic(preset_path: Path):
    """All base agent (non-QA) temperatures must be 0.0 for deterministic extraction."""
    data = _load(preset_path)
    wrong: dict[str, float] = {}
    for section in _BASE_AGENT_SECTIONS:
        block = data.get(section, {})
        if "Temperature" in block:
            t = float(block["Temperature"])
            if t != 0.0:
                wrong[section] = t

    assert not wrong, f"{preset_path.name}: Base agent temperatures must be 0.0. Non-zero values: {wrong}"


_QA_PROMPT_REQUIRED_FIELDS = ("system", "evaluation_criteria", "instructions")


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_qa_prompts_complete(preset_path: Path):
    """Every section with a QA block must have a non-empty QAPrompt with required fields."""
    data = _load(preset_path)
    failures: list[str] = []

    for section in _QA_SECTIONS:
        block = data.get(section, {})
        if not isinstance(block, dict) or not block.get("QA"):
            continue

        qa_prompt_block = block.get("QAPrompt", {})
        prompt_str = qa_prompt_block.get("prompt", "") if isinstance(qa_prompt_block, dict) else ""

        if not prompt_str or not prompt_str.strip():
            failures.append(f"{section}: QAPrompt.prompt is empty")
            continue

        try:
            parsed = json.loads(prompt_str)
        except (ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{section}: QAPrompt.prompt is not valid JSON ({exc})")
            continue

        for field in _QA_PROMPT_REQUIRED_FIELDS:
            if field == "system":
                # Runtime accepts either 'system' or legacy 'role' (mirrors llm_service._validate_qa_prompt_config)
                value = parsed.get("system") or parsed.get("role")
                if not value:
                    failures.append(f"{section}: QAPrompt.prompt missing or empty field 'system'/'role'")
                continue
            value = parsed.get(field)
            if not value:
                failures.append(f"{section}: QAPrompt.prompt missing or empty field '{field}'")
            elif field == "evaluation_criteria" and not isinstance(value, list):
                failures.append(f"{section}: QAPrompt.prompt 'evaluation_criteria' must be a list")

    assert not failures, f"{preset_path.name} QA prompt issues:\n" + "\n".join(f"  - {f}" for f in failures)


# ---------------------------------------------------------------------------
# Canonical-agent prompt round-trip through to-legacy conversion
# ---------------------------------------------------------------------------
# Background: SigmaAgent and RankAgent are LOCKED_CANONICAL_AGENTS whose
# generation prompts are stored in the legacy {prompt: "..."} shape inside
# quickstart presets. The UI imports V2 presets via:
#   load_workflow_config(v2_preset) → _v2_to_legacy_preset_dict(config)
# and places the result in agentPrompts[agentName].  renderSinglePrompt then
# calls parsePromptParts(agentPrompts[agentName].prompt) which routes text
# with {identifier} placeholders to promptParts.user.  The "Active generation
# template:" display in the amber locked-scaffold section reads promptParts.user.
#
# If _v2_to_legacy_preset_dict loses the prompt text, promptParts.user is
# empty and users see a blank prompt panel after every quickstart preset import.
# ---------------------------------------------------------------------------

_CANONICAL_AGENTS_IN_PRESETS = ("SigmaAgent", "RankAgent")


@pytest.mark.parametrize("preset_path", _QUICKSTART_PRESETS, ids=lambda p: p.stem)
def test_quickstart_canonical_agent_prompts_survive_to_legacy_roundtrip(preset_path: Path):
    """SigmaAgent and RankAgent prompts survive the V2→legacy conversion used by applyPreset().

    Regression guard for the blank-prompt-after-import bug (commit 9b8617d7):
    when a quickstart preset is imported the frontend calls /config/preset/to-legacy,
    which runs load_workflow_config → _v2_to_legacy_preset_dict. The resulting
    agent_prompts['SigmaAgent']['prompt'] must be non-empty so renderSinglePrompt
    can display it in the 'Active generation template:' section.
    """
    data = _load(preset_path)
    config = load_workflow_config(data)
    legacy = _v2_to_legacy_preset_dict(config)

    agent_prompts = legacy.get("agent_prompts", {})
    failures: list[str] = []

    for agent_name in _CANONICAL_AGENTS_IN_PRESETS:
        ap = agent_prompts.get(agent_name, {})
        prompt_text = ap.get("prompt", "")
        if not (prompt_text and prompt_text.strip()):
            failures.append(
                f"{agent_name}: prompt is empty after to-legacy conversion "
                "(the 'Active generation template:' display will be blank after import)"
            )

    assert not failures, f"{preset_path.name} lost canonical agent prompts in to-legacy conversion:\n" + "\n".join(
        f"  - {f}" for f in failures
    )
