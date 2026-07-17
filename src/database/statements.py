"""Shared SQLAlchemy statement builders for the sync and async database managers.

DatabaseManager (sync, CLI callers) and AsyncDatabaseManager (async, web callers)
cannot share an execution path -- Session and AsyncSession differ in execute(),
await points, and lifecycle. They CAN share statement construction, and every
query shape that exists on both sides is defined here exactly once so the two
managers cannot silently drift apart. (That drift already shipped once: three
different default sort orders for "list articles", filters supported on one
side only, and a duplicated archived filter.)

Rules for this module:

- Builders are pure functions: inputs in, a SQLAlchemy Select/Update out.
  They never touch a session, never execute, never log.
- Filter objects are duck-typed via getattr() with defaults. Callers pass
  ArticleListFilter, SourceFilter, the web routes' SimpleFilter, or bare
  SimpleNamespace objects in tests -- none of these are required to carry
  every field (see tests/test_async_manager_source_filter_compat.py).
- Intentional sync/async divergences are expressed as explicit keyword
  parameters (e.g. default_sort_field, include_archived), never as separate
  copies of the query.
- Execution-side behavior (error handling, content deferral, annotation-count
  injection, ORM-to-Pydantic conversion) stays in each manager on purpose.
"""

from types import SimpleNamespace
from typing import Any

from sqlalchemy import Numeric, Select, Update, cast, desc, func, select, update
from sqlalchemy.dialects.postgresql import JSONB

from src.database.models import ArticleTable, SourceTable

# Sort keys that map to article_metadata['threat_hunting_score'] rather than a
# real column. "annotation_count" is intentionally approximated by hunt score:
# annotation counts are injected post-query by the async manager, so they are
# not sortable in SQL.
_METADATA_SORT_KEYS = ("threat_hunting_score", "annotation_count")


def _threat_score_expr() -> Any:
    """Numeric sort expression for the JSON-stored threat hunting score.

    Must use ->> (astext), not -> with a VARCHAR cast: ->> unquotes JSON
    strings and turns JSON null into SQL NULL (so the coalesce applies),
    whereas CAST(json AS VARCHAR) yields 'null' or a quoted string -- both
    crash CAST AS NUMERIC on the first row with a non-numeric score.
    """
    return func.cast(
        func.coalesce(ArticleTable.article_metadata["threat_hunting_score"].as_string(), "0"),
        Numeric,
    )


def _apply_article_filters(stmt: Select, article_filter: Any) -> Select:
    """Apply the canonical article WHERE clauses shared by list and count."""
    source_id = getattr(article_filter, "source_id", None)
    if source_id is not None:
        stmt = stmt.where(ArticleTable.source_id == source_id)

    # authors/tags are JSON list columns; plain JSON has no containment operator
    # in PostgreSQL, so cast to JSONB and use @> (Postgres-only, like the app).
    author = getattr(article_filter, "author", None)
    if author:
        stmt = stmt.where(cast(ArticleTable.authors, JSONB).contains([author]))

    tag = getattr(article_filter, "tag", None)
    if tag:
        stmt = stmt.where(cast(ArticleTable.tags, JSONB).contains([tag]))

    published_after = getattr(article_filter, "published_after", None)
    if published_after is not None:
        stmt = stmt.where(ArticleTable.published_at >= published_after)

    published_before = getattr(article_filter, "published_before", None)
    if published_before is not None:
        stmt = stmt.where(ArticleTable.published_at <= published_before)

    processing_status = getattr(article_filter, "processing_status", None)
    if processing_status is not None:
        stmt = stmt.where(ArticleTable.processing_status == processing_status)

    content_contains = getattr(article_filter, "content_contains", None)
    if content_contains is not None:
        stmt = stmt.where(ArticleTable.content.contains(content_contains))

    return stmt


def _apply_article_sort(stmt: Select, article_filter: Any, default_sort_field: str) -> Select:
    """Apply the canonical sort: metadata hunt-score sorts, real columns with a
    hunt-score tiebreaker, or hunt-score-only fallback for unknown keys."""
    sort_by = getattr(article_filter, "sort_by", None) or default_sort_field
    sort_order = getattr(article_filter, "sort_order", None) or "desc"

    if sort_by in _METADATA_SORT_KEYS:
        score = _threat_score_expr()
        return stmt.order_by(desc(score) if sort_order == "desc" else score)

    sort_field = getattr(ArticleTable, sort_by, None)
    if sort_field is None:
        return stmt.order_by(desc(_threat_score_expr()))

    score = _threat_score_expr()
    if sort_order == "desc":
        return stmt.order_by(desc(sort_field), desc(score))
    return stmt.order_by(sort_field, desc(score))


