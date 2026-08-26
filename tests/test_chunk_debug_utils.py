"""Tests for chunk debug utility helpers."""

import pytest

import src.web.routes.debug as debug_module
from src.utils.llm_optimizer import GPT4O_INPUT_COST_PER_MILLION_TOKENS
from src.web.routes.debug import (
    _build_chunk_reason,
    _clear_chunk_debug_progress,
    _init_chunk_debug_progress,
    api_chunk_debug_progress,
    calculate_filtered_costs,
)

pytestmark = pytest.mark.unit


class _FakeRedis:
    """Minimal redis-py stand-in backed by a dict shared across instances,
    the same way distinct real connections share one Redis server. Values are
    stringified on write since real Redis hashes only store strings -- this
    exercises the int()/float()/bool(int()) parsing in _read_chunk_debug_progress
    exactly as the live path would."""

    def __init__(self, store: dict):
        self._store = store

    def hset(self, key, mapping):
        self._store[key] = {k: str(v) for k, v in mapping.items()}

    def expire(self, key, ttl):
        pass

    def hincrby(self, key, field, amount):
        current = int(self._store.get(key, {}).get(field, 0))
        self._store.setdefault(key, {})[field] = str(current + amount)

    def hgetall(self, key):
        return dict(self._store.get(key, {}))

    def delete(self, key):
        self._store.pop(key, None)

    def close(self):
        pass


@pytest.fixture
def fake_redis(monkeypatch):
    """Patches debug._redis_client so progress helpers use an in-process fake
    instead of a live Redis -- these are unit tests, not integration tests."""
    store: dict = {}
    monkeypatch.setattr(debug_module, "_redis_client", lambda: _FakeRedis(store))
    return store


class TestChunkDebugProgressEndpoint:
    """The Junk Filter Tuning loading modal polls this endpoint during a long
    analysis (article 7216: 1,250 chunks, 62s with no visible progress before
    this fix). Progress lives in Redis, not process memory, because the poll
    and the analysis can land on different uvicorn workers (--workers 2)."""

    async def test_no_entry_reports_not_in_progress(self, fake_redis):
        result = await api_chunk_debug_progress(article_id=999)
        assert result == {"in_progress": False, "processed_chunks": 0, "total_chunks": 0}

    async def test_existing_entry_is_reported_after_increments(self, fake_redis):
        _init_chunk_debug_progress(
            42,
            total_chunks=1250,
            chunk_limit_applied=True,
            concurrency_limit=4,
            per_chunk_timeout_seconds=12.0,
        )
        debug_module._redis_client().hincrby(debug_module._chunk_debug_progress_key(42), "processed_chunks", 150)

        result = await api_chunk_debug_progress(article_id=42)

        assert result["in_progress"] is True
        assert result["processed_chunks"] == 150
        assert result["total_chunks"] == 1250
        assert result["chunk_limit_applied"] is True
        assert result["concurrency_limit"] == 4
        assert result["per_chunk_timeout_seconds"] == 12.0

    async def test_different_article_ids_do_not_collide(self, fake_redis):
        _init_chunk_debug_progress(
            1, total_chunks=10, chunk_limit_applied=False, concurrency_limit=4, per_chunk_timeout_seconds=12.0
        )

        result = await api_chunk_debug_progress(article_id=2)

        assert result == {"in_progress": False, "processed_chunks": 0, "total_chunks": 0}

    async def test_clear_removes_the_entry(self, fake_redis):
        _init_chunk_debug_progress(
            7, total_chunks=10, chunk_limit_applied=False, concurrency_limit=4, per_chunk_timeout_seconds=12.0
        )
        _clear_chunk_debug_progress(7)

        result = await api_chunk_debug_progress(article_id=7)

        assert result["in_progress"] is False

    async def test_redis_unavailable_reports_not_in_progress_without_raising(self, monkeypatch):
        def _raise():
            raise ConnectionError("redis is down")

        monkeypatch.setattr(debug_module, "_redis_client", lambda: _raise())

        # init must not raise even though the client is unreachable
        _init_chunk_debug_progress(
            5, total_chunks=10, chunk_limit_applied=False, concurrency_limit=4, per_chunk_timeout_seconds=12.0
        )

        result = await api_chunk_debug_progress(article_id=5)
        assert result["in_progress"] is False


class TestBuildChunkReason:
    """A kept chunk's reason must never read as though it was removed, and
    should name the deciding feature when one is available (2026-08-20 dogfood
    finding: 'Content filtered successfully' on a kept chunk reads as removal)."""

    def test_kept_with_feature_contribution_names_top_feature(self):
        reason = _build_chunk_reason(
            is_huntable=True,
            feature_contribution={"cmdline_artifact_count": 0.9, "perfect_pattern_count": 0.4},
        )
        assert reason.lower().startswith("kept")
        assert "cmdline artifact count" in reason
        assert "not kept" not in reason.lower()

    def test_kept_without_feature_contribution_still_reads_as_kept(self):
        reason = _build_chunk_reason(is_huntable=True, feature_contribution=None)
        assert reason.lower().startswith("kept")
        assert "not kept" not in reason.lower()

    def test_removed_with_feature_contribution_names_top_feature(self):
        reason = _build_chunk_reason(
            is_huntable=False,
            feature_contribution={"atomic_ioc_density": 0.7, "sentence_count": 0.1},
        )
        assert reason.lower().startswith("not kept")
        assert "atomic ioc density" in reason

    def test_removed_without_feature_contribution_has_no_kept_prefix(self):
        reason = _build_chunk_reason(is_huntable=False, feature_contribution=None)
        assert reason.lower().startswith("not kept")

    def test_empty_feature_contribution_dict_falls_back_like_none(self):
        reason = _build_chunk_reason(is_huntable=True, feature_contribution={})
        assert reason == "Kept - huntable content detected"


def test_calculate_filtered_costs_reuses_filtered_tokens():
    """Cost estimation should use filtered token length and never exceed original."""
    estimate = calculate_filtered_costs(original_length=10000, filtered_length=4000)

    # Token estimates use 4 chars/token heuristic
    assert estimate["original_tokens"] == 2500
    assert estimate["filtered_tokens"] == 1000

    # Savings reflect the difference between original and filtered tokens, at
    # the shared GPT-4o input rate (not a hardcoded literal -- see
    # tests/unit/test_llm_optimizer_cost_rate.py for the dedup regression).
    expected_savings = (2500 - 1000) * (GPT4O_INPUT_COST_PER_MILLION_TOKENS / 1_000_000)
    assert estimate["tokens_saved"] == 1500
    assert abs(estimate["cost_savings"] - expected_savings) < 1e-9

    # Input cost should be based on filtered tokens plus prompt tokens
    expected_input_tokens = 1000 + estimate["prompt_tokens"]
    expected_input_cost = (expected_input_tokens / 1_000_000) * GPT4O_INPUT_COST_PER_MILLION_TOKENS
    assert estimate["input_tokens"] == expected_input_tokens
    assert abs(estimate["input_cost"] - expected_input_cost) < 1e-9
