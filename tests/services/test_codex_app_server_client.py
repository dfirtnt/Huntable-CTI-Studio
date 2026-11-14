"""Unit tests for the isolated Codex app-server adapter."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.codex_app_server_client import (
    CODEX_STREAM_LIMIT,
    CodexAppServerClient,
    CodexAppServerError,
    CodexEmptyAgentMessageError,
    messages_to_codex_input,
    normalize_completed_turn,
)

pytestmark = pytest.mark.unit


def test_messages_to_codex_input_preserves_existing_roles():
    payload = messages_to_codex_input(
        [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Extract commands."},
        ],
        max_tokens=250,
    )

    text = payload[0]["text"]
    assert "<system>\nReturn JSON.\n</system>" in text
    assert "<user>\nExtract commands.\n</user>" in text
    assert "Do not call tools" in text


def test_messages_to_codex_input_skips_empty_content_and_carries_token_budget():
    payload = messages_to_codex_input(
        [
            {"role": "user", "content": ""},
            {"role": "user", "content": None},
            {"role": "user", "content": "Extract commands."},
        ],
        max_tokens=500,
    )

    text = payload[0]["text"]
    assert text.count("<user>") == 1
    assert "Extract commands." in text
    assert "500" in text


def test_normalize_completed_turn_returns_workflow_shape():
    result = normalize_completed_turn(
        {"status": "completed", "usage": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10}},
        '{"items": []}',
        "gpt-5.6-luna",
    )

    assert result["choices"][0]["message"]["content"] == '{"items": []}'
    assert result["usage"] == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
    assert result["_provider_url"] == "codex-app-server://local"


def test_normalize_completed_turn_rejects_failed_or_empty_turns():
    with pytest.raises(CodexAppServerError, match="subscription expired"):
        normalize_completed_turn({"status": "failed", "error": {"message": "subscription expired"}}, "", "model")

    with pytest.raises(CodexAppServerError, match="without an agent message"):
        normalize_completed_turn({"status": "completed"}, "", "model")


@pytest.mark.asyncio
async def test_list_models_uses_visible_models_with_subscription_default_first():
    client = CodexAppServerClient(timeout=15.0)
    client._start = AsyncMock()
    client._close = AsyncMock()
    client._rpc = AsyncMock(
        side_effect=[
            {},
            {
                "data": [
                    {"model": "gpt-5.6-terra", "hidden": False, "isDefault": False},
                    {"model": "gpt-5.6-luna", "hidden": False, "isDefault": True},
                    {"model": "hidden", "hidden": True, "isDefault": False},
                    {"id": "gpt-5.6-sol", "hidden": False, "isDefault": False},
                    {"model": "gpt-5.5", "hidden": True, "isDefault": False},
                ]
            },
        ]
    )

    assert await client.list_models() == ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]


@pytest.mark.asyncio
async def test_list_models_keeps_every_visible_numbered_generation_and_drops_codenames():
    """A gpt-6.1 default must not hide gpt-6-* or the gpt-5.6-* models existing configs use."""
    client = CodexAppServerClient(timeout=15.0)
    client._start = AsyncMock()
    client._close = AsyncMock()
    client._rpc = AsyncMock(
        side_effect=[
            {},
            {
                "data": [
                    {"model": "gpt-6-luna", "hidden": False, "isDefault": False},
                    {"model": "gpt-6.1-sol", "hidden": False, "isDefault": True},
                    {"model": "gpt-5.6-sol", "hidden": False, "isDefault": False},
                    {"model": "gpt-5.5", "hidden": True, "isDefault": False},
                    {"model": "gpt-daybreak-blue-latest", "hidden": False, "isDefault": False},
                ]
            },
        ]
    )

    assert await client.list_models() == ["gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-sol"]


@pytest.mark.asyncio
async def test_list_models_without_a_default_flag_and_with_id_only_entries():
    """Entries may carry only ``id``; with no isDefault the numbered models are still listed
    and a codename-only catalog yields an empty picker rather than leaking codenames."""

    def client_for(data):
        client = CodexAppServerClient(timeout=15.0)
        client._start = AsyncMock()
        client._close = AsyncMock()
        client._rpc = AsyncMock(side_effect=[{}, {"data": data}])
        return client

    mixed = client_for(
        [
            {"id": "gpt-6-luna", "hidden": False},
            {"id": "gpt-daybreak-blue-latest", "hidden": False},
            {"id": "gpt-5.6-terra", "hidden": False},
        ]
    )
    assert await mixed.list_models() == ["gpt-6-luna", "gpt-5.6-terra"]

    only_codenames = client_for([{"id": "gpt-daybreak-blue-latest", "hidden": False}])
    assert await only_codenames.list_models() == []


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gpt-5.6-luna", (5, 6)),
        ("gpt-6-sol", (6, 0)),
        ("gpt-6.1-sol", (6, 1)),
        ("gpt-5", (5, 0)),
        ("gpt-daybreak-blue-latest", None),
        ("codex-auto-review", None),
    ],
)
def test_model_generation_parses_numbered_ids_only(model_id, expected):
    from src.services.codex_app_server_client import _model_generation

    assert _model_generation(model_id) == expected


@pytest.mark.asyncio
async def test_list_models_returns_empty_list_for_malformed_model_response():
    client = CodexAppServerClient(timeout=15.0)
    client._start = AsyncMock()
    client._close = AsyncMock()
    client._rpc = AsyncMock(side_effect=[{}, {"data": {"model": "gpt-5.6-luna"}}])

    assert await client.list_models() == []
    client._close.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_starts_an_ephemeral_read_only_thread():
    client = CodexAppServerClient(timeout=15.0)
    client._start = AsyncMock(return_value=Path("/tmp/huntable-codex-workspace"))
    client._close = AsyncMock()
    client._rpc = AsyncMock(side_effect=[{}, {"thread": {"id": "thread-123"}}, {}])
    client._read_completed_turn = AsyncMock(return_value={"choices": []})

    result = await client.complete(
        messages=[{"role": "user", "content": "Extract commands."}],
        model_name="gpt-5.6-luna",
        max_tokens=250,
    )

    assert result == {"choices": []}
    assert client._rpc.await_args_list[1].args == (
        "thread/start",
        {
            "model": "gpt-5.6-luna",
            "cwd": "/tmp/huntable-codex-workspace",
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "ephemeral": True,
        },
    )


@pytest.mark.asyncio
async def test_read_completed_turn_uses_pending_agent_message():
    """An agentMessage notification already buffered wins over turn items."""
    client = CodexAppServerClient(timeout=15.0)
    client._pending_notifications = [
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "from pending item"}}},
    ]
    client._read_message = AsyncMock(
        return_value={"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
    )

    result = await client._read_completed_turn("gpt-5.6-luna")

    assert result["choices"][0]["message"]["content"] == "from pending item"
    client._read_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_completed_turn_falls_back_to_turn_items():
    """Without a buffered agentMessage, extract it from the completed turn's items."""
    client = CodexAppServerClient(timeout=15.0)
    client._pending_notifications = []
    client._read_message = AsyncMock(
        return_value={
            "method": "turn/completed",
            "params": {"turn": {"status": "completed", "items": [{"type": "agentMessage", "text": "from turn items"}]}},
        }
    )

    result = await client._read_completed_turn("gpt-5.6-luna")

    assert result["choices"][0]["message"]["content"] == "from turn items"


