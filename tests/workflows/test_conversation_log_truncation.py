"""Tests for conversation log truncation in agentic_workflow.

The live-view SSE stream reads truncated messages from the conversation log.
Message content is capped at 3000 chars and response at 2000 chars to prevent
JSONB bloat from storing the full article content per agent.

Since the truncation logic is inline in the extract_agent step (not a standalone
function), these tests replicate the exact truncation logic and verify its
behavior against various edge cases.
"""

import pytest

pytestmark = pytest.mark.unit

# Match the constants from agentic_workflow.py (lines 1692-1693)
_MAX_MSG_CHARS = 3000
_MAX_RESP_CHARS = 2000


def _truncate_messages(llm_messages: list) -> list:
    """Replicate the truncation logic from agentic_workflow.py lines 1697-1706."""
    truncated = []
    for _m in llm_messages:
        if isinstance(_m, dict):
            _c = _m.get("content", "")
            truncated.append({**_m, "content": _c[:_MAX_MSG_CHARS] + "…"} if len(_c) > _MAX_MSG_CHARS else _m)
        else:
            truncated.append(_m)
    return truncated


def _truncate_response(llm_response: str) -> str:
    """Replicate the truncation logic from agentic_workflow.py line 1709."""
    return llm_response[:_MAX_RESP_CHARS] + "…" if len(llm_response) > _MAX_RESP_CHARS else llm_response


def _build_log_entry(agent_name: str, items_count: int, agent_result: dict) -> dict:
    """Replicate the full log entry building from agentic_workflow.py lines 1694-1713."""
    log_entry: dict = {"agent": agent_name, "items_count": items_count, "result": agent_result}
    if isinstance(agent_result, dict):
        if "_llm_messages" in agent_result:
            log_entry["messages"] = _truncate_messages(agent_result["_llm_messages"])
        if "_llm_response" in agent_result:
            log_entry["llm_response"] = _truncate_response(agent_result["_llm_response"])
        if "_llm_attempt" in agent_result:
            log_entry["attempt"] = agent_result["_llm_attempt"]
        if "_attention_preprocessor" in agent_result:
            log_entry["attention_preprocessor"] = agent_result["_attention_preprocessor"]
    return log_entry


# ===========================================================================
# Message truncation
# ===========================================================================


class TestMessageTruncation:
    """LLM message content is truncated at _MAX_MSG_CHARS."""

    def test_long_message_truncated(self):
        msgs = [{"role": "user", "content": "x" * 5000}]
        result = _truncate_messages(msgs)
        assert len(result[0]["content"]) == _MAX_MSG_CHARS + 1  # +1 for ellipsis char
        assert result[0]["content"].endswith("…")

    def test_short_message_preserved(self):
        msgs = [{"role": "system", "content": "You are a helpful agent."}]
        result = _truncate_messages(msgs)
        assert result[0]["content"] == "You are a helpful agent."

    def test_exact_limit_not_truncated(self):
        content = "x" * _MAX_MSG_CHARS
        msgs = [{"role": "user", "content": content}]
        result = _truncate_messages(msgs)
        assert result[0]["content"] == content
        assert "…" not in result[0]["content"]

    def test_one_over_limit_truncated(self):
        content = "x" * (_MAX_MSG_CHARS + 1)
        msgs = [{"role": "user", "content": content}]
        result = _truncate_messages(msgs)
        assert result[0]["content"][-1] == "…"
        assert len(result[0]["content"]) == _MAX_MSG_CHARS + 1

    def test_multiple_messages_independent_truncation(self):
        msgs = [
            {"role": "system", "content": "short"},
            {"role": "user", "content": "y" * 5000},
        ]
        result = _truncate_messages(msgs)
        assert result[0]["content"] == "short"
        assert len(result[1]["content"]) == _MAX_MSG_CHARS + 1

    def test_non_dict_messages_preserved(self):
        """String messages (legacy format) pass through unchanged."""
        msgs = [{"role": "user", "content": "normal"}, "raw string message"]
        result = _truncate_messages(msgs)
        assert result[1] == "raw string message"

    def test_message_other_fields_preserved(self):
        """Truncation only affects content; role and other keys preserved."""
        msgs = [{"role": "user", "content": "x" * 5000, "name": "test_agent"}]
        result = _truncate_messages(msgs)
        assert result[0]["role"] == "user"
        assert result[0]["name"] == "test_agent"

    def test_empty_content_preserved(self):
        msgs = [{"role": "user", "content": ""}]
        result = _truncate_messages(msgs)
        assert result[0]["content"] == ""

    def test_missing_content_key_safe(self):
        msgs = [{"role": "system"}]
        result = _truncate_messages(msgs)
        # .get("content", "") returns "", which is <= limit
        assert result[0] == {"role": "system"}


