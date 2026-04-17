"""Unit tests for ``_merge_default_prompts`` used by the reset-to-defaults route.

These tests pin down the selective prompt-reset behavior that fixes
observable-traceability confidence scores for CmdlineExtract and sibling
extraction sub-agents. The bug surfaced because the *active workflow config in
the database* still pointed at stale prompts after the on-disk files were
updated to require traceability fields (confidence_score, source_evidence,
extraction_justification). The fix path: let an operator resync specific
agents from disk defaults without wiping customizations on the others.

The reset endpoint is a thin DB wrapper around ``_merge_default_prompts``;
exercising the helper directly keeps these tests fast and DB-free while
covering every branch of the merge rule.
"""

from __future__ import annotations

import pytest

from src.web.routes.workflow_config import _merge_default_prompts

pytestmark = pytest.mark.unit


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def disk_defaults() -> dict:
    """Minimal stand-in for ``get_default_agent_prompts()`` output."""
    return {
        "CmdlineExtract": {
            "model": "Not configured",
            "prompt": '{"role": "cmdline-role", "task": "extract cmdlines with confidence_score"}',
            "instructions": "",
        },
        "RegistryExtract": {
            "model": "Not configured",
            "prompt": '{"role": "registry-role", "task": "registry with confidence_score"}',
            "instructions": "",
        },
        "HuntQueriesExtract": {
            "model": "Not configured",
            "prompt": '{"role": "huntq-role", "task": "queries with traceability"}',
            "instructions": "",
        },
        "ProcTreeExtract": {
            "model": "Not configured",
            "prompt": '{"role": "proctree-role", "task": "process lineage with confidence"}',
            "instructions": "",
        },
    }


# ── Happy paths ───────────────────────────────────────────────────────────


@pytest.mark.regression
def test_resets_only_requested_agents_leaves_others_untouched(disk_defaults):
    """A targeted reset must replace only the listed agents' prompts."""
    existing = {
        "CmdlineExtract": {
            "prompt": '{"role": "stale-cmdline"}',
            "instructions": "",
            "model": "gpt-4o",
        },
        "RegistryExtract": {
            "prompt": '{"role": "stale-registry"}',
            "instructions": "",
            "model": "gpt-4o",
        },
        "SigmaAgent": {
            "prompt": "user-customized sigma prompt",
            "instructions": "keep me",
            "model": "custom-model",
        },
    }

    merged, reset = _merge_default_prompts(
        existing_prompts=existing,
        defaults=disk_defaults,
        agent_names=["CmdlineExtract"],
    )

    # Only CmdlineExtract was refreshed
    assert reset == ["CmdlineExtract"]
    assert merged["CmdlineExtract"]["prompt"] == disk_defaults["CmdlineExtract"]["prompt"]

    # RegistryExtract is still stale (not in the reset list)
    assert merged["RegistryExtract"]["prompt"] == '{"role": "stale-registry"}'

    # SigmaAgent (not in defaults at all) is preserved entirely
    assert merged["SigmaAgent"] == existing["SigmaAgent"]


def test_empty_agent_names_resets_every_disk_default(disk_defaults):
    """Omitting agent_names resets every key the disk defaults provide."""
    existing = {
        "CmdlineExtract": {"prompt": "stale", "instructions": "", "model": "gpt-4o"},
    }

    merged, reset = _merge_default_prompts(
        existing_prompts=existing,
        defaults=disk_defaults,
        agent_names=None,
    )

    assert set(reset) == set(disk_defaults.keys())
    for name in disk_defaults:
        assert merged[name]["prompt"] == disk_defaults[name]["prompt"]


def test_empty_list_resets_every_disk_default(disk_defaults):
    """Empty list is treated the same as None (reset all)."""
    merged, reset = _merge_default_prompts(
        existing_prompts={},
        defaults=disk_defaults,
        agent_names=[],
    )
    assert set(reset) == set(disk_defaults.keys())
    assert set(merged.keys()) == set(disk_defaults.keys())