@pytest.mark.asyncio
async def test_read_completed_turn_rejects_missing_agent_text():
    client = CodexAppServerClient(timeout=15.0)
    client._pending_notifications = []
    client._read_message = AsyncMock(
        return_value={"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}
    )

    with pytest.raises(CodexAppServerError, match="without an agent message"):
        await client._read_completed_turn("gpt-5.6-luna")


def _scripted_client(*messages):
    client = CodexAppServerClient(timeout=15.0)
    client._pending_notifications = []
    client._read_message = AsyncMock(side_effect=list(messages))
    return client


_EMPTY_TURN_COMPLETED = {"method": "turn/completed", "params": {"turn": {"status": "completed", "items": []}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "  \n"])
async def test_read_completed_turn_flags_empty_agent_message_distinctly(text):
    """Executions 26/37-40: the model DID answer (item/completed delivered an agentMessage) but
    with no text. That is not the same outcome as a turn with no agentMessage at all, and the
    old message ("Turn carried no items") said the opposite of what happened."""
    client = _scripted_client(
        {"method": "item/completed", "params": {"item": {"type": "reasoning", "id": "r1"}}},
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": text}}},
        _EMPTY_TURN_COMPLETED,
    )

    with pytest.raises(CodexEmptyAgentMessageError) as excinfo:
        await client._read_completed_turn("gpt-5.6-luna")

    message = str(excinfo.value)
    assert "empty agent message" in message
    assert "gpt-5.6-luna" in message
    assert "agentMessage" in message
    assert "no items" not in message.lower()
    # Still a CodexAppServerError, so callers that do not special-case it keep failing closed.
    assert isinstance(excinfo.value, CodexAppServerError)


@pytest.mark.asyncio
async def test_read_completed_turn_without_any_agent_message_is_not_an_empty_reply():
    """A reasoning-only / refused / throttled turn must keep raising the generic error."""
    client = _scripted_client(
        {"method": "item/completed", "params": {"item": {"type": "reasoning", "id": "r1"}}},
        _EMPTY_TURN_COMPLETED,
    )

    with pytest.raises(CodexAppServerError, match="without an agent message") as excinfo:
        await client._read_completed_turn("gpt-5.6-luna")

    assert not isinstance(excinfo.value, CodexEmptyAgentMessageError)
    # Item types seen only in notifications are now part of the forensic trace.
    assert "Turn items: reasoning." in str(excinfo.value)


@pytest.mark.asyncio
async def test_read_completed_turn_failed_turn_with_empty_agent_message_still_raises_the_failure():
    client = _scripted_client(
        {"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": ""}}},
        {
            "method": "turn/completed",
            "params": {"turn": {"status": "failed", "error": {"message": "usage limit reached"}}},
        },
    )

    with pytest.raises(CodexAppServerError, match="usage limit reached") as excinfo:
        await client._read_completed_turn("gpt-5.6-luna")

    assert not isinstance(excinfo.value, CodexEmptyAgentMessageError)


