"""Regression tests: sigma eval must inject committed fixture content, not DB text."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from src.database.models import AgenticWorkflowConfigTable
from src.web.routes.evaluation_api import SigmaEvalRunRequest, _missing_sigma_eval_extractor_prompts, run_sigma_eval

pytestmark = pytest.mark.api

_FIXTURE_URL = "https://thedfirreport.com/2024/04/01/from-onenote-to-ransomnote-an-ice-cold-intrusion/"


def _active_config() -> AgenticWorkflowConfigTable:
    extractor_prompt = json.dumps({"system": "Extract observables", "user": "{content}"})
    return AgenticWorkflowConfigTable(
        id=7,
        version=3,
        is_active=True,
        min_hunt_score=97.0,
        ranking_threshold=6.0,
        similarity_threshold=0.5,
        agent_models={"ExtractAgent": "eval-model"},
        agent_prompts={
            "ExtractAgentSettings": {"disabled_agents": []},
            "CmdlineExtract": {"prompt": extractor_prompt},
            "ProcTreeExtract": {"prompt": extractor_prompt},
            "HuntQueriesExtract": {"prompt": extractor_prompt},
            "RegistryExtract": {"prompt": extractor_prompt},
            "ServicesExtract": {"prompt": extractor_prompt},
            "ScheduledTasksExtract": {"prompt": extractor_prompt},
            "NetworkIndicatorExtract": {"prompt": extractor_prompt},
        },
        cmdline_attention_preprocessor_enabled=True,
        proc_tree_attention_preprocessor_enabled=True,
    )


def _session_with_config(config: AgenticWorkflowConfigTable, added: list) -> MagicMock:
    session = MagicMock()
    config_query = MagicMock()
    config_query.filter.return_value.order_by.return_value.first.return_value = config
    session.query.return_value = config_query
    session.add.side_effect = lambda obj: added.append(obj)
    session.flush.side_effect = lambda: setattr(added[-1], "id", 501)
    return session


@pytest.mark.asyncio
async def test_sigma_eval_injects_committed_fixture_content():
    """A found article whose URL has a committed sigma fixture gets fixture text, not a DB fallback."""
    config = _active_config()
    added: list = []
    session = _session_with_config(config, added)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session

    captured_snapshots = []

    def capture_snapshot(_session, execution, payload):
        captured_snapshots.append(payload)
        execution.config_snapshot = {"snapshot_id": 45}

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api.resolve_articles_by_urls", return_value={_FIXTURE_URL: 100}),
        patch("src.web.routes.evaluation_api.attach_snapshot", side_effect=capture_snapshot),
        patch("src.web.routes.evaluation_api.trigger_agentic_workflow.apply_async") as apply_async,
    ):
        result = await run_sigma_eval(
            request=MagicMock(spec=Request),
            eval_request=SigmaEvalRunRequest(article_urls=[_FIXTURE_URL]),
        )

    assert result["success"] is True
    assert len(captured_snapshots) == 1
    snapshot = captured_snapshots[0]
    assert snapshot["sigma_eval"] is True
    assert snapshot["eval_fixture_content"]
    assert len(snapshot["eval_fixture_content"]) > 1000
    assert (
        snapshot["eval_fixture_content_sha256"]
        == hashlib.sha256(snapshot["eval_fixture_content"].encode("utf-8")).hexdigest()
    )
    apply_async.assert_called_once()


@pytest.mark.asyncio
async def test_sigma_eval_rejects_missing_enabled_extractor_prompts_before_dispatch():
    config = _active_config()
    del config.agent_prompts["CmdlineExtract"]
    added: list = []
    session = _session_with_config(config, added)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api.trigger_agentic_workflow.apply_async") as apply_async,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await run_sigma_eval(
                request=MagicMock(spec=Request),
                eval_request=SigmaEvalRunRequest(article_urls=[_FIXTURE_URL]),
            )

    assert exc_info.value.status_code == 422
    assert "CmdlineExtract" in exc_info.value.detail
    assert added == []
    session.commit.assert_not_called()
    apply_async.assert_not_called()


def test_sigma_eval_allows_missing_prompt_for_disabled_extractor():
    config = _active_config()
    del config.agent_prompts["CmdlineExtract"]
    config.agent_prompts["ExtractAgentSettings"] = {"disabled_agents": ["CmdlineExtract"]}

    assert _missing_sigma_eval_extractor_prompts(config) == []


@pytest.mark.asyncio
async def test_sigma_eval_hard_fails_when_fixture_missing():
    """A found article with no committed sigma fixture must 422, never fall back to DB content."""
    config = _active_config()
    added: list = []
    session = _session_with_config(config, added)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session
    missing_url = "https://example.test/not-a-committed-sigma-fixture"

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api.resolve_articles_by_urls", return_value={missing_url: 100}),
        patch("src.web.routes.evaluation_api.trigger_agentic_workflow.apply_async") as apply_async,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await run_sigma_eval(
                request=MagicMock(spec=Request),
                eval_request=SigmaEvalRunRequest(article_urls=[missing_url]),
            )

    assert exc_info.value.status_code == 422
    apply_async.assert_not_called()
