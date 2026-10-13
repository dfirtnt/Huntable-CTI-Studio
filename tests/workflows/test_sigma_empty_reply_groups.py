"""An empty model reply for a SIGMA generation group means "zero rules", not a failure.

Regression for workflow executions 26, 37, 38, 39 and 40 (article 2645): every failure was the
``network_connection`` group. Its observables were C2 domains/URLs only, the system prompt says
"Behavior over IOC" and "output ONLY YAML", so the model had nothing it was allowed to write and
returned an agentMessage with empty text. The app turned that into
``Codex completed without an agent message. Turn carried no items.`` and failed the group -- and
the whole execution when it was the only group.

These tests drive the real ``generate_sigma`` node, the real ``SigmaGenerationService`` and the
real ``LLMService`` routing. The single stubbed seam is the Codex app-server transport: a scripted
client replays the JSON-RPC notifications a real turn produces, so ``_read_completed_turn`` and
``normalize_completed_turn`` run for real. No LLM is called.
"""

# ruff: noqa: F811  (pytest fixtures imported from the phase-one suite are re-bound as test args)

import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.codex_app_server_client import CodexAppServerClient, CodexAppServerError
from src.services.llm_service import WORKFLOW_PROVIDER_APPSETTING_KEYS, LLMService
from src.services.sigma_generation_service import SIGMA_NO_RULES_EMPTY_REPLY, SigmaGenerationService
from src.services.workflow_config_snapshot import build_config_snapshot
from src.workflows.status_utils import TERMINATION_REASON_NO_SIGMA_RULES
from tests.workflows.test_platform_telemetry_phase_one import (  # noqa: F401  (fixtures)
    _capture_nodes,
    _default_state,
    _make_db_session,
    _network_extraction,
    _two_windows_groups_extraction,
    article,
    config_obj,
    execution,
)

pytestmark = pytest.mark.unit

CODEX_MODEL = "gpt-5.6-luna"

PROCESS_RULE_YAML = """title: Net User Domain Account Discovery
id: 3b6f2f0e-8f3a-4a5e-9c1d-2a7b6c5d4e3f
status: experimental
description: Detects domain account discovery through the net user command.
references:
    - https://example.com/acceptance
author: Huntable CTI Studio
date: 2026-10-13
tags:
    - attack.discovery
    - attack.t1087.002
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: '/domain'
    condition: selection
falsepositives:
    - Administrative activity
level: medium
"""

NETWORK_MARKER = "`logsource.category: network_connection`"


