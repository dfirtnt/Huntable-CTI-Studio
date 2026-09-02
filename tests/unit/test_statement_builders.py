"""Unit tests for the shared statement builders (src/database/statements.py).

These builders are the single source of truth for every query shape shared by
DatabaseManager (sync) and AsyncDatabaseManager (async). The assertions here
pin the canonical SQL shape: if a builder changes, both managers change with
it, and this file is where that contract is enforced.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from src.database.statements import (
    build_article_by_id_stmt,
    build_article_count_stmt,
    build_article_list_stmt,
    build_existing_urls_stmt,
    build_source_by_id_stmt,
    build_source_by_identifier_stmt,
    build_source_list_stmt,
    build_update_article_embedding_stmt,
)
from src.models.article import ArticleListFilter


def _compiled(stmt):
    """Compile to PostgreSQL SQL text plus bound parameter values."""
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


@pytest.mark.unit
class TestArticleListStmt:
    def test_no_filter_applies_default_sort_and_single_archived_filter(self):
        sql, _ = _compiled(build_article_list_stmt(default_sort_field="published_at"))
        assert "articles.published_at DESC" in sql
        assert sql.count("archived = false") == 1, "archived exclusion must appear exactly once"
        assert "LIMIT" not in sql

    def test_no_filter_async_default_sort_and_bare_limit(self):
        sql, params = _compiled(build_article_list_stmt(default_sort_field="discovered_at", limit=1000))
        assert "articles.discovered_at DESC" in sql
        assert "LIMIT" in sql
        assert 1000 in params.values()

    def test_include_archived_drops_archived_filter(self):
        sql, _ = _compiled(build_article_list_stmt(include_archived=True))
        assert "archived = false" not in sql

    def test_filter_fields_all_apply(self):
        article_filter = ArticleListFilter(
            source_id=3,
            author="alice",
            tag="apt",
            processing_status="pending",
            content_contains="rundll32",
            limit=50,
            offset=10,
        )
        sql, params = _compiled(build_article_list_stmt(article_filter))
        assert "articles.source_id =" in sql
        # authors/tags are JSON columns: containment must go through a JSONB
        # cast and @>, not LIKE (plain JSON has no LIKE operator in Postgres).
        assert "CAST(articles.authors AS JSONB) @>" in sql
        assert "CAST(articles.tags AS JSONB) @>" in sql
        assert "articles.processing_status =" in sql
        assert "articles.content LIKE" in sql
        assert "LIMIT" in sql and "OFFSET" in sql
        for value in (3, "pending", 50, 10):
            assert value in params.values()

    def test_filter_defaults_sort_published_at_desc_with_hunt_score_tiebreak(self):
        sql, _ = _compiled(build_article_list_stmt(ArticleListFilter()))
        order_clause = sql.split("ORDER BY")[1]
        assert "articles.published_at DESC" in order_clause
        assert "article_metadata" in order_clause, "hunt-score tiebreaker expected"

    def test_metadata_sort_threat_hunting_score_asc_and_desc(self):
        sql_desc, _ = _compiled(build_article_list_stmt(ArticleListFilter(sort_by="threat_hunting_score")))
        order_desc = sql_desc.split("ORDER BY")[1]
        assert "article_metadata" in order_desc and "DESC" in order_desc

        sql_asc, _ = _compiled(
            build_article_list_stmt(ArticleListFilter(sort_by="threat_hunting_score", sort_order="asc"))
        )
        order_asc = sql_asc.split("ORDER BY")[1]
        assert "article_metadata" in order_asc and "DESC" not in order_asc

    def test_annotation_count_sort_uses_correlated_count_desc(self):
        sql, _ = _compiled(build_article_list_stmt(ArticleListFilter(sort_by="annotation_count")))
        order_clause = sql.split("ORDER BY")[1]
        assert "count(article_annotations.id)" in order_clause.lower()
        assert "article_annotations.article_id = articles.id" in order_clause.lower()
        assert "DESC" in order_clause
        # hunt-score tiebreaker, same shape as a real-column sort
        assert "article_metadata" in order_clause

    def test_annotation_count_sort_asc_drops_leading_desc(self):
        sql, _ = _compiled(build_article_list_stmt(ArticleListFilter(sort_by="annotation_count", sort_order="asc")))
        order_clause = sql.split("ORDER BY")[1]
        first_clause = order_clause.split(",")[0]
        assert "DESC" not in first_clause
        assert "count(article_annotations.id)" in first_clause.lower()

    def test_hunt_score_sort_uses_astext_not_json_cast(self):
        """The score sort must extract via ->> (astext): CAST(json AS VARCHAR)
        yields 'null' for JSON null and keeps quotes on JSON strings, and both
        crash CAST AS NUMERIC on the first bad metadata row. ->> unquotes and
        maps JSON null to SQL NULL so the coalesce('0') applies (verified on
        Postgres: null/'\"85\"'/92.5/missing -> 0/85/92.5/0)."""
        sql, _ = _compiled(build_article_list_stmt(ArticleListFilter(sort_by="threat_hunting_score")))
        order_clause = sql.split("ORDER BY")[1]
        assert "->>" in order_clause
        assert "-> %" not in order_clause

    def test_unknown_sort_column_falls_back_to_hunt_score_only(self):
        sql, _ = _compiled(build_article_list_stmt(ArticleListFilter(sort_by="hunt_score")))
        order_clause = sql.split("ORDER BY")[1]
        assert "article_metadata" in order_clause
        assert "published_at" not in order_clause

    def test_zero_offset_and_zero_limit_are_not_applied(self):
        sql, _ = _compiled(build_article_list_stmt(ArticleListFilter(offset=0, limit=0)))
        assert "OFFSET" not in sql
        assert "LIMIT" not in sql

    def test_published_date_range_filters(self):
        from datetime import datetime

        after = datetime(2026, 6, 1)
        before = datetime(2026, 7, 1)
        sql, params = _compiled(
            build_article_list_stmt(ArticleListFilter(published_after=after, published_before=before))
        )
        assert "articles.published_at >=" in sql
        assert "articles.published_at <=" in sql
        assert after in params.values() and before in params.values()

    def test_duck_typed_filter_without_optional_fields(self):
        """Web-route SimpleFilter-like objects need not carry every field."""
        bare = SimpleNamespace(source_id=7, sort_by="created_at", sort_order="asc")
        sql, params = _compiled(build_article_list_stmt(bare))
        assert 7 in params.values()
        assert "articles.created_at" in sql.split("ORDER BY")[1]

    def test_none_sort_by_falls_back_to_default_sort_field(self):
        bare = SimpleNamespace(sort_by=None, sort_order=None)
        sql, _ = _compiled(build_article_list_stmt(bare, default_sort_field="discovered_at"))
        assert "articles.discovered_at DESC" in sql.split("ORDER BY")[1]


@pytest.mark.unit
class TestArticleCountStmt:
    def test_count_shares_filter_shape_with_single_archived_filter(self):
        sql, params = _compiled(build_article_count_stmt(source_id=5, processing_status="pending"))
        assert "count" in sql
        assert sql.count("archived = false") == 1
        assert 5 in params.values() and "pending" in params.values()

    def test_count_without_filters(self):
        sql, _ = _compiled(build_article_count_stmt())
        assert "count" in sql and "archived = false" in sql


@pytest.mark.unit
class TestArticleByIdStmt:
    def test_excludes_archived_when_asked(self):
        sql, params = _compiled(build_article_by_id_stmt(7, include_archived=False))
        assert "archived = false" in sql
        assert 7 in params.values()

    def test_includes_archived_when_asked(self):
        sql, _ = _compiled(build_article_by_id_stmt(7, include_archived=True))
        assert "archived = false" not in sql


@pytest.mark.unit
class TestSourceStmts:
    def test_list_always_ordered_by_name(self):
        sql, _ = _compiled(build_source_list_stmt())
        assert "ORDER BY sources.name" in sql

    def test_minimal_source_filter_shape(self):
        sql, params = _compiled(build_source_list_stmt(SimpleNamespace(active=True, identifier="alp")))
        assert "sources.active =" in sql
        assert "alp" in params.values()
        assert "ORDER BY sources.name" in sql

    def test_legacy_alias_fields_still_apply(self):
        stmt = build_source_list_stmt(SimpleNamespace(active=None, identifier_contains="bet", name_contains="Beta"))
        sql, params = _compiled(stmt)
        assert "bet" in params.values() and "Beta" in params.values()
        assert "sources.active =" not in sql

    def test_failure_and_staleness_filters(self):
        from datetime import datetime

        cutoff = datetime(2026, 1, 1)
        stmt = build_source_list_stmt(SimpleNamespace(consecutive_failures_gte=3, last_check_before=cutoff))
        sql, params = _compiled(stmt)
        assert "consecutive_failures >=" in sql
        assert "last_check <" in sql
        assert 3 in params.values() and cutoff in params.values()

    def test_by_id_and_by_identifier(self):
        sql_id, params_id = _compiled(build_source_by_id_stmt(9))
        assert "LIMIT" in sql_id and 9 in params_id.values()

        sql_ident, params_ident = _compiled(build_source_by_identifier_stmt("msrc"))
        assert "LIMIT" in sql_ident and "msrc" in params_ident.values()

    def test_source_pagination_applies_when_present(self):
        """Source pagination keeps the legacy sync semantics: offset/limit apply
        whenever set (including 0) -- unlike article filters, which guard on >0.
        Pinned so the asymmetry is a documented choice, not an accident."""
        stmt = build_source_list_stmt(SimpleNamespace(offset=0, limit=0))
        sql, _ = _compiled(stmt)
        assert "OFFSET" in sql and "LIMIT" in sql

        sql_none, _ = _compiled(build_source_list_stmt(SimpleNamespace(active=True)))
        assert "OFFSET" not in sql_none and "LIMIT" not in sql_none


@pytest.mark.unit
class TestOtherStmts:
    def test_existing_urls_excludes_archived_and_limits(self):
        sql, params = _compiled(build_existing_urls_stmt(500))
        assert "canonical_url" in sql
        assert "archived = false" in sql
        assert 500 in params.values()

    def test_existing_content_hashes_reads_articles_table(self):
        from src.database.statements import build_existing_content_hashes_stmt

        sql, params = _compiled(build_existing_content_hashes_stmt(500))
        assert "articles.content_hash" in sql
        assert "content_hashes" not in sql, "must not read the legacy ledger table"
        assert "archived = false" in sql
        assert 500 in params.values()

    def test_update_article_embedding_sets_all_three_columns(self):
        stmt = build_update_article_embedding_stmt(1, [0.1, 0.2], "all-mpnet-base-v2")
        sql = str(stmt)
        assert "UPDATE articles" in sql
        assert "embedding" in sql and "embedding_model" in sql and "embedded_at" in sql
