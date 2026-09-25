"""PUT /api/workflow/config rejects an effort tier the agent's model cannot take."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.web.routes.workflow_config import _validate_agent_effort_values

pytestmark = pytest.mark.unit


def _merged(**extra):
    base = {
        "SigmaAgent_provider": "openai",
        "SigmaAgent": "gpt-5.6-luna",
        "CmdlineExtract_provider": "anthropic",
        "CmdlineExtract_model": "claude-sonnet-4-6",
        "RankAgent_provider": "codex",
        "RankAgent": "gpt-5.6-terra",
        "ProcTreeExtract_provider": "openai",
        "ProcTreeExtract_model": "gpt-4o",
    }
    base.update(extra)
    return base


def test_supported_tier_passes():
    _validate_agent_effort_values(_merged(SigmaAgent_effort="xhigh", CmdlineExtract_effort="max"))


def test_blank_or_missing_effort_is_ignored():
    _validate_agent_effort_values(_merged(SigmaAgent_effort="", CmdlineExtract_effort=None))


def test_tier_outside_the_models_list_is_rejected_with_the_supported_list():
    with pytest.raises(HTTPException) as exc:
        _validate_agent_effort_values(_merged(CmdlineExtract_effort="xhigh"))
    assert exc.value.status_code == 400
    detail = exc.value.detail
    assert "CmdlineExtract" in detail and "claude-sonnet-4-6" in detail and "xhigh" in detail
    assert "low, medium, high, max" in detail


def test_model_with_no_effort_control_rejects_any_tier():
    with pytest.raises(HTTPException) as exc:
        _validate_agent_effort_values(_merged(ProcTreeExtract_effort="high"))
    assert "no effort control" in exc.value.detail


def test_codex_tiers_are_live_so_only_the_token_shape_is_checked():
    _validate_agent_effort_values(_merged(RankAgent_effort="ultra"))
    with pytest.raises(HTTPException) as exc:
        _validate_agent_effort_values(_merged(RankAgent_effort="not a tier!"))
    assert "RankAgent" in exc.value.detail


def test_all_problems_are_reported_together():
    with pytest.raises(HTTPException) as exc:
        _validate_agent_effort_values(_merged(CmdlineExtract_effort="xhigh", ProcTreeExtract_effort="low"))
    assert "CmdlineExtract" in exc.value.detail and "ProcTreeExtract" in exc.value.detail
