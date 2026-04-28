"""Backward-compatibility shim tests: CmdlineQA → CmdLineQA normalization in v2 configs.

The handoff report notes that test_cmdline_qa_normalized in test_workflow_config_migrate.py
only covers the v1-flat → v2 path.  These tests cover the v2-input path, where a stored
config already has Version "2.0" but still contains the old "CmdlineQA" key in one or more
of the three sections that receive normalization:

  * Agents
  * QA.Enabled
  * Prompts

They also cover the conflict case (both old and new key present simultaneously).
"""

import pytest

from src.config.workflow_config_migrate import migrate_v1_to_v2
from src.config.workflow_config_schema import WorkflowConfigV2

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Minimal v2 skeleton — avoids duplication across test fixtures.
# All tests start from this and layer their specific Agents / QA / Prompts.
# ---------------------------------------------------------------------------

_BASE_V2: dict = {
    "Version": "2.0",
    "Metadata": {"CreatedAt": "2026-01-01T00:00:00Z", "Description": "shim test"},
    "Thresholds": {
        "MinHuntScore": 97.0,
        "RankingThreshold": 6.0,
        "SimilarityThreshold": 0.5,
        "JunkFilterThreshold": 0.8,
    },
    "Embeddings": {"OsDetection": "bert", "Sigma": "bert"},
    "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": False},
    "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}, "OsDetectionSelectedOs": ["Windows"]},
}

_RANK_AGENT_CFG = {"Provider": "lmstudio", "Model": "rank-model", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}
_QA_AGENT_CFG = {"Provider": "lmstudio", "Model": "qa-model", "Temperature": 0.0, "TopP": 0.9, "Enabled": True}


def _v2_with(**overrides) -> dict:
    """Return a complete v2 dict, deep-copying _BASE_V2 and applying overrides."""
    import copy

    d = copy.deepcopy(_BASE_V2)
    d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# Agents section
# ---------------------------------------------------------------------------


def test_agents_cmdline_qa_old_key_renamed():
    """v2 config with 'CmdlineQA' in Agents → normalised to 'CmdLineQA'."""
    raw = _v2_with(
        Agents={
            "RankAgent": _RANK_AGENT_CFG,
            "CmdlineQA": _QA_AGENT_CFG,  # old casing
        },
        QA={"Enabled": {}, "MaxRetries": 3},
        Prompts={
            "RankAgent": {"prompt": "", "instructions": ""},
            "CmdlineQA": {"prompt": "p", "instructions": "i"},
        },
    )
    result = migrate_v1_to_v2(raw)
    assert "CmdLineQA" in result["Agents"], "old key should be renamed to CmdLineQA"
    assert "CmdlineQA" not in result["Agents"], "old key must not survive"
    assert result["Agents"]["CmdLineQA"]["Model"] == "qa-model"


def test_agents_conflict_old_key_dropped():
    """When both 'CmdlineQA' AND 'CmdLineQA' exist in Agents, old one is silently dropped."""
    raw = _v2_with(
        Agents={
            "RankAgent": _RANK_AGENT_CFG,
            "CmdLineQA": {**_QA_AGENT_CFG, "Model": "canonical-model"},
            "CmdlineQA": {**_QA_AGENT_CFG, "Model": "legacy-model"},
        },
        QA={"Enabled": {}, "MaxRetries": 3},
        Prompts={"RankAgent": {"prompt": "", "instructions": ""}},
    )
    result = migrate_v1_to_v2(raw)
    assert "CmdlineQA" not in result["Agents"], "legacy key must be dropped"
    assert "CmdLineQA" in result["Agents"], "canonical key must survive"
    assert result["Agents"]["CmdLineQA"]["Model"] == "canonical-model", "canonical model must be kept"


# ---------------------------------------------------------------------------
# QA.Enabled section
# ---------------------------------------------------------------------------


def test_qa_enabled_cmdline_qa_old_key_renamed():
    """v2 config with 'CmdlineQA' in QA.Enabled → renamed to 'CmdLineQA'."""
    raw = _v2_with(
        Agents={"RankAgent": _RANK_AGENT_CFG},
        QA={"Enabled": {"CmdlineQA": True}, "MaxRetries": 3},  # old casing
        Prompts={"RankAgent": {"prompt": "", "instructions": ""}},
    )
    result = migrate_v1_to_v2(raw)
    enabled = result["QA"]["Enabled"]
    assert "CmdLineQA" in enabled, "old QA.Enabled key should be renamed"
    assert "CmdlineQA" not in enabled, "old QA.Enabled key must not survive"
    assert enabled["CmdLineQA"] is True


