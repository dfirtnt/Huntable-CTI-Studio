"""Unit tests for workflow execution stream event shaping."""

import pytest

from src.web.routes.workflow_executions import _build_conversation_stream_events

pytestmark = pytest.mark.unit


def test_generate_sigma_generation_call_emits_llm_interaction_with_rule_counts():
    agent_log = {
        "conversation_log": [
            {
                "event_type": "generation_call",
                "generation_phase": "generation",
                "attempt": 1,
                "messages": [{"role": "user", "content": "Generate Sigma"}],
                "llm_response": "title: Test Rule",
                "generated_rule_count": 2,
                "valid_rule_count": 1,
                "invalid_rule_count": 1,
            }
        ]
    }

    events = _build_conversation_stream_events("generate_sigma", agent_log, {}, "2026-06-12T00:00:00")

    assert events == [
        {
            "type": "llm_interaction",
            "step": "generate_sigma",
            "agent": "generate_sigma",
            "messages": [{"role": "user", "content": "Generate Sigma"}],
            "response": "title: Test Rule",
            "attempt": 1,
            "timestamp": "2026-06-12T00:00:00",
            "generation_phase": "generation",
            "generated_rule_count": 2,
            "valid_rule_count": 1,
            "invalid_rule_count": 1,
        }
    ]


def test_generate_sigma_rule_validation_does_not_emit_empty_llm_interaction():
    agent_log = {
        "conversation_log": [
            {
                "event_type": "rule_validation",
                "rule_id": "rule-1",
                "generation_phase": "generation",
                "final_status": "valid",
                "repair_attempts": [],
                "validation": {"is_valid": True, "errors": [], "warnings": []},
            }
        ]
    }

    events = _build_conversation_stream_events("generate_sigma", agent_log, {}, "2026-06-12T00:00:00")

    assert events == []


def test_generate_sigma_events_skip_entries_already_seen():
    entry = {
        "event_type": "generation_call",
        "generation_phase": "generation",
        "attempt": 1,
        "messages": [{"role": "user", "content": "Generate Sigma"}],
        "llm_response": "title: Test Rule",
    }

    events = _build_conversation_stream_events(
        "generate_sigma",
        {"conversation_log": [entry]},
        {"conversation_log": [entry]},
        "2026-06-12T00:00:00",
    )

    assert events == []


def test_extract_agent_legacy_entry_still_emits_subagent_llm_interaction():
    agent_log = {
        "conversation_log": [
            {
                "agent": "CmdlineExtract",
                "items_count": 3,
                "messages": [{"role": "user", "content": "Extract commands"}],
                "llm_response": '{"cmdline_items": []}',
                "attempt": 1,
                "attention_preprocessor": {"enabled": True, "snippet_count": 4},
            }
        ]
    }

    events = _build_conversation_stream_events("extract_agent", agent_log, {}, "2026-06-12T00:00:00")

    assert len(events) == 1
    assert events[0]["type"] == "llm_interaction"
    assert events[0]["agent"] == "CmdlineExtract"
    assert events[0]["discrete_huntables_count"] == 3
    assert events[0]["attention_preprocessor"] == {"enabled": True, "snippet_count": 4}
