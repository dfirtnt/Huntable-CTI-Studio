"""Tests for chunk debug utility helpers."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import src.web.routes.debug as debug_module
from src.utils.llm_optimizer import GPT4O_INPUT_COST_PER_MILLION_TOKENS
from src.web.routes.debug import (
    _PHASE_ANALYZING,
    _PHASE_FILTERING,
    _PHASE_FINALIZING,
    _build_chunk_reason,
    _clear_chunk_debug_progress,
    _init_chunk_debug_progress,
    _set_chunk_debug_phase,
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

    def hset(self, key, field=None, value=None, mapping=None):
        if mapping is not None:
            self._store[key] = {k: str(v) for k, v in mapping.items()}
        else:
            self._store.setdefault(key, {})[field] = str(value)

    def exists(self, key):
        return 1 if key in self._store else 0

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
            article_total_chunks=1250,
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
            1,
            total_chunks=10,
            article_total_chunks=10,
            chunk_limit_applied=False,
            concurrency_limit=4,
            per_chunk_timeout_seconds=12.0,
        )

        result = await api_chunk_debug_progress(article_id=2)

        assert result == {"in_progress": False, "processed_chunks": 0, "total_chunks": 0}

    async def test_clear_removes_the_entry(self, fake_redis):
        _init_chunk_debug_progress(
            7,
            total_chunks=10,
            article_total_chunks=10,
            chunk_limit_applied=False,
            concurrency_limit=4,
            per_chunk_timeout_seconds=12.0,
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
            5,
            total_chunks=10,
            article_total_chunks=10,
            chunk_limit_applied=False,
            concurrency_limit=4,
            per_chunk_timeout_seconds=12.0,
        )
        # nor must a phase update -- it runs on the same best-effort contract
        _set_chunk_debug_phase(5, _PHASE_ANALYZING)

        result = await api_chunk_debug_progress(article_id=5)
        assert result["in_progress"] is False

    async def test_phase_advances_through_the_three_stages(self, fake_redis):
        """Progress must describe the whole run, not just the per-chunk loop.

        Measured on article 7216 before this was fixed: a 64.9s run reported
        progress only from t+28.5s to t+35.6s -- 11% of the wall time. The
        expensive full-article filter_content() pass ran first with no
        instrumentation, and response assembly afterwards left the last chunk
        count frozen on screen, which reads as a hang.
        """
        _init_chunk_debug_progress(
            11,
            total_chunks=150,
            article_total_chunks=1250,
            chunk_limit_applied=True,
            concurrency_limit=4,
            per_chunk_timeout_seconds=12.0,
        )

        # Filtering: the article-wide total is known, no per-chunk counter yet.
        result = await api_chunk_debug_progress(article_id=11)
        assert result["phase"] == _PHASE_FILTERING
        assert result["article_total_chunks"] == 1250
        assert result["total_chunks"] == 150
        assert result["processed_chunks"] == 0

        _set_chunk_debug_phase(11, _PHASE_ANALYZING)
        debug_module._redis_client().hincrby(debug_module._chunk_debug_progress_key(11), "processed_chunks", 42)
        result = await api_chunk_debug_progress(article_id=11)
        assert result["phase"] == _PHASE_ANALYZING
        assert result["processed_chunks"] == 42
        assert result["article_total_chunks"] == 1250, "phase change must not disturb the counters"

        _set_chunk_debug_phase(11, _PHASE_FINALIZING)
        result = await api_chunk_debug_progress(article_id=11)
        assert result["phase"] == _PHASE_FINALIZING
        assert result["processed_chunks"] == 42

    async def test_phase_update_does_not_resurrect_a_cleared_run(self, fake_redis):
        """A late phase write must not recreate a zeroed record.

        hset creates a missing key, so without the existence guard a phase
        update arriving after the clear would report a finished analysis as
        freshly started -- an endless spinner on a run that already returned.
        """
        _init_chunk_debug_progress(
            12,
            total_chunks=10,
            article_total_chunks=10,
            chunk_limit_applied=False,
            concurrency_limit=4,
            per_chunk_timeout_seconds=12.0,
        )
        _clear_chunk_debug_progress(12)

        _set_chunk_debug_phase(12, _PHASE_FINALIZING)

        result = await api_chunk_debug_progress(article_id=12)
        assert result["in_progress"] is False


class _StubFilterResult:
    def __init__(self):
        self.removed_chunks = []
        self.filtered_content = "kept text"
        self.is_huntable = True
        self.confidence = 0.9
        self.cost_savings = 0.0


class _StubContentFilter:
    """Minimal stand-in for the live ContentFilter.

    ``model = None`` skips the sklearn branch and ``feature_version`` defaults to
    v1, so only ``extract_features`` is needed. ``on_full_filter`` fires on the
    first ``filter_content`` call -- the whole-article pass -- which is the moment
    the progress record has to already exist.
    """

    model = None

    def __init__(self, chunks, on_full_filter=None):
        self._chunks = chunks
        self._on_full_filter = on_full_filter
        self._filter_calls = 0

    def chunk_content(self, content, chunk_size, overlap):
        return self._chunks

    def filter_content(self, content, min_confidence, chunk_size, hunt_score):
        self._filter_calls += 1
        if self._filter_calls == 1 and self._on_full_filter is not None:
            self._on_full_filter()
        return _StubFilterResult()

    def extract_features(self, chunk_text, hunt_score, include_new_features=True):
        return {"cmdline_artifact_count": 0.0}


class TestChunkDebugProgressCoversTheWholeRun:
    """Guards the placement of the progress calls inside api_chunk_debug.

    The helper-level tests above pass just as happily with the reporting wrapped
    around the per-chunk loop only -- verified by re-introducing that exact
    regression, which left all of them green. What made the feature useless was
    *where* it was called from, so these drive the real handler instead.

    Measured on article 7216 (1,250 chunks) before the fix: a 64.9s run reported
    progress for 7.1s of it. filter_content() is a full sklearn pass over every
    chunk and ran before the reporting started; response assembly ran after it
    stopped, leaving a frozen chunk count on screen for the rest of the run.
    """

    @pytest.fixture
    def stub_article(self):
        return SimpleNamespace(
            content="chunk one text. chunk two text.",
            title="Stub Article",
            article_metadata={},
        )

    def _patch_deps(self, monkeypatch, content_filter, article):
        async def _get_article(article_id):
            return article

        monkeypatch.setattr(debug_module.async_db_manager, "get_article", _get_article)
        monkeypatch.setattr(debug_module, "get_content_filter", lambda: content_filter)

    async def test_progress_is_live_while_the_full_article_filter_runs(self, fake_redis, monkeypatch, stub_article):
        """The expensive pass must be inside the reported window, not before it.

        This is the whole defect: with the init below filter_content the operator
        watched a static spinner through the longest phase of the run.
        """
        observed = {}

        def _sample_progress():
            # Snapshot, not a reference: the fake stores one dict per key and the
            # handler keeps mutating it, so an alias would report the end state.
            live = fake_redis.get(debug_module._chunk_debug_progress_key(77))
            observed["during_filter"] = dict(live) if live is not None else None

        content_filter = _StubContentFilter(
            [(0, 15, "chunk one text."), (16, 31, "chunk two text.")],
            on_full_filter=_sample_progress,
        )
        self._patch_deps(monkeypatch, content_filter, stub_article)

        await debug_module.api_chunk_debug(article_id=77)

        during = observed.get("during_filter")
        assert during is not None, (
            "no progress record existed while filter_content was running -- the init "
            "has moved back below it, so the longest phase of the run reports nothing"
        )
        assert during["phase"] == _PHASE_FILTERING
        assert int(during["article_total_chunks"]) == 2

    async def test_progress_still_reports_while_the_response_is_assembled(self, fake_redis, monkeypatch, stub_article):
        """Reporting must outlive the chunk loop, not stop with it.

        estimate_gpt4o_cost runs after the loop, during response assembly -- the
        ~29s stretch on article 7216 that used to sit behind a frozen chunk count
        because the record was cleared as soon as the loop finished.
        """
        observed = {}
        real_estimate = debug_module.estimate_gpt4o_cost

        def _sampling_estimate(content, use_filtering=True):
            live = fake_redis.get(debug_module._chunk_debug_progress_key(80))
            observed["during_assembly"] = dict(live) if live is not None else None
            return real_estimate(content, use_filtering=use_filtering)

        monkeypatch.setattr(debug_module, "estimate_gpt4o_cost", _sampling_estimate)
        content_filter = _StubContentFilter([(0, 15, "chunk one text.")])
        self._patch_deps(monkeypatch, content_filter, stub_article)

        await debug_module.api_chunk_debug(article_id=80)

        during = observed.get("during_assembly")
        assert during is not None, (
            "progress was already cleared while the response was still being built -- "
            "the loading modal freezes on its last chunk count for the rest of the run"
        )
        assert during["phase"] == _PHASE_FINALIZING

    async def test_progress_is_cleared_once_the_handler_returns(self, fake_redis, monkeypatch, stub_article):
        """Cleared at the end of the handler, not at the end of the chunk loop.

        Clearing when the loop finished ended reporting while response assembly
        was still running, which froze the last count on screen.
        """
        content_filter = _StubContentFilter([(0, 15, "chunk one text.")])
        self._patch_deps(monkeypatch, content_filter, stub_article)

        await debug_module.api_chunk_debug(article_id=78)

        result = await api_chunk_debug_progress(article_id=78)
        assert result["in_progress"] is False
        assert debug_module._chunk_debug_progress_key(78) not in fake_redis

    async def test_a_failed_run_does_not_leave_progress_reporting_forever(self, fake_redis, monkeypatch, stub_article):
        """An error must clear too, or a dead run reports as live until its TTL."""

        class _Boom(_StubContentFilter):
            def filter_content(self, *a, **kw):
                raise RuntimeError("filter blew up")

        content_filter = _Boom([(0, 15, "chunk one text.")])
        self._patch_deps(monkeypatch, content_filter, stub_article)

        with pytest.raises(HTTPException):
            await debug_module.api_chunk_debug(article_id=79)

        result = await api_chunk_debug_progress(article_id=79)
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