def test_qa_enabled_conflict_old_key_dropped():
    """Both CmdlineQA and CmdLineQA in QA.Enabled → old one dropped, canonical kept."""
    raw = _v2_with(
        Agents={"RankAgent": _RANK_AGENT_CFG},
        QA={
            "Enabled": {
                "CmdLineQA": False,  # canonical — should survive
                "CmdlineQA": True,  # legacy — must be dropped
            },
            "MaxRetries": 3,
        },
        Prompts={"RankAgent": {"prompt": "", "instructions": ""}},
    )
    result = migrate_v1_to_v2(raw)
    enabled = result["QA"]["Enabled"]
    assert "CmdlineQA" not in enabled
    assert "CmdLineQA" in enabled
    assert enabled["CmdLineQA"] is False, "canonical value must be preserved"


# ---------------------------------------------------------------------------
# Prompts section
# ---------------------------------------------------------------------------


def test_prompts_cmdline_qa_old_key_renamed():
    """v2 config with 'CmdlineQA' in Prompts → renamed to 'CmdLineQA'."""
    raw = _v2_with(
        Agents={
            "RankAgent": _RANK_AGENT_CFG,
            "CmdLineQA": _QA_AGENT_CFG,
        },
        QA={"Enabled": {}, "MaxRetries": 3},
        Prompts={
            "RankAgent": {"prompt": "", "instructions": ""},
            "CmdlineQA": {"prompt": "old-prompt", "instructions": "old-instr"},  # old casing
        },
    )
    result = migrate_v1_to_v2(raw)
    prompts = result["Prompts"]
    assert "CmdLineQA" in prompts, "old Prompts key should be renamed"
    assert "CmdlineQA" not in prompts, "old Prompts key must not survive"
    assert prompts["CmdLineQA"]["prompt"] == "old-prompt"
    assert prompts["CmdLineQA"]["instructions"] == "old-instr"


def test_prompts_conflict_old_key_dropped():
    """Both CmdlineQA and CmdLineQA in Prompts → old one dropped, canonical kept."""
    raw = _v2_with(
        Agents={
            "RankAgent": _RANK_AGENT_CFG,
            "CmdLineQA": _QA_AGENT_CFG,
        },
        QA={"Enabled": {}, "MaxRetries": 3},
        Prompts={
            "RankAgent": {"prompt": "", "instructions": ""},
            "CmdLineQA": {"prompt": "canonical-prompt", "instructions": ""},  # canonical
            "CmdlineQA": {"prompt": "legacy-prompt", "instructions": ""},  # legacy — drop
        },
    )
    result = migrate_v1_to_v2(raw)
    prompts = result["Prompts"]
    assert "CmdlineQA" not in prompts
    assert "CmdLineQA" in prompts
    assert prompts["CmdLineQA"]["prompt"] == "canonical-prompt"


# ---------------------------------------------------------------------------
# End-to-end: normalised result passes WorkflowConfigV2.model_validate()
# ---------------------------------------------------------------------------


def test_normalised_v2_validates_successfully():
    """A v2 config that arrives with 'CmdlineQA' should normalise and validate."""
    raw = _v2_with(
        Agents={
            "RankAgent": _RANK_AGENT_CFG,
            "RankAgentQA": _QA_AGENT_CFG,
            "CmdlineExtract": _RANK_AGENT_CFG,
            "CmdlineQA": _QA_AGENT_CFG,  # old key
        },
        QA={"Enabled": {"CmdlineQA": True}, "MaxRetries": 3},
        Prompts={
            "RankAgent": {"prompt": "", "instructions": ""},
            "RankAgentQA": {"prompt": "", "instructions": ""},
            "CmdlineExtract": {"prompt": "", "instructions": ""},
            "CmdlineQA": {"prompt": "", "instructions": ""},
        },
    )
    result = migrate_v1_to_v2(raw)
    # Must not raise
    config = WorkflowConfigV2.model_validate(result)
    assert "CmdLineQA" in config.Agents
    assert "CmdlineQA" not in config.Agents