def test_normalize_completed_turn_empty_agent_message_listed_in_turn_items():
    with pytest.raises(CodexEmptyAgentMessageError):
        normalize_completed_turn(
            {"status": "completed", "items": [{"type": "agentMessage", "text": ""}]}, "", "gpt-5.6-luna"
        )


@pytest.mark.asyncio
async def test_read_message_rejects_invalid_json_line():
    client = CodexAppServerClient(timeout=15.0)
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"this is not json\n")
    stdout.feed_eof()
    client.process = SimpleNamespace(stdout=stdout, stderr=None, returncode=None)

    with pytest.raises(CodexAppServerError, match="invalid JSON-RPC output"):
        await client._read_message()


@pytest.mark.asyncio
async def test_read_message_reports_stderr_when_process_exits():
    client = CodexAppServerClient(timeout=15.0)
    stdout = asyncio.StreamReader()
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_data(b"codex: login required\n")
    stderr.feed_eof()
    client.process = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=None)

    with pytest.raises(CodexAppServerError, match="login required"):
        await client._read_message()


@pytest.mark.asyncio
async def test_read_message_reports_oversized_line_instead_of_raw_value_error():
    """A JSON-RPC line past the stream limit must surface as a Codex error, not ValueError."""
    client = CodexAppServerClient(timeout=15.0)
    stdout = asyncio.StreamReader(limit=16)
    stdout.feed_data(b"x" * 512 + b"\n")
    client.process = SimpleNamespace(stdout=stdout, stderr=None, returncode=None)

    with pytest.raises(CodexAppServerError, match="larger than the"):
        await client._read_message()


