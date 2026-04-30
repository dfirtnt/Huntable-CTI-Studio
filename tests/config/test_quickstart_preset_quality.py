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
from src.web.routes.workflow_config import _scan_preset_prompts_for_warnings

pytestmark = pytest.mark.unit

_QUICKSTART_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "presets" / "AgentConfigs" / "quickstart"
_QUICKSTART_PRESETS = sorted(_QUICKSTART_DIR.glob("*.json"))

# Sections that carry a nested QA block with a Temperature field.
_QA_SECTIONS = [
    "RankAgent",
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
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


_QA_PROMPT_REQUIRED_FIELDS = ("role", "evaluation_criteria", "instructions")


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
            if field == "role":
                # Runtime accepts either 'role' or 'system' (mirrors llm_service._validate_qa_prompt_config)
                value = parsed.get("role") or parsed.get("system")
                if not value:
                    failures.append(f"{section}: QAPrompt.prompt missing or empty field 'role'/'system'")
                continue
            value = parsed.get(field)
            if not value:
                failures.append(f"{section}: QAPrompt.prompt missing or empty field '{field}'")
            elif field == "evaluation_criteria" and not isinstance(value, list):
                failures.append(f"{section}: QAPrompt.prompt 'evaluation_criteria' must be a list")

    assert not failures, f"{preset_path.name} QA prompt issues:\n" + "\n".join(f"  - {f}" for f in failures)