def _agent_message(text):
    return {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": text}}}


def _turn_completed(status="completed", error=None):
    turn = {"status": status, "items": []}
    if error:
        turn["error"] = {"message": error}
    return {"method": "turn/completed", "params": {"turn": turn}}


REASONING = {"method": "item/completed", "params": {"item": {"type": "reasoning", "id": "r1"}}}
RULE_TURN = [REASONING, _agent_message(PROCESS_RULE_YAML), _turn_completed()]
# What executions 26/37-40 actually received: an agentMessage item whose text is "".
EMPTY_TURN = [REASONING, _agent_message(""), _turn_completed()]
FAILED_TURN = [_turn_completed(status="failed", error="You've hit your usage limit.")]
PROCESS_EXIT: list = []  # stdout closes before turn/completed


def _scripted_codex(script):
    """A CodexAppServerClient whose transport replays ``script(prompt) -> [notifications]``."""
    prompts: list[str] = []

    class ScriptedCodex(CodexAppServerClient):
        async def _start(self):
            return Path("/tmp")

        async def _close(self):
            return None

        async def _rpc(self, method, params):
            if method == "thread/start":
                return {"thread": {"id": "thread-1"}}
            if method == "turn/start":
                prompt = params["input"][0]["text"]
                prompts.append(prompt)
                self._queue = list(script(prompt))
            return {}

        async def _read_message(self):
            if not self._queue:
                raise CodexAppServerError("Codex app-server exited unexpectedly.")
            return self._queue.pop(0)

    ScriptedCodex.prompts = prompts
    return ScriptedCodex


def _by_group(*, process, network):
    return lambda prompt: network if NETWORK_MARKER in prompt else process


async def _run_node(article, execution, config_obj, extraction_result, script):
    """Run the real generate_sigma node + SigmaGenerationService over a scripted Codex transport."""
    config_obj.agent_models = {"SigmaAgent": CODEX_MODEL, "SigmaAgent_provider": "codex"}
    db_session = _make_db_session(article, execution)
    nodes = _capture_nodes(db_session, config_obj)
    codex_cls = _scripted_codex(script)
    with (
        patch.object(
            LLMService,
            "_load_workflow_provider_settings",
            return_value={WORKFLOW_PROVIDER_APPSETTING_KEYS["codex_enabled"]: "true"},
        ),
        patch.object(LLMService, "_load_lmstudio_settings", return_value={}),
        patch("src.services.llm_client.CodexAppServerClient", codex_cls),
        patch(
            "src.services.sigma_generation_service.optimize_article_content",
            new=AsyncMock(return_value={"success": True, "filtered_content": article.content, "tokens_saved": 0}),
        ),
    ):
        result = await nodes["generate_sigma"](
            _default_state(
                filtered_content=article.content,
                extraction_result=extraction_result,
                discrete_huntables_count=extraction_result.get("discrete_huntables_count"),
                config=build_config_snapshot(config_obj),
            )
        )
    return result, codex_cls.prompts


@pytest.mark.asyncio
async def test_empty_group_yields_zero_rules_and_keeps_sibling_rules(article, execution, config_obj, caplog):
    """Executions 26/37/38: network_connection came back empty while process_creation produced
    rules. The empty group contributes nothing and is recorded; it is not an error."""
    with caplog.at_level(logging.WARNING):
        result, prompts = await _run_node(
            article,
            execution,
            config_obj,
            _two_windows_groups_extraction(),
            _by_group(process=RULE_TURN, network=EMPTY_TURN),
        )

    assert len(prompts) == 2, "one Phase 1 call per group, no retry or expansion on an empty reply"
    assert [rule["title"] for rule in result["sigma_rules"]] == ["Net User Domain Account Discovery"]
    assert not result.get("error")
    assert execution.status != "failed"
    assert execution.error_message is None

    entry = execution.error_log["generate_sigma"]
    assert entry["errors"] is None
    assert entry["group_errors"] is None, "an empty reply must not be reported as a group error"
    assert [(g["platform"], g["telemetry_category"]) for g in entry["groups_with_no_rules"]] == [
        ("windows", "network_connection")
    ]
    no_rules = entry["groups_with_no_rules"][0]
    assert no_rules["reason"] == SIGMA_NO_RULES_EMPTY_REPLY
    assert no_rules["model"] == CODEX_MODEL
    assert no_rules["provider"] == "codex"
    assert no_rules["group"].startswith("windows:network_connection:")

    summaries = {g["telemetry_category"]: g for g in entry["sigma_generation_groups"]}
    assert summaries["network_connection"]["error"] is None
    assert summaries["network_connection"]["generated_rules"] == 0
    assert summaries["network_connection"]["no_rules"]["reason"] == SIGMA_NO_RULES_EMPTY_REPLY
    assert summaries["process_creation"]["generated_rules"] == 1
    assert summaries["process_creation"]["no_rules"] is None

    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == "src.workflows.agentic_workflow"
    ]
    assert any("windows:network_connection" in m and CODEX_MODEL in m and "empty reply" in m for m in warnings), (
        warnings
    )
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], "an empty reply must not log an error"