@pytest.mark.asyncio
async def test_start_raises_the_stdout_buffer_above_the_asyncio_default():
    """Codex echoes turn input back, so the 64 KiB default truncates large SIGMA prompts."""
    client = CodexAppServerClient(timeout=15.0)

    with patch("src.services.codex_app_server_client.asyncio.create_subprocess_exec") as spawn:
        spawn.return_value = SimpleNamespace(stdout=None, stderr=None, stdin=None, returncode=None)
        await client._start()

    assert spawn.await_args.kwargs["limit"] == CODEX_STREAM_LIMIT
    assert CODEX_STREAM_LIMIT > 64 * 1024


@pytest.mark.asyncio
async def test_list_model_details_preserves_reasoning_effort_tiers_and_default():
    """model/list carries supportedReasoningEfforts; they must survive into the UI payload."""
    client = CodexAppServerClient(timeout=15.0)
    client._start = AsyncMock()
    client._close = AsyncMock()
    client._rpc = AsyncMock(
        side_effect=[
            {},
            {
                "data": [
                    {
                        "model": "gpt-5.6-luna",
                        "hidden": False,
                        "isDefault": True,
                        "supportedReasoningEfforts": [
                            {"reasoningEffort": "low", "description": "Fast responses"},
                            {"reasoningEffort": "ultra", "description": "Maximum reasoning"},
                        ],
                        "defaultReasoningEffort": "low",
                    },
                    {"model": "gpt-5.6-sol", "hidden": False, "isDefault": False},
                    {"model": "gpt-5.5", "hidden": True, "isDefault": False},
                ]
            },
        ]
    )

    details = await client.list_model_details()

    assert [d["model"] for d in details] == ["gpt-5.6-luna", "gpt-5.6-sol"]
    assert details[0]["is_default"] is True
    assert details[0]["supported_reasoning_efforts"] == [
        {"reasoning_effort": "low", "description": "Fast responses"},
        {"reasoning_effort": "ultra", "description": "Maximum reasoning"},
    ]
    assert details[0]["default_reasoning_effort"] == "low"
    # A model without tier data still lists, with an empty tier set.
    assert details[1]["supported_reasoning_efforts"] == []
    assert details[1]["default_reasoning_effort"] is None


@pytest.mark.asyncio
async def test_complete_sends_effort_as_a_turn_override_only_when_configured():
    client = CodexAppServerClient(timeout=15.0)
    client._start = AsyncMock(return_value=Path("/tmp/huntable-codex-workspace"))
    client._close = AsyncMock()
    client._rpc = AsyncMock(side_effect=[{}, {"thread": {"id": "thread-1"}}, {}])
    client._read_completed_turn = AsyncMock(return_value={"choices": []})

    await client.complete(
        messages=[{"role": "user", "content": "Extract commands."}],
        model_name="gpt-5.6-luna",
        max_tokens=250,
        effort="xhigh",
    )
    turn_start = client._rpc.await_args_list[2].args
    assert turn_start[0] == "turn/start"
    assert turn_start[1]["threadId"] == "thread-1"
    assert turn_start[1]["effort"] == "xhigh"
    client._read_completed_turn.assert_awaited_once_with("gpt-5.6-luna", effort="xhigh")

    client._rpc = AsyncMock(side_effect=[{}, {"thread": {"id": "thread-2"}}, {}])
    client._read_completed_turn = AsyncMock(return_value={"choices": []})
    await client.complete(
        messages=[{"role": "user", "content": "Extract commands."}],
        model_name="gpt-5.6-luna",
        max_tokens=250,
    )
    assert "effort" not in client._rpc.await_args_list[2].args[1]


def test_normalize_completed_turn_records_effort_in_the_forensic_payload():
    turn = {"status": "completed", "usage": {}}
    with_effort = normalize_completed_turn(turn, "ok", "gpt-5.6-luna", effort="high")
    assert with_effort["_provider_payload"]["effort"] == "high"
    without = normalize_completed_turn(turn, "ok", "gpt-5.6-luna")
    assert "effort" not in without["_provider_payload"]
