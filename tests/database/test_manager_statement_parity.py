"""Sync/async manager statement parity drift-guard.

DatabaseManager and AsyncDatabaseManager execute the SAME shared statements
from src/database/statements.py. These tests capture the statement each
manager actually passes to session.execute() and compare the compiled SQL,
so any reintroduced per-manager query logic fails here immediately.

Fake sessions follow the pattern in tests/test_async_manager_source_filter_compat.py.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from src.database.async_manager import AsyncDatabaseManager
from src.database.manager import DatabaseManager
from src.models.article import ArticleListFilter


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class _FakeResult:
    """Covers every result-access pattern the managers use on empty rows."""

    def all(self):
        return []

    def unique(self):
        return self

    def scalars(self):
        return self

    def first(self):
        return None

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return 0


class _RecordingSyncSession:
    def __init__(self, captured: list):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, stmt):
        self._captured.append(stmt)
        return _FakeResult()


class _RecordingAsyncSession:
    def __init__(self, captured: list):
        self._captured = captured

    async def execute(self, stmt):
        self._captured.append(stmt)
        return _FakeResult()


def _make_sync_manager(captured: list) -> DatabaseManager:
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr.get_session = lambda: _RecordingSyncSession(captured)
    return mgr


def _make_async_manager(captured: list) -> AsyncDatabaseManager:
    mgr = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

    @asynccontextmanager
    async def _fake_get_session():
        yield _RecordingAsyncSession(captured)

    mgr.get_session = _fake_get_session
    return mgr


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_articles_same_filter_produces_identical_sql():
    """The core drift-guard: same filter in, same statement out, both sides."""
    article_filter = ArticleListFilter(
        source_id=3,
        processing_status="pending",
        sort_by="published_at",
        sort_order="desc",
        limit=25,
        offset=5,
    )

    sync_stmts: list = []
    _make_sync_manager(sync_stmts).list_articles(article_filter)

    async_stmts: list = []
    await _make_async_manager(async_stmts).list_articles(article_filter)

    assert sync_stmts and async_stmts
    assert _sql(sync_stmts[0]) == _sql(async_stmts[0])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_articles_no_filter_diverges_only_in_default_sort():
    """The one intentional divergence: CLI sorts published_at, web discovered_at."""
    sync_stmts: list = []
    _make_sync_manager(sync_stmts).list_articles()

    async_stmts: list = []
    await _make_async_manager(async_stmts).list_articles()

    sync_sql, async_sql = _sql(sync_stmts[0]), _sql(async_stmts[0])
    assert "articles.published_at DESC" in sync_sql
    assert "articles.discovered_at DESC" in async_sql
    assert sync_sql.replace("published_at DESC", "X") == async_sql.replace("discovered_at DESC", "X")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_sources_same_filter_produces_identical_sql():
    source_filter = SimpleNamespace(active=True, identifier="msrc")

    sync_stmts: list = []
    _make_sync_manager(sync_stmts).list_sources(source_filter)

    async_stmts: list = []
    await _make_async_manager(async_stmts).list_sources(source_filter)

    assert _sql(sync_stmts[0]) == _sql(async_stmts[0])
    assert "ORDER BY sources.name" in _sql(sync_stmts[0])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_existing_urls_produces_identical_sql():
    sync_stmts: list = []
    _make_sync_manager(sync_stmts).get_existing_urls(limit=1234)

    async_stmts: list = []
    await _make_async_manager(async_stmts).get_existing_urls(limit=1234)

    assert _sql(sync_stmts[0]) == _sql(async_stmts[0])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_existing_content_hashes_produces_identical_sql():
    """Regression: the sync manager used to read the content_hashes ledger
    (written only by the sync bulk path -- ~5% of the corpus) while async read
    articles.content_hash. Canonicalized on the articles table."""
    sync_stmts: list = []
    _make_sync_manager(sync_stmts).get_existing_content_hashes(limit=1234)

    async_stmts: list = []
    await _make_async_manager(async_stmts).get_existing_content_hashes(limit=1234)

    sync_sql = _sql(sync_stmts[0])
    assert sync_sql == _sql(async_stmts[0])
    assert "articles.content_hash" in sync_sql
    assert "content_hashes" not in sync_sql


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_article_archived_divergence_is_manager_level():
    """Sync get_article excludes archived rows; async includes them (web article
    detail must render archived articles). Pinned at the manager level so a
    silent flag flip in either manager fails here, not just in builder tests."""
    sync_stmts: list = []
    _make_sync_manager(sync_stmts).get_article(7)
    assert "archived = false" in _sql(sync_stmts[0])

    sync_stmts_incl: list = []
    _make_sync_manager(sync_stmts_incl).get_article_including_archived(7)
    assert "archived = false" not in _sql(sync_stmts_incl[0])

    async_stmts: list = []
    await _make_async_manager(async_stmts).get_article(7)
    assert "archived = false" not in _sql(async_stmts[0])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_articles_count_uses_shared_filter_logic():
    """Count and list share _apply_article_filters, so pagination totals can
    never disagree with page contents about what a filter means."""
    async_stmts: list = []
    await _make_async_manager(async_stmts).get_articles_count(source_id=5, processing_status="pending")

    sql = _sql(async_stmts[0])
    assert "count" in sql
    assert "articles.source_id" in sql and "articles.processing_status" in sql
    assert sql.count("archived = false") == 1


class _RowcountSyncSession(_RecordingSyncSession):
    def __init__(self, captured: list, rowcount: int):
        super().__init__(captured)
        self._rowcount = rowcount

    def execute(self, stmt):
        self._captured.append(stmt)
        result = _FakeResult()
        result.rowcount = self._rowcount
        return result

    def commit(self):
        pass


@pytest.mark.unit
def test_sync_update_article_embedding_returns_rowcount_truth():
    """Sync semantics: True only when a row was actually updated."""
    hit = DatabaseManager.__new__(DatabaseManager)
    hit.get_session = lambda: _RowcountSyncSession([], rowcount=1)
    assert hit.update_article_embedding(1, [0.1], "m") is True

    miss = DatabaseManager.__new__(DatabaseManager)
    miss.get_session = lambda: _RowcountSyncSession([], rowcount=0)
    assert miss.update_article_embedding(999999, [0.1], "m") is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_article_embedding_returns_true_on_success():
    """Async semantics preserved: True on successful execute+commit regardless
    of row match (legacy behavior the embedding worker relies on)."""
    captured: list = []
    mgr = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

    class _CommittingAsyncSession(_RecordingAsyncSession):
        async def commit(self):
            pass

    @asynccontextmanager
    async def _fake_get_session():
        yield _CommittingAsyncSession(captured)

    mgr.get_session = _fake_get_session

    assert await mgr.update_article_embedding(1, [0.1], "m") is True
    assert "UPDATE articles" in _sql(captured[0])


@pytest.mark.unit
def test_sync_list_articles_accepts_pydantic_filter_with_limit():
    """Regression: ArticleListFilter previously lacked limit/offset/author/tag,
    so the sync manager raised AttributeError for every CLI-built filter
    (export/search were dead). The filter now carries the full union."""
    captured: list = []
    mgr = _make_sync_manager(captured)

    result = mgr.list_articles(ArticleListFilter(limit=10, author="alice", tag="apt"))

    assert result == []
    sql = _sql(captured[0])
    assert "LIMIT" in sql
    assert "articles.authors" in sql and "articles.tags" in sql


@pytest.mark.unit
def test_sync_list_articles_propagates_db_errors():
    """Sync error semantics: exceptions propagate to the CLI caller."""

    class _ErrorSession(_RecordingSyncSession):
        def execute(self, stmt):
            raise RuntimeError("simulated DB error")

    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr.get_session = lambda: _ErrorSession([])

    with pytest.raises(RuntimeError, match="simulated DB error"):
        mgr.list_articles()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_list_articles_propagates_db_errors():
    """Async error semantics now match the sync manager: exceptions propagate.

    Previously this returned [], which made a broken database look like an
    empty result and rendered "no articles" instead of an error. Every caller
    wraps list_articles in its own handler and turns the raised error into an
    HTTP 500 or error.html."""

    class _ErrorAsyncSession(_RecordingAsyncSession):
        async def execute(self, stmt):
            raise RuntimeError("simulated DB error")

    mgr = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

    @asynccontextmanager
    async def _fake_get_session():
        yield _ErrorAsyncSession([])

    mgr.get_session = _fake_get_session

    with pytest.raises(RuntimeError, match="simulated DB error"):
        await mgr.list_articles()