@pytest.mark.asyncio
async def test_only_group_empty_completes_with_zero_rules_and_recorded_reason(article, execution, config_obj):
    """Executions 39/40: network_connection was the ONLY group, so the empty reply failed the
    whole execution. It must complete with zero rules and say why."""
    result, prompts = await _run_node(article, execution, config_obj, _network_extraction(), lambda prompt: EMPTY_TURN)

    assert len(prompts) == 1
    assert result["sigma_rules"] == []
    assert not result.get("error")
    assert result.get("should_continue") is not False
    assert result["status"] == "running"
    assert execution.status == "running"
    assert execution.error_message is None
    assert result["termination_reason"] == TERMINATION_REASON_NO_SIGMA_RULES
    details = result["termination_details"]
    assert details["generated_rules"] == 0
    assert details["groups_with_no_rules"][0]["reason"] == SIGMA_NO_RULES_EMPTY_REPLY
    assert details["groups_with_no_rules"][0]["model"] == CODEX_MODEL

    entry = execution.error_log["generate_sigma"]
    assert entry["errors"] is None
    assert entry["group_errors"] is None
    assert len(entry["groups_with_no_rules"]) == 1
    # The prompt that drew the empty reply stays inspectable in the conversation log.
    call = entry["conversation_log"][0]
    assert call["event_type"] == "generation_call"
    assert call["llm_response"] == ""
    assert call["no_rules"]["reason"] == SIGMA_NO_RULES_EMPTY_REPLY
    assert call["messages"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_all_groups_empty_completes_with_zero_rules(article, execution, config_obj):
    result, prompts = await _run_node(
        article, execution, config_obj, _two_windows_groups_extraction(), lambda prompt: EMPTY_TURN
    )

    assert len(prompts) == 2
    assert result["sigma_rules"] == []
    assert not result.get("error")
    assert execution.status == "running"
    assert result["termination_reason"] == TERMINATION_REASON_NO_SIGMA_RULES
    entry = execution.error_log["generate_sigma"]
    assert {g["telemetry_category"] for g in entry["groups_with_no_rules"]} == {
        "process_creation",
        "network_connection",
    }
    assert entry["group_errors"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("network_turn", "expected_error"),
    [(FAILED_TURN, "usage limit"), (PROCESS_EXIT, "exited unexpectedly")],
    ids=["turn-status-failed", "process-exit"],
)
async def test_real_codex_failure_still_fails_the_group(article, execution, config_obj, network_turn, expected_error):
    """A genuine Codex failure is not an empty reply: the group still errors as before."""
    result, _ = await _run_node(
        article,
        execution,
        config_obj,
        _two_windows_groups_extraction(),
        _by_group(process=RULE_TURN, network=network_turn),
    )

    # Partial success still completes, exactly as before the change.
    assert len(result["sigma_rules"]) == 1
    entry = execution.error_log["generate_sigma"]
    assert expected_error in entry["group_errors"]
    assert "network_connection" in entry["group_errors"]
    assert entry["groups_with_no_rules"] == []
    summaries = {g["telemetry_category"]: g for g in entry["sigma_generation_groups"]}
    assert expected_error in summaries["network_connection"]["error"]
    assert summaries["network_connection"]["no_rules"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("turn", "expected_error"),
    [(FAILED_TURN, "usage limit"), (PROCESS_EXIT, "exited unexpectedly"), ([REASONING, _turn_completed()], "without")],
    ids=["turn-status-failed", "process-exit", "no-agent-message"],
)
async def test_real_codex_failure_in_only_group_still_fails_the_execution(
    article, execution, config_obj, turn, expected_error
):
    result, _ = await _run_node(article, execution, config_obj, _network_extraction(), lambda prompt: turn)

    assert result["sigma_rules"] == []
    assert expected_error in result["error"]
    assert result["should_continue"] is False
    assert execution.status == "failed"
    assert expected_error in execution.error_message
    assert execution.error_log["generate_sigma"]["groups_with_no_rules"] == []


@pytest.mark.asyncio
async def test_empty_and_failed_groups_together_still_fail_the_execution(article, execution, config_obj):
    """An empty reply must not mask a sibling's real failure when nothing was generated."""
    result, _ = await _run_node(
        article,
        execution,
        config_obj,
        _two_windows_groups_extraction(),
        _by_group(process=FAILED_TURN, network=EMPTY_TURN),
    )

    assert execution.status == "failed"
    assert "usage limit" in result["error"]
    entry = execution.error_log["generate_sigma"]
    assert "process_creation" in entry["group_errors"]
    assert len(entry["groups_with_no_rules"]) == 1


@pytest.mark.asyncio
async def test_non_codex_empty_content_is_zero_rules_not_an_exception():
    """Other providers signal the same outcome as empty ``content``. That used to raise a
    ValueError straight out of generate_sigma_rules, aborting every remaining group."""
    llm = Mock()
    llm.provider_sigma = "openai"
    llm.model_sigma = "gpt-4o-mini"
    llm.provider_defaults = {"openai": "gpt-4o-mini"}
    llm.temperature_sigma = 0.0
    llm.top_p_sigma = 0.9
    llm.seed = None
    llm.effort_sigma = None
    llm._canonicalize_provider = Mock(return_value="lmstudio")
    llm._convert_messages_for_model = Mock(side_effect=lambda messages, model: messages)
    llm.request_chat = AsyncMock(return_value={"choices": [{"message": {"content": "  "}}], "usage": {}})
    with patch("src.services.sigma_generation_service.LLMService", return_value=llm):
        service = SigmaGenerationService()

    with patch(
        "src.services.sigma_generation_service.optimize_article_content",
        new=AsyncMock(return_value={"success": True, "filtered_content": "content", "tokens_saved": 0}),
    ):
        result = await service.generate_sigma_rules(
            article_title="t", article_content="content", source_name="s", url="https://example.com/a"
        )

    assert result["rules"] == []
    assert result["errors"] is None
    assert result["metadata"]["no_rules"]["reason"] == SIGMA_NO_RULES_EMPTY_REPLY
    assert result["metadata"]["no_rules"]["model"] == "gpt-4o-mini"
    assert llm.request_chat.await_count == 1
