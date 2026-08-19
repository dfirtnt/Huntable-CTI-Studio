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
                    {"model": "gpt-5.5", "hidden": False, "isDefault": False},
                ]
            },
        ]
    )

    assert await client.list_models() == ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]


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
