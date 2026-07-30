"""Unit contract tests for ArticleTable schema invariants.

Regression guard for Todoist 6h6M3fPjX4vHCg3V: production enforces a UNIQUE
btree named uq_articles_canonical_url on articles.canonical_url, but the ORM
model omitted unique=True, so a fresh DB built via Base.metadata.create_all()
silently lost canonical-URL uniqueness. These tests assert the ORM declares
the constraint (by production's exact index name) so the drift cannot recur.
"""

from __future__ import annotations

import pytest

from src.database.models import ArticleTable

pytestmark = pytest.mark.unit


def _canonical_url_index():
    return next(
        (ix for ix in ArticleTable.__table__.indexes if ix.name == "uq_articles_canonical_url"),
        None,
    )


def test_article_declares_canonical_url_unique_index():
    index = _canonical_url_index()

    assert index is not None, "ArticleTable must declare the uq_articles_canonical_url index"
    assert index.unique is True, "uq_articles_canonical_url must be a UNIQUE index"
    assert [col.name for col in index.columns] == ["canonical_url"]


def test_article_has_no_duplicate_plain_canonical_url_index():
    # Production has only the unique index on canonical_url (no separate plain
    # ix_articles_canonical_url). Guard against re-adding index=True on the
    # column, which would emit a second, redundant non-unique index.
    canonical_url_indexes = [
        ix for ix in ArticleTable.__table__.indexes if [col.name for col in ix.columns] == ["canonical_url"]
    ]

    assert len(canonical_url_indexes) == 1
    assert canonical_url_indexes[0].name == "uq_articles_canonical_url"