# ===========================================================================
# Response truncation
# ===========================================================================


class TestResponseTruncation:
    """LLM response is truncated at _MAX_RESP_CHARS."""

    def test_long_response_truncated(self):
        resp = "z" * 4000
        result = _truncate_response(resp)
        assert len(result) == _MAX_RESP_CHARS + 1
        assert result.endswith("…")

    def test_short_response_preserved(self):
        resp = '{"registry_artifacts": [], "count": 0}'
        result = _truncate_response(resp)
        assert result == resp

    def test_exact_limit_not_truncated(self):
        resp = "z" * _MAX_RESP_CHARS
        result = _truncate_response(resp)
        assert result == resp

    def test_empty_response_preserved(self):
        assert _truncate_response("") == ""


# ===========================================================================
# Full log entry building
# ===========================================================================


class TestLogEntryBuilding:
    """Full log entry construction with truncation."""

    def test_log_entry_basic_structure(self):
        result = {"items": [1, 2], "count": 2}
        entry = _build_log_entry("RegistryExtract", 2, result)
        assert entry["agent"] == "RegistryExtract"
        assert entry["items_count"] == 2
        assert "messages" not in entry  # no _llm_messages key

    def test_log_entry_with_llm_fields(self):
        result = {
            "items": [],
            "count": 0,
            "_llm_messages": [{"role": "user", "content": "short"}],
            "_llm_response": '{"registry_artifacts": []}',
            "_llm_attempt": 1,
        }
        entry = _build_log_entry("RegistryExtract", 0, result)
        assert entry["messages"] == [{"role": "user", "content": "short"}]
        assert entry["llm_response"] == '{"registry_artifacts": []}'
        assert entry["attempt"] == 1

    def test_log_entry_truncates_large_content(self):
        result = {
            "items": [],
            "count": 0,
            "_llm_messages": [{"role": "user", "content": "x" * 10000}],
            "_llm_response": "z" * 5000,
        }
        entry = _build_log_entry("CmdlineExtract", 0, result)
        assert len(entry["messages"][0]["content"]) == _MAX_MSG_CHARS + 1
        assert len(entry["llm_response"]) == _MAX_RESP_CHARS + 1

    def test_log_entry_original_result_untouched(self):
        """Truncation in log_entry doesn't modify the original agent_result."""
        original_content = "x" * 10000
        result = {
            "_llm_messages": [{"role": "user", "content": original_content}],
            "_llm_response": "z" * 5000,
        }
        _build_log_entry("RegistryExtract", 0, result)
        # Original should be untouched
        assert len(result["_llm_messages"][0]["content"]) == 10000
        assert len(result["_llm_response"]) == 5000

    def test_attention_preprocessor_propagated(self):
        result = {
            "_attention_preprocessor": {"snippets": 5},
        }
        entry = _build_log_entry("CmdlineExtract", 3, result)
        assert entry["attention_preprocessor"] == {"snippets": 5}

    def test_non_dict_result_handled(self):
        """If agent_result is not a dict (edge case), log_entry still works."""
        entry = _build_log_entry("RegistryExtract", 0, "error string")
        assert entry["agent"] == "RegistryExtract"
        assert entry["result"] == "error string"
        assert "messages" not in entry
