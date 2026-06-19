"""Unit tests for the Phase B LLM platform adjudicator.

The adjudicator runs ONLY on the low-confidence / Unknown tail left by the
deterministic KB gate (Phase A). The LLM call is dependency-injected so these
tests are deterministic and make no network/LLM calls.

See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (§6).
"""

import pytest

from src.services.platform_adjudicator import (
    adjudicate_platforms,
    build_adjudication_messages,
    parse_adjudication_response,
)

pytestmark = [pytest.mark.unit]


def test_parse_single_platform():
    r = parse_adjudication_response('{"platforms": ["Linux"], "confidence": "high", "evidence": ["systemd unit"]}')
    assert r.platforms == ["linux"]
    assert r.primary == "linux"
    assert r.confidence == "high"
    assert r.method == "llm_adjudication"


def test_parse_multi_platform():
    r = parse_adjudication_response('{"platforms": ["Windows", "Linux"], "confidence": "medium"}')
    assert set(r.platforms) == {"windows", "linux"}
    assert r.confidence == "medium"


def test_parse_strips_markdown_fence():
    text = '```json\n{"platforms": ["macOS"], "confidence": "high"}\n```'
    r = parse_adjudication_response(text)
    assert r.platforms == ["macos"]


def test_parse_normalizes_aliases():
    r = parse_adjudication_response('{"platforms": ["win", "darwin"], "confidence": "medium"}')
    assert set(r.platforms) == {"windows", "macos"}


def test_parse_unknown_yields_no_platform():
    r = parse_adjudication_response('{"platforms": ["unknown"], "confidence": "low"}')
    assert r.platforms == []
    assert r.primary == "unknown"
    assert r.confidence == "low"


def test_parse_empty_platforms_is_unknown():
    r = parse_adjudication_response('{"platforms": [], "confidence": "low"}')
    assert r.platforms == []
    assert r.primary == "unknown"


def test_parse_malformed_response_is_unknown_not_crash():
    r = parse_adjudication_response("the model rambled without any JSON")
    assert r.platforms == []
    assert r.primary == "unknown"
    assert r.confidence == "low"


def test_build_messages_includes_vocab_and_truncates():
    content = "x" * 50000
    messages = build_adjudication_messages(content, max_chars=8000)
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    blob = messages[0]["content"] + messages[1]["content"]
    for label in ("Windows", "Linux", "macOS"):
        assert label in blob
    # content excerpt is bounded
    assert len(messages[1]["content"]) < 9000


@pytest.mark.asyncio
async def test_adjudicate_success_returns_classification():
    async def fake_llm(messages):
        return '{"platforms": ["Linux"], "confidence": "high", "evidence": ["/etc/systemd"]}'

    r = await adjudicate_platforms("a Linux article", llm_call=fake_llm)
    assert r.platforms == ["linux"]
    assert r.method == "llm_adjudication"


@pytest.mark.asyncio
async def test_adjudicate_llm_error_returns_unknown():
    async def boom(messages):
        raise RuntimeError("provider down")

    r = await adjudicate_platforms("content", llm_call=boom)
    assert r.platforms == []
    assert r.primary == "unknown"
    assert r.confidence == "low"


@pytest.mark.asyncio
async def test_adjudicate_result_maps_to_os_result_shape():
    async def fake_llm(messages):
        return '{"platforms": ["Linux"], "confidence": "high"}'

    res = (await adjudicate_platforms("c", llm_call=fake_llm)).as_os_result()
    assert res["operating_system"] == "Linux"
    assert res["method"] == "llm_adjudication"
    assert res["platforms_detected"] == ["Linux"]