@pytest.mark.regression
def test_preserves_model_selection_on_reset_agent(disk_defaults):
    """Resetting a prompt must not overwrite the user's model choice."""
    existing = {
        "CmdlineExtract": {
            "prompt": '{"role": "stale"}',
            "instructions": "",
            "model": "claude-opus-4-6",  # user picked this
        },
    }

    merged, _ = _merge_default_prompts(
        existing_prompts=existing,
        defaults=disk_defaults,
        agent_names=["CmdlineExtract"],
    )

    assert merged["CmdlineExtract"]["model"] == "claude-opus-4-6"
    # Prompt was refreshed
    assert merged["CmdlineExtract"]["prompt"] == disk_defaults["CmdlineExtract"]["prompt"]


def test_fills_model_from_default_when_existing_has_none(disk_defaults):
    """When no prior model selection exists, fall back to the disk default's model hint."""
    merged, _ = _merge_default_prompts(
        existing_prompts={},
        defaults=disk_defaults,
        agent_names=["CmdlineExtract"],
    )

    assert merged["CmdlineExtract"]["model"] == "Not configured"


def test_adds_agent_when_not_in_existing(disk_defaults):
    """If an agent is missing from existing prompts, the reset adds it."""
    merged, reset = _merge_default_prompts(
        existing_prompts={},
        defaults=disk_defaults,
        agent_names=["HuntQueriesExtract"],
    )

    assert reset == ["HuntQueriesExtract"]
    assert "HuntQueriesExtract" in merged
    assert merged["HuntQueriesExtract"]["prompt"] == disk_defaults["HuntQueriesExtract"]["prompt"]


def test_default_instructions_fall_back_to_empty_string(disk_defaults):
    """If a disk default omits ``instructions``, merged result uses empty string."""
    defaults = {
        "CmdlineExtract": {
            "model": "Not configured",
            "prompt": '{"role": "x"}',
            # no "instructions" key
        },
    }

    merged, _ = _merge_default_prompts({}, defaults, ["CmdlineExtract"])

    assert merged["CmdlineExtract"]["instructions"] == ""


def test_does_not_mutate_caller_inputs(disk_defaults):
    """The helper must not mutate the existing_prompts dict passed in."""
    existing = {
        "CmdlineExtract": {"prompt": "stale", "instructions": "", "model": "gpt-4o"},
        "SigmaAgent": {"prompt": "custom", "instructions": "", "model": "x"},
    }
    snapshot = {k: dict(v) for k, v in existing.items()}

    _merge_default_prompts(existing, disk_defaults, ["CmdlineExtract"])

    assert existing == snapshot


# ── All four extraction sub-agents (mirrors the Todoist bug scope) ────────


@pytest.mark.parametrize(
    "agent_name",
    ["CmdlineExtract", "RegistryExtract", "HuntQueriesExtract", "ProcTreeExtract"],
)
@pytest.mark.regression
def test_each_extraction_sub_agent_resets_cleanly(disk_defaults, agent_name):
    """Every sub-agent implicated in the confidence-score bug can be reset in isolation."""
    existing = {agent_name: {"prompt": "stale", "instructions": "", "model": "gpt-4o"}}

    merged, reset = _merge_default_prompts(existing, disk_defaults, [agent_name])

    assert reset == [agent_name]
    assert merged[agent_name]["prompt"] == disk_defaults[agent_name]["prompt"]


# ── Error paths ───────────────────────────────────────────────────────────


def test_raises_when_defaults_is_empty():
    """Caller must get a clear error if no disk defaults were loaded."""
    with pytest.raises(ValueError, match="No on-disk default prompts available"):
        _merge_default_prompts({}, {}, ["CmdlineExtract"])