def build_article_list_stmt(
    article_filter: Any | None = None,
    *,
    default_sort_field: str = "published_at",
    limit: int | None = None,
    include_archived: bool = False,
) -> Select:
    """Canonical "list articles" statement for both managers.

    default_sort_field is the one intentional sync/async divergence: the CLI
    (sync) lists by published_at, the web dashboard (async) by discovered_at
    when no filter is given. limit applies only in the no-filter form, matching
    the async manager's signature; a filter carries its own offset/limit.
    """
    stmt = select(ArticleTable)
    if not include_archived:
        stmt = stmt.where(ArticleTable.archived == False)  # noqa: E712

    if article_filter is None:
        stmt = stmt.order_by(desc(getattr(ArticleTable, default_sort_field)))
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)
        return stmt

    stmt = _apply_article_filters(stmt, article_filter)
    stmt = _apply_article_sort(stmt, article_filter, default_sort_field)

    offset = getattr(article_filter, "offset", None)
    if offset is not None and offset > 0:
        stmt = stmt.offset(offset)

    filter_limit = getattr(article_filter, "limit", None)
    if filter_limit is not None and filter_limit > 0:
        stmt = stmt.limit(filter_limit)

    return stmt


def build_article_count_stmt(
    source_id: int | None = None,
    processing_status: str | None = None,
) -> Select:
    """COUNT twin of build_article_list_stmt -- same WHERE logic, no sort.

    Routed through _apply_article_filters so list and count can never disagree
    about what a filter means (pagination totals stay consistent with pages).
    """
    stmt = select(func.count(ArticleTable.id)).where(ArticleTable.archived == False)  # noqa: E712
    return _apply_article_filters(stmt, SimpleNamespace(source_id=source_id, processing_status=processing_status))


def build_article_by_id_stmt(article_id: int, *, include_archived: bool) -> Select:
    """Fetch one article by id.

    include_archived is an intentional divergence: the sync manager's plain
    get_article() excludes archived rows (it has an explicit
    get_article_including_archived variant); the async manager serves the web
    article detail page and includes archived rows.
    """
    stmt = select(ArticleTable).where(ArticleTable.id == article_id)
    if not include_archived:
        stmt = stmt.where(ArticleTable.archived == False)  # noqa: E712
    return stmt


def build_existing_urls_stmt(limit: int = 10000) -> Select:
    """Canonical URLs of non-archived articles, for ingestion deduplication."""
    return select(ArticleTable.canonical_url).where(ArticleTable.archived == False).limit(limit)  # noqa: E712


def build_update_article_embedding_stmt(
    article_id: int,
    embedding: list[float],
    model_name: str,
) -> Update:
    """Set an article's embedding vector, model name, and embed timestamp."""
    return (
        update(ArticleTable)
        .where(ArticleTable.id == article_id)
        .values(embedding=embedding, embedding_model=model_name, embedded_at=func.now())
    )


def _apply_source_filters(stmt: Select, filter_params: Any) -> Select:
    """Apply the canonical source WHERE clauses.

    SourceFilter is intentionally minimal (active, identifier); the legacy
    aliases below are kept for non-model filter objects still in the wild.
    """
    active = getattr(filter_params, "active", None)
    if active is not None:
        stmt = stmt.where(SourceTable.active == active)

    identifier = getattr(filter_params, "identifier", None)
    if identifier:
        stmt = stmt.where(SourceTable.identifier.contains(identifier))

    identifier_contains = getattr(filter_params, "identifier_contains", None)
    if identifier_contains:
        stmt = stmt.where(SourceTable.identifier.contains(identifier_contains))

    name_contains = getattr(filter_params, "name_contains", None)
    if name_contains:
        stmt = stmt.where(SourceTable.name.contains(name_contains))

    consecutive_failures_gte = getattr(filter_params, "consecutive_failures_gte", None)
    if consecutive_failures_gte is not None:
        stmt = stmt.where(SourceTable.consecutive_failures >= consecutive_failures_gte)

    last_check_before = getattr(filter_params, "last_check_before", None)
    if last_check_before:
        stmt = stmt.where(SourceTable.last_check < last_check_before)

    return stmt


def build_source_list_stmt(filter_params: Any | None = None) -> Select:
    """Canonical "list sources" statement, always ordered by name.

    The name ordering was async-only before unification; it is now canonical
    for both managers so every surface lists sources deterministically.
    """
    stmt = select(SourceTable)
    if filter_params is not None:
        stmt = _apply_source_filters(stmt, filter_params)

        offset = getattr(filter_params, "offset", None)
        if offset is not None:
            stmt = stmt.offset(offset)

        limit = getattr(filter_params, "limit", None)
        if limit is not None:
            stmt = stmt.limit(limit)

    return stmt.order_by(SourceTable.name)


def build_source_by_id_stmt(source_id: int) -> Select:
    """Fetch one source by primary key."""
    return select(SourceTable).where(SourceTable.id == source_id).limit(1)


def build_source_by_identifier_stmt(identifier: str) -> Select:
    """Fetch one source by its unique identifier."""
    return select(SourceTable).where(SourceTable.identifier == identifier).limit(1)
