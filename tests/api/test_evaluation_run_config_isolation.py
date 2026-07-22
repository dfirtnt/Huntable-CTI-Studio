"""Regression tests for full-workflow evaluation config isolation."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from src.database.models import AgenticWorkflowConfigTable, ArticleTable
from src.web.routes.evaluation_api import EvaluationRunRequest, run_evaluation

pytestmark = pytest.mark.api


def _config(config_id: int, *, is_active: bool) -> AgenticWorkflowConfigTable:
    return AgenticWorkflowConfigTable(
        id=config_id,
        version=config_id,
        is_active=is_active,
        min_hunt_score=91.0,
        ranking_threshold=7.0,
        similarity_threshold=0.4,
        junk_filter_threshold=0.7,
        sigma_fallback_enabled=True,
        rank_agent_enabled=True,
        cmdline_attention_preprocessor_enabled=False,
        proc_tree_attention_preprocessor_enabled=False,
        agent_models={"ExtractAgent": "eval-model"},
        agent_prompts={"CmdlineExtract": {"prompt": "fixture prompt"}},
    )


def _session_for(article: ArticleTable, config: AgenticWorkflowConfigTable) -> MagicMock:
    session = MagicMock()
    article_query = MagicMock()
    article_query.filter.return_value.first.return_value = article
    config_query = MagicMock()
    config_query.filter.return_value.first.return_value = config
    session.query.side_effect = [article_query, config_query]
    session.refresh.side_effect = lambda execution: setattr(execution, "id", 501)
    return session


@pytest.mark.asyncio
async def test_full_eval_keeps_active_config_unchanged_and_snapshots_fixture_content():
    active_config = _config(10, is_active=True)
    eval_config = _config(20, is_active=False)
    article = ArticleTable(id=100, canonical_url="https://example.test/eval")
    session = _session_for(article, eval_config)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._load_static_eval_fixture_by_url", return_value="committed fixture"),
        patch("src.web.routes.evaluation_api.trigger_agentic_workflow.apply_async") as apply_async,
    ):
        result = await run_evaluation(
            request=MagicMock(spec=Request),
            eval_request=EvaluationRunRequest(article_ids=[100], config_ids=[20]),
        )

    assert result["success"] is True
    assert active_config.is_active is True
    assert eval_config.is_active is False
    execution = session.add.call_args.args[0]
    assert execution.config_snapshot["config_id"] == 20
    assert execution.config_snapshot["junk_filter_threshold"] == 0.7
    assert execution.config_snapshot["eval_fixture_content"] == "committed fixture"
    assert execution.config_snapshot["eval_fixture_content_sha256"] == hashlib.sha256(b"committed fixture").hexdigest()
    apply_async.assert_called_once_with(args=[100, 501], countdown=0.0)
    assert session.commit.call_count == 1


@pytest.mark.asyncio
async def test_full_eval_dispatch_failure_cannot_change_active_config():
    active_config = _config(10, is_active=True)
    eval_config = _config(20, is_active=False)
    article = ArticleTable(id=100, canonical_url="https://example.test/eval")
    session = _session_for(article, eval_config)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._load_static_eval_fixture_by_url", return_value=None),
        patch(
            "src.web.routes.evaluation_api.trigger_agentic_workflow.apply_async",
            side_effect=RuntimeError("broker down"),
        ),
        pytest.raises(HTTPException),
    ):
        await run_evaluation(
            request=MagicMock(spec=Request),
            eval_request=EvaluationRunRequest(article_ids=[100], config_ids=[20]),
        )

    assert active_config.is_active is True
    assert eval_config.is_active is False
    assert session.commit.call_count == 1
    session.close.assert_called_once()
