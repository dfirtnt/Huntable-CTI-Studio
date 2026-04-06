"""Regression tests for collect_from_source task behavior."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.models.article import ArticleCreate
from src.models.source import Source


def _import_celery_app():
    """Import celery_app with worker task modules mocked."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }

    with patch.dict(sys.modules, mocks):
        return importlib.import_module("src.worker.celery_app")


def _build_source() -> Source:
    now = datetime.now(UTC)
    return Source(
        id=25,
        identifier="dfir_report",
        name="The DFIR Report",
        url="https://thedfirreport.com",
        rss_url="https://thedfirreport.com/feed/",
        check_frequency=3600,
        lookback_days=999,
        active=True,
        config={"min_content_length": 2000, "archive_pages": True, "max_archive_pages": 20},
        last_check=None,
        last_success=None,
        consecutive_failures=0,
        total_articles=11,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


def _article(url: str, title: str) -> ArticleCreate:
    now = datetime.now(UTC)
    return ArticleCreate(
        title=title,
        canonical_url=url,
        content=f"content for {title}",
        source_id=25,
        published_at=now,
        modified_at=None,
        authors=[],
        tags=[],
        summary=None,
        article_metadata={},
        content_hash=None,
    )


@dataclass
class _DedupResult:
    unique_articles: list[ArticleCreate]
    duplicates: list[ArticleCreate]
    stats: dict


@dataclass
class _FetchResult:
    success: bool
    articles: list[ArticleCreate]
    method: str
    response_time: float
    rss_parsing_stats: dict
    error: str | None = None


class _FakeContentProcessor:
    """Capture init args and pass through fetched articles as unique."""

    last_init_kwargs: dict = {}

    def __init__(self, similarity_threshold: float, max_age_days: int, enable_content_enhancement: bool):
        self.__class__.last_init_kwargs = {
            "similarity_threshold": similarity_threshold,
            "max_age_days": max_age_days,
            "enable_content_enhancement": enable_content_enhancement,
        }

    async def process_articles(self, real_articles: list[ArticleCreate], existing_hashes: set[str]) -> _DedupResult:
        del existing_hashes
        return _DedupResult(
            unique_articles=list(real_articles),
            duplicates=[],
            stats={
                "quality_filtered": 0,
                "hash_duplicates": 0,
                "url_duplicates": 0,
                "similarity_duplicates": 0,
                "validation_failures": 0,
            },
        )


class _FakeContentFetcher:
    """Return deterministic fetch results without network access."""

    def __init__(self):
        self._articles = [
            _article("https://thedfirreport.com/post-1", "Post 1"),
            _article("https://thedfirreport.com/post-2", "Post 2"),
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        del exc_type, exc, tb
        return False

    async def fetch_source(self, source: Source) -> _FetchResult:
        assert source.lookback_days == 999
        assert source.active is True
        return _FetchResult(
            success=True,
            articles=list(self._articles),
            method="rss+basic_scraping",
            response_time=0.25,
            rss_parsing_stats={"total_entries": 10, "parsed_successfully": 10},
        )


class _FakeSessionCtx:
    def __enter__(self):
        return SimpleNamespace()

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        del exc_type, exc, tb
        return False


class _FakeDatabaseManager:
    """Minimal DB manager behavior used by collect_from_source."""

    source_template: Source | None = None
    last_instance: _FakeDatabaseManager | None = None

    def __init__(self):
        if self.__class__.source_template is None:
            raise RuntimeError("source_template must be set before constructing fake DB manager")
        self.source = self.__class__.source_template.model_copy(deep=True)
        self.persisted_articles: list[ArticleCreate] = []
        self.health_updates: list[dict] = []
        self.source_checks: list[dict] = []
        self.__class__.last_instance = self

    def get_source(self, source_id: int) -> Source | None:
        if source_id != self.source.id:
            return None
        return self.source

    def get_existing_content_hashes(self, limit: int = 10000) -> set[str]:
        del limit
        return set()

    def create_articles_bulk(self, articles: list[ArticleCreate]) -> tuple[list[ArticleCreate], list[str]]:
        self.persisted_articles.extend(articles)
        return list(articles), []

    def update_source_health(self, source_id: int, success: bool, response_time: float = 0.0) -> None:
        self.health_updates.append({"source_id": source_id, "success": success, "response_time": response_time})

    def get_session(self) -> _FakeSessionCtx:
        return _FakeSessionCtx()

    def _update_source_article_count(self, session, source_id: int) -> None:  # noqa: ANN001
        del session, source_id
        self.source.total_articles = len(self.persisted_articles)

    def record_source_check(self, **kwargs) -> None:
        self.source_checks.append(kwargs)

    # Guard against accidental mutation paths.
    def update_source(self, source_id: int, update_data):  # noqa: ANN001
        raise AssertionError(
            f"collect_from_source should not call update_source (source_id={source_id}, data={update_data})"
        )


def _call_collect_task(mod, source_id: int):
    """Handle either plain function or Celery Task wrapper."""
    task = mod.collect_from_source
    if hasattr(task, "run"):
        return task.run(source_id)  # pragma: no cover - depends on celery wrapper implementation
    return task(MagicMock(), source_id)


def test_collect_from_source_preserves_active_and_lookback_state():
    """Collection run must not mutate source active/lookback configuration."""
    mod = _import_celery_app()

    _FakeDatabaseManager.source_template = _build_source()
    _FakeDatabaseManager.last_instance = None
    _FakeContentProcessor.last_init_kwargs = {}

    with patch.dict(
        sys.modules,
        {
            "src.database.manager": SimpleNamespace(DatabaseManager=_FakeDatabaseManager),
            "src.core.fetcher": SimpleNamespace(ContentFetcher=_FakeContentFetcher),
            "src.core.processor": SimpleNamespace(ContentProcessor=_FakeContentProcessor),
        },
    ):
        result = _call_collect_task(mod, 25)

    db = _FakeDatabaseManager.last_instance
    assert db is not None
    assert result["status"] == "success"
    assert db.source.active is True
    assert db.source.lookback_days == 999
    assert _FakeContentProcessor.last_init_kwargs["max_age_days"] == 999
    assert db.health_updates and db.health_updates[-1]["success"] is True


def test_collect_from_source_keeps_total_articles_in_sync_with_saved_rows():
    """After collection finalization, total_articles should match persisted non-archived rows."""
    mod = _import_celery_app()

    _FakeDatabaseManager.source_template = _build_source()
    _FakeDatabaseManager.last_instance = None

    with patch.dict(
        sys.modules,
        {
            "src.database.manager": SimpleNamespace(DatabaseManager=_FakeDatabaseManager),
            "src.core.fetcher": SimpleNamespace(ContentFetcher=_FakeContentFetcher),
            "src.core.processor": SimpleNamespace(ContentProcessor=_FakeContentProcessor),
        },
    ):
        result = _call_collect_task(mod, 25)

    db = _FakeDatabaseManager.last_instance
    assert db is not None
    assert result["status"] == "success"
    assert result["articles_saved"] == len(db.persisted_articles) == 2
    assert db.source.total_articles == len(db.persisted_articles)
    assert db.source_checks and db.source_checks[-1]["articles_found"] == 2
