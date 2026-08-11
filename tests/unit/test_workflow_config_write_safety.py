"""Regression coverage for workflow-config write serialization and prompt merges."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.database.models import AgenticWorkflowConfigTable
from src.web.routes.workflow_config import _lock_workflow_config, _merge_agent_prompts

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
