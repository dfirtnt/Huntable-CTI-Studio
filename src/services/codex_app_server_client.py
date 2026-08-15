"""Minimal, isolated Codex app-server adapter for workflow inference.

This adapter intentionally uses Codex-managed ChatGPT authentication rather
than exposing a subscription credential as an OpenAI API key. Each workflow
call gets an ephemeral, read-only Codex thread in a dedicated empty workspace.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


class CodexAppServerError(RuntimeError):
    """A Codex app-server request could not be completed."""


# asyncio's default StreamReader limit is 64 KiB. Codex echoes turn input back in
# `item/completed` / `turn/completed` notifications, so a large SIGMA prompt produces a
# single JSON-RPC line well past that and readline() fails the whole turn.
CODEX_STREAM_LIMIT = 16 * 1024 * 1024


def codex_workspace() -> Path:
    """Return the isolated workspace used by subscription-backed workflow turns."""
    workspace = Path("/tmp/huntable-codex-workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def codex_command() -> list[str]:
    """Return the fixed Codex app-server command installed in the worker image."""
    return ["codex", "app-server"]


def messages_to_codex_input(messages: list[dict[str, Any]], max_tokens: int) -> list[dict[str, str]]:
    """Flatten the existing chat contract into one instruction-preserving user turn."""
    parts = [
        "You are a text-only workflow inference engine.",
        "Return only the requested answer. Do not call tools, run commands, read files, or change files.",
        f"Keep the response within approximately {max_tokens} output tokens.",
    ]
    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        content = str(message.get("content") or "")
        if content:
            parts.append(f"<{role}>\n{content}\n</{role}>")
    return [{"type": "text", "text": "\n\n".join(parts)}]


def normalize_completed_turn(turn: dict[str, Any], agent_text: str, model_name: str) -> dict[str, Any]:
    """Map Codex turn events into the OpenAI-compatible shape LLMService consumes."""
    if turn.get("status") != "completed":
        error = turn.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else None
        raise CodexAppServerError(message or f"Codex turn ended with status '{turn.get('status')}'.")
    if not agent_text.strip():
        raise CodexAppServerError("Codex completed without an agent message.")

    usage = turn.get("usage") if isinstance(turn.get("usage"), dict) else {}
    return {
        "choices": [{"message": {"content": agent_text}}],
        "usage": {
            "prompt_tokens": usage.get("inputTokens", usage.get("prompt_tokens", 0)),
            "completion_tokens": usage.get("outputTokens", usage.get("completion_tokens", 0)),
            "total_tokens": usage.get("totalTokens", usage.get("total_tokens", 0)),
        },
        "model": model_name,
        "_provider_payload": {"input": "Codex app-server turn", "model": model_name},
        "_provider_url": "codex-app-server://local",
    }


class CodexAppServerClient:
    """One ephemeral, read-only Codex app-server session per workflow request."""

    def __init__(self, *, timeout: float):
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending_notifications: list[dict[str, Any]] = []

    async def read_account(self) -> dict[str, Any]:
        """Return non-secret account metadata from Codex-managed authentication."""
        await self._start()
        try:
            async with asyncio.timeout(self.timeout):
                await self._rpc(
                    "initialize",
                    {
                        "clientInfo": {"name": "huntable-cti-studio", "version": "1"},
                        "capabilities": {},
                    },
                )
                return await self._rpc("account/read", {})
        except TimeoutError as exc:
            raise CodexAppServerError(f"Codex app-server timed out after {self.timeout:.0f}s.") from exc
        finally:
            await self._close()

    async def list_models(self) -> list[str]:
        """Return this ChatGPT subscription's visible Codex models, default first."""
        await self._start()
        try:
            async with asyncio.timeout(self.timeout):
                await self._rpc(
                    "initialize",
                    {
                        "clientInfo": {"name": "huntable-cti-studio", "version": "1"},
                        "capabilities": {},
                    },
                )
                result = await self._rpc("model/list", {})
        except TimeoutError as exc:
            raise CodexAppServerError(f"Codex app-server timed out after {self.timeout:.0f}s.") from exc
        finally:
            await self._close()

        models = result.get("data") if isinstance(result, dict) else None
        if not isinstance(models, list):
            return []
        visible = [
            item
            for item in models
            if isinstance(item, dict)
            and not item.get("hidden")
            and isinstance(item.get("model") or item.get("id"), str)
        ]
        visible.sort(key=lambda item: not bool(item.get("isDefault")))
        default_model = next((str(item.get("model") or item["id"]) for item in visible if item.get("isDefault")), "")
        # Codex keeps older models visible during a migration. Present the current
        # default family instead, so a ChatGPT subscription picker does not offer
        # deprecated models merely because they remain temporarily runnable.
        family = default_model.rsplit("-", 1)[0] if "-" in default_model else default_model
        current_models = [
            item
            for item in visible
            if not family
            or str(item.get("model") or item["id"]) in {family, default_model}
            or str(item.get("model") or item["id"]).startswith(f"{family}-")
        ]
        return list(dict.fromkeys(str(item.get("model") or item["id"]) for item in current_models))

    async def complete(self, *, messages: list[dict[str, Any]], model_name: str, max_tokens: int) -> dict[str, Any]:
        workspace = await self._start()
        try:
            async with asyncio.timeout(self.timeout):
                await self._rpc(
                    "initialize",
                    {
                        "clientInfo": {"name": "huntable-cti-studio", "version": "1"},
                        "capabilities": {},
                    },
                )
                thread_result = await self._rpc(
                    "thread/start",
                    {
                        "model": model_name,
                        "cwd": str(workspace),
                        "approvalPolicy": "never",
                        # Codex app-server uses kebab-case enum values. This keeps
                        # the subscription thread isolated without allowing writes.
                        "sandbox": "read-only",
                        "ephemeral": True,
                    },
                )
                thread = thread_result.get("thread") if isinstance(thread_result, dict) else None
                thread_id = thread.get("id") if isinstance(thread, dict) else None
                if not thread_id:
                    raise CodexAppServerError("Codex app-server did not return a thread id.")
                await self._rpc(
                    "turn/start",
                    {"threadId": thread_id, "input": messages_to_codex_input(messages, max_tokens)},
                )
                return await self._read_completed_turn(model_name)
        except TimeoutError as exc:
            raise CodexAppServerError(f"Codex app-server timed out after {self.timeout:.0f}s.") from exc
        finally:
            await self._close()

    async def _start(self) -> Path:
        workspace = codex_workspace()
        self.process = await asyncio.create_subprocess_exec(
            *codex_command(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
            limit=CODEX_STREAM_LIMIT,
        )
        return workspace

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = await self._read_message()
            if message.get("id") != request_id:
                if "method" in message:
                    self._pending_notifications.append(message)
                continue
            if "error" in message:
                error = message["error"]
                raise CodexAppServerError(error.get("message", "Codex app-server RPC failed."))
            result = message.get("result")
            return result if isinstance(result, dict) else {}

    async def _read_completed_turn(self, model_name: str) -> dict[str, Any]:
        agent_text = ""
        while True:
            message = self._pending_notifications.pop(0) if self._pending_notifications else await self._read_message()
            if message.get("method") == "item/completed":
                item = (message.get("params") or {}).get("item") or {}
                if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                    agent_text = item["text"]
            if message.get("method") == "turn/completed":
                turn = (message.get("params") or {}).get("turn") or {}
                if not agent_text:
                    for item in turn.get("items") or []:
                        if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                            agent_text = item["text"]
                return normalize_completed_turn(turn, agent_text, model_name)

    async def _send(self, payload: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise CodexAppServerError("Codex app-server is not running.")
        self.process.stdin.write((json.dumps(payload) + "\n").encode())
        await self.process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise CodexAppServerError("Codex app-server is not running.")
        try:
            line = await self.process.stdout.readline()
        except ValueError as exc:
            # asyncio's StreamReader raises ValueError once a single JSON-RPC line exceeds
            # the stream limit ("Separator is found, but chunk is longer than limit").
            raise CodexAppServerError(
                f"Codex app-server emitted a JSON-RPC line larger than the {CODEX_STREAM_LIMIT}-byte "
                "stdout buffer. Reduce the prompt size or raise CODEX_STREAM_LIMIT."
            ) from exc
        if not line:
            stderr = ""
            if self.process.stderr:
                stderr = (await self.process.stderr.read()).decode(errors="replace").strip()
            raise CodexAppServerError(f"Codex app-server exited unexpectedly. {stderr}".strip())
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexAppServerError("Codex app-server emitted invalid JSON-RPC output.") from exc
        if not isinstance(message, dict):
            raise CodexAppServerError("Codex app-server emitted an invalid JSON-RPC message.")
        return message

    async def _close(self) -> None:
        if not self.process or self.process.returncode is not None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=2)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()