@pytest.mark.regression
def test_raises_on_unknown_agent_name(disk_defaults):
    """Unknown agent names must produce a precise error listing the missing names."""
    with pytest.raises(ValueError, match="NotAnAgent"):
        _merge_default_prompts({}, disk_defaults, ["CmdlineExtract", "NotAnAgent"])


def test_skips_disk_entries_without_prompt(disk_defaults):
    """Disk default entries that lack a 'prompt' field must be skipped silently."""
    defaults = dict(disk_defaults)
    defaults["BrokenAgent"] = {"model": "x", "instructions": ""}  # no 'prompt'

    merged, reset = _merge_default_prompts({}, defaults, ["BrokenAgent", "CmdlineExtract"])

    # BrokenAgent skipped, CmdlineExtract applied
    assert reset == ["CmdlineExtract"]
    assert "BrokenAgent" not in merged


def test_existing_entry_not_a_dict_is_replaced_cleanly(disk_defaults):
    """If the existing entry for an agent is malformed (not a dict), reset still works."""
    # Some legacy snapshots store a raw string — make sure we recover
    existing = {"CmdlineExtract": "legacy-raw-string"}

    merged, reset = _merge_default_prompts(existing, disk_defaults, ["CmdlineExtract"])

    assert reset == ["CmdlineExtract"]
    assert merged["CmdlineExtract"]["prompt"] == disk_defaults["CmdlineExtract"]["prompt"]
    # Model falls back to the disk default since prior entry was unusable
    assert merged["CmdlineExtract"]["model"] == "Not configured"


def test_existing_instructions_replaced_by_disk_default(disk_defaults):
    """Custom instructions are overwritten on reset (unlike model which is preserved)."""
    existing = {
        "CmdlineExtract": {
            "prompt": "stale",
            "instructions": "user-customized instructions — should be replaced",
            "model": "gpt-4o",
        },
    }

    merged, _ = _merge_default_prompts(existing, disk_defaults, ["CmdlineExtract"])

    # Instructions come from disk default, NOT preserved from existing
    assert merged["CmdlineExtract"]["instructions"] == disk_defaults["CmdlineExtract"]["instructions"]
    # Model IS preserved
    assert merged["CmdlineExtract"]["model"] == "gpt-4o"


def test_multiple_agents_reset_simultaneously(disk_defaults):
    """Resetting multiple agents at once works and returns all names."""
    existing = {
        "CmdlineExtract": {"prompt": "stale-1", "instructions": "", "model": "gpt-4o"},
        "RegistryExtract": {"prompt": "stale-2", "instructions": "", "model": "claude-opus-4-6"},
        "SigmaAgent": {"prompt": "untouched", "instructions": "", "model": "x"},
    }

    merged, reset = _merge_default_prompts(
        existing, disk_defaults, ["CmdlineExtract", "RegistryExtract", "ProcTreeExtract"]
    )

    assert set(reset) == {"CmdlineExtract", "RegistryExtract", "ProcTreeExtract"}
    assert merged["CmdlineExtract"]["prompt"] == disk_defaults["CmdlineExtract"]["prompt"]
    assert merged["RegistryExtract"]["prompt"] == disk_defaults["RegistryExtract"]["prompt"]
    assert merged["ProcTreeExtract"]["prompt"] == disk_defaults["ProcTreeExtract"]["prompt"]
    # SigmaAgent untouched
    assert merged["SigmaAgent"]["prompt"] == "untouched"


def test_empty_string_model_falls_back_to_default(disk_defaults):
    """An empty-string model in the existing entry is falsy — should fall back to disk default."""
    existing = {
        "CmdlineExtract": {"prompt": "stale", "instructions": "", "model": ""},
    }

    merged, _ = _merge_default_prompts(existing, disk_defaults, ["CmdlineExtract"])

    # Empty string is falsy, so the `or` chain should pick up the disk default's model
    assert merged["CmdlineExtract"]["model"] == "Not configured"
