"""Unit tests for the isolated Codex app-server adapter."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.services.codex_app_server_client import (
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
