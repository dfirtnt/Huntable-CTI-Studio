"""Regression coverage for workflow-config write serialization and prompt merges."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from src.database.models import AgenticWorkflowConfigTable
from src.web.routes.workflow_config import (
    _lock_workflow_config,
    _merge_agent_prompts,
    _validate_agent_model_pairs,
)

pytestmark = pytest.mark.unit


def test_partial_prompt_merge_preserves_unmentioned_agents_and_removes_explicit_nulls():
    current = {
        "CmdlineExtract": {"prompt": "current"},
        "SigmaAgent": {"prompt": "keep"},
    }

    merged = _merge_agent_prompts(
        current,
        {
            "CmdlineExtract": {"prompt": "updated"},
            "SigmaAgent": None,
            "RankAgent": {"prompt": "new"},
        },
    )

    assert merged == {
        "CmdlineExtract": {"prompt": "updated"},
        "RankAgent": {"prompt": "new"},
    }
    assert current == {
        "CmdlineExtract": {"prompt": "current"},
        "SigmaAgent": {"prompt": "keep"},
    }


def test_absent_prompt_payload_keeps_current_prompts():
    current = {"SigmaAgent": {"prompt": "keep"}}

    assert _merge_agent_prompts(current, None) == current


def test_postgres_write_lock_uses_transaction_scoped_advisory_lock():
    session = Mock()
    session.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    _lock_workflow_config(session)

    statement, params = session.execute.call_args.args
    assert str(statement) == "SELECT pg_advisory_xact_lock(:key)"
    assert params == {"key": 8412771}


@pytest.mark.parametrize("dialect", ["sqlite", "mysql"])
def test_non_postgres_write_lock_is_a_noop(dialect):
    session = Mock()
    session.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))

    _lock_workflow_config(session)

    session.execute.assert_not_called()


def test_workflow_config_version_is_declared_unique_for_new_schemas():
    assert AgenticWorkflowConfigTable.__table__.c.version.unique is True


class TestValidateAgentModelPairs:
    """The config write boundary must reject provably-wrong provider/model pairs
    without making an already-broken config permanently unsaveable.

    Two shapes make this subtle, and both were got wrong on the first pass:

    1. Sub-extractors store their model at "<Agent>_model", only RankAgent /
       ExtractAgent / SigmaAgent use the bare key (workflow_config_schema.py).
       Checking the bare key alone skips 7 of the 10 model-bearing agents.
    2. The UI autosave sends *every* agent_models key it holds, so scoping by
       "present in the payload" validates the whole blob. Since an autosave 400 is
       only logged to the console, a pre-existing mismatch would then silently
       discard unrelated edits forever. Scope is therefore "changed vs stored".
    """

    def test_rejects_a_newly_introduced_mismatch(self):
        merged = {"SigmaAgent_provider": "lmstudio", "SigmaAgent": "gpt-5.6-sol"}
        with pytest.raises(HTTPException) as exc_info:
            _validate_agent_model_pairs(merged, current={})
        assert exc_info.value.status_code == 400
        assert "SigmaAgent" in exc_info.value.detail
        assert "gpt-5.6-sol" in exc_info.value.detail

    def test_rejects_when_only_the_model_changed(self):
        current = {"SigmaAgent_provider": "anthropic", "SigmaAgent": "claude-sonnet-5"}
        merged = {"SigmaAgent_provider": "anthropic", "SigmaAgent": "gpt-4o"}
        with pytest.raises(HTTPException):
            _validate_agent_model_pairs(merged, current=current)

    def test_rejects_when_only_the_provider_changed(self):
        current = {"SigmaAgent_provider": "openai", "SigmaAgent": "gpt-4o"}
        merged = {"SigmaAgent_provider": "anthropic", "SigmaAgent": "gpt-4o"}
        with pytest.raises(HTTPException):
            _validate_agent_model_pairs(merged, current=current)

    def test_allows_codex_with_openai_family_model(self):
        """The live config and three shipped quickstart presets depend on this."""
        merged = {"SigmaAgent_provider": "codex", "SigmaAgent": "gpt-5.6-sol"}
        _validate_agent_model_pairs(merged, current={})

    # -- sub-extractor key shape (regression: these were silently unchecked) ------

    @pytest.mark.parametrize(
        "agent",
        [
            "CmdlineExtract",
            "ProcTreeExtract",
            "RegistryExtract",
            "ServicesExtract",
            "ScheduledTasksExtract",
            "HuntQueriesExtract",
            "NetworkIndicatorExtract",
        ],
    )
    def test_sub_extractor_mismatch_is_caught_via_model_suffix_key(self, agent):
        merged = {f"{agent}_provider": "lmstudio", f"{agent}_model": "gpt-5.6-sol"}
        with pytest.raises(HTTPException) as exc_info:
            _validate_agent_model_pairs(merged, current={})
        assert agent in exc_info.value.detail

    def test_sub_extractor_valid_pair_is_allowed(self):
        merged = {"CmdlineExtract_provider": "codex", "CmdlineExtract_model": "gpt-5.6-luna"}
        _validate_agent_model_pairs(merged, current={})

    def test_live_config_shape_round_trips(self):
        """The shape actually stored today: codex everywhere, sub-agents suffixed."""
        merged = {"SigmaAgent_provider": "codex", "SigmaAgent": "gpt-5.6-sol"}
        for agent in ("CmdlineExtract", "ProcTreeExtract", "RegistryExtract"):
            merged[f"{agent}_provider"] = "codex"
            merged[f"{agent}_model"] = "gpt-5.6-luna"
        _validate_agent_model_pairs(merged, current={})

    # -- autosave safety: full-blob payloads must not weaponise old mismatches ----

    def test_full_blob_autosave_does_not_reject_a_preexisting_mismatch(self):
        """The real autosave payload carries every key. An unrelated edit must still
        save even though ExtractAgent is already broken -- otherwise the operator
        silently loses work to a console-only 400."""
        stored = {
            "ExtractAgent_provider": "lmstudio",
            "ExtractAgent": "gpt-5.6-sol",  # pre-existing mismatch
            "RankAgent_provider": "openai",
            "RankAgent": "gpt-4o-mini",
        }
        merged = dict(stored, RankAgent="gpt-4o")  # operator edits an unrelated agent
        _validate_agent_model_pairs(merged, current=stored)

    def test_touching_the_broken_agent_still_surfaces_it(self):
        stored = {"ExtractAgent_provider": "lmstudio", "ExtractAgent": "gpt-5.6-sol"}
        merged = {"ExtractAgent_provider": "lmstudio", "ExtractAgent": "gpt-4o"}
        with pytest.raises(HTTPException):
            _validate_agent_model_pairs(merged, current=stored)

    def test_repairing_a_broken_agent_is_allowed(self):
        """The operator must be able to save their way out."""
        stored = {"ExtractAgent_provider": "lmstudio", "ExtractAgent": "gpt-5.6-sol"}
        merged = {"ExtractAgent_provider": "codex", "ExtractAgent": "gpt-5.6-sol"}
        _validate_agent_model_pairs(merged, current=stored)

    def test_reports_every_offending_agent_at_once(self):
        merged = {
            "SigmaAgent_provider": "lmstudio",
            "SigmaAgent": "gpt-4o",
            "CmdlineExtract_provider": "anthropic",
            "CmdlineExtract_model": "gpt-4o-mini",
        }
        with pytest.raises(HTTPException) as exc_info:
            _validate_agent_model_pairs(merged, current={})
        assert "SigmaAgent" in exc_info.value.detail
        assert "CmdlineExtract" in exc_info.value.detail

    def test_agent_without_a_model_is_allowed(self):
        merged = {"CmdlineExtract_provider": "codex"}
        _validate_agent_model_pairs(merged, current={})

    def test_empty_payloads_are_noops(self):
        _validate_agent_model_pairs({}, {})
        _validate_agent_model_pairs({}, None)
        _validate_agent_model_pairs({"SigmaAgent_provider": "", "SigmaAgent": "gpt-4o"}, {})
