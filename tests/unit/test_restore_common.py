"""Unit tests for scripts/_restore_common.py filter helpers."""

import sys
from pathlib import Path

import pytest

# Make the scripts package importable without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from _restore_common import filter_dump_lines, rewrite_fk_to_not_valid  # noqa: E402


# ---------------------------------------------------------------------------
# rewrite_fk_to_not_valid
# ---------------------------------------------------------------------------


def test_fk_rewrite_appends_not_valid():
    line = "    ADD CONSTRAINT foo FOREIGN KEY (a) REFERENCES b(id);\n"
    result = rewrite_fk_to_not_valid(line)
    assert "NOT VALID" in result
    assert result.endswith(";\n")


def test_fk_rewrite_idempotent():
    line = "    ADD CONSTRAINT foo FOREIGN KEY (a) REFERENCES b(id) NOT VALID;\n"
    assert rewrite_fk_to_not_valid(line) == line


def test_fk_rewrite_ignores_non_fk_lines():
    line = "    ADD CONSTRAINT foo PRIMARY KEY (id);\n"
    assert rewrite_fk_to_not_valid(line) == line


# ---------------------------------------------------------------------------
# filter_dump_lines -- primary-key deduplication
# ---------------------------------------------------------------------------

_PK_BLOCK = """\
ALTER TABLE ONLY public.content_hashes
    ADD CONSTRAINT content_hashes_pkey PRIMARY KEY (id);
"""


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _run(text: str, **kwargs) -> str:
    return "".join(filter_dump_lines(_lines(text), **kwargs))


def test_single_pk_block_passes_through():
    result = _run(_PK_BLOCK, dedup_primary_keys=True)
    assert "ADD CONSTRAINT content_hashes_pkey PRIMARY KEY" in result


def test_duplicate_pk_block_is_deduplicated():
    duplicate = _PK_BLOCK + "\n" + _PK_BLOCK
    result = _run(duplicate, dedup_primary_keys=True)
    # Should appear exactly once
    assert result.count("ADD CONSTRAINT content_hashes_pkey PRIMARY KEY") == 1


def test_different_tables_both_kept():
    other = """\
ALTER TABLE ONLY public.articles
    ADD CONSTRAINT articles_pkey PRIMARY KEY (id);
"""
    combined = _PK_BLOCK + "\n" + other
    result = _run(combined, dedup_primary_keys=True)
    assert "content_hashes_pkey" in result
    assert "articles_pkey" in result


def test_fk_constraint_still_rewritten_alongside_pk_dedup():
    fk_block = """\
ALTER TABLE ONLY public.content_hashes
    ADD CONSTRAINT content_hashes_article_id_fkey FOREIGN KEY (article_id) REFERENCES articles(id);
"""
    combined = _PK_BLOCK + "\n" + fk_block
    result = _run(combined, dedup_primary_keys=True, rewrite_fk_constraints=True)
    assert "NOT VALID" in result
    assert "ADD CONSTRAINT content_hashes_pkey PRIMARY KEY" in result


def test_dedup_disabled_keeps_both():
    duplicate = _PK_BLOCK + "\n" + _PK_BLOCK
    result = _run(duplicate, dedup_primary_keys=False)
    assert result.count("ADD CONSTRAINT content_hashes_pkey PRIMARY KEY") == 2


def test_skip_unsupported_sets():
    sql = "SET transaction_timeout = 0;\nSELECT 1;\n"
    result = _run(sql, skip_unsupported_sets=True)
    assert "transaction_timeout" not in result
    assert "SELECT 1" in result


def test_skip_db_lifecycle():
    sql = "DROP DATABASE cti_scraper;\nCREATE DATABASE cti_scraper;\nSELECT 1;\n"
    result = _run(sql, skip_db_lifecycle=True)
    assert "DROP DATABASE" not in result
    assert "CREATE DATABASE" not in result
    assert "SELECT 1" in result


# ---------------------------------------------------------------------------
# filter_dump_lines -- COPY row deduplication
# ---------------------------------------------------------------------------

_COPY_BLOCK = """\
COPY public.articles (id, title, url) FROM stdin;
1\tFirst article\thttp://example.com/1
35\tDuplicate article\thttp://example.com/35
35\tDuplicate article again\thttp://example.com/35b
2\tSecond article\thttp://example.com/2
\\.
"""


def test_copy_dedup_removes_second_occurrence():
    result = _run(_COPY_BLOCK, dedup_copy_rows=True)
    # Row 35 should appear once only
    assert result.count("35\t") == 1
    # Other rows untouched
    assert "1\tFirst article" in result
    assert "2\tSecond article" in result


def test_copy_dedup_keeps_first_occurrence():
    result = _run(_COPY_BLOCK, dedup_copy_rows=True)
    assert "Duplicate article\t" in result
    assert "Duplicate article again" not in result


def test_copy_dedup_disabled_keeps_all():
    result = _run(_COPY_BLOCK, dedup_copy_rows=False)
    assert result.count("35\t") == 2


def test_copy_dedup_no_id_column_passes_through():
    no_id = """\
COPY public.foo (name, value) FROM stdin;
alice\t1
alice\t2
\\.
"""
    result = _run(no_id, dedup_copy_rows=True)
    # No id column -- both rows kept
    assert result.count("alice") == 2


def test_copy_dedup_multiple_tables_independent():
    block2 = """\
COPY public.sources (id, name) FROM stdin;
35\tSource A
35\tSource A dup
\\.
"""
    combined = _COPY_BLOCK + "\n" + block2
    result = _run(combined, dedup_copy_rows=True)
    # Each table's COPY block is deduplicated independently
    assert result.count("35\t") == 2  # one from articles, one from sources


def test_copy_dedup_end_sentinel_preserved():
    result = _run(_COPY_BLOCK, dedup_copy_rows=True)
    assert "\\." in result


def test_copy_dedup_combined_with_pk_dedup():
    """Both filters active simultaneously -- realistic dump excerpt."""
    dump = _COPY_BLOCK + "\n" + _PK_BLOCK + "\n" + _PK_BLOCK
    result = _run(dump, dedup_copy_rows=True, dedup_primary_keys=True)
    assert result.count("35\t") == 1
    assert result.count("ADD CONSTRAINT content_hashes_pkey PRIMARY KEY") == 1


def test_copy_dedup_triple_duplicate_keeps_only_first():
    """Three rows with the same id -- only the first survives."""
    block = (
        "COPY public.articles (id, title) FROM stdin;\n"
        "5\tOriginal\n"
        "5\tDup 1\n"
        "5\tDup 2\n"
        "\\.\n"
    )
    result = _run(block, dedup_copy_rows=True)
    assert result.count("5\t") == 1
    assert "Original" in result
    assert "Dup 1" not in result
    assert "Dup 2" not in result


def test_copy_dedup_empty_block_passes_through():
    """COPY block with no data rows should be preserved intact."""
    block = "COPY public.articles (id, title) FROM stdin;\n\\.\n"
    result = _run(block, dedup_copy_rows=True)
    assert "COPY public.articles" in result
    assert "\\." in result


def test_pk_dedup_three_blocks_keeps_only_first():
    """Three identical PK blocks -- only the first should be emitted."""
    triple = _PK_BLOCK + "\n" + _PK_BLOCK + "\n" + _PK_BLOCK
    result = _run(triple, dedup_primary_keys=True)
    assert result.count("ADD CONSTRAINT content_hashes_pkey PRIMARY KEY") == 1


def test_pk_dedup_trailing_alter_table_flushed():
    """ALTER TABLE at end of file with no following ADD CONSTRAINT is emitted."""
    # This covers the trailing-buffer flush code path.
    sql = "ALTER TABLE ONLY public.orphan\n"
    result = _run(sql, dedup_primary_keys=True)
    assert "ALTER TABLE ONLY public.orphan" in result


def test_pk_dedup_alter_table_followed_by_non_constraint():
    """ALTER TABLE followed by a non-ADD-CONSTRAINT line flushes the buffer normally."""
    sql = (
        "ALTER TABLE ONLY public.articles\n"
        "    ALTER COLUMN id SET DEFAULT nextval('articles_id_seq');\n"
    )
    result = _run(sql, dedup_primary_keys=True)
    assert "ALTER TABLE ONLY public.articles" in result
    assert "ALTER COLUMN id SET DEFAULT" in result


def test_realistic_clean_dump_excerpt():
    """Single-occurrence PK (the common case) must pass through unchanged."""
    excerpt = (
        "-- Name: content_hashes content_hashes_pkey\n"
        "--\n"
        "\n"
        "ALTER TABLE ONLY public.content_hashes\n"
        "    ADD CONSTRAINT content_hashes_pkey PRIMARY KEY (id);\n"
        "\n"
        "ALTER TABLE ONLY public.articles\n"
        "    ADD CONSTRAINT articles_pkey PRIMARY KEY (id);\n"
    )
    result = _run(excerpt, dedup_primary_keys=True, dedup_copy_rows=True, rewrite_fk_constraints=True)
    assert result.count("PRIMARY KEY") == 2


# ---------------------------------------------------------------------------
# Cross-script consistency: all restore callers must pass skip_unsupported_sets
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

_RESTORE_SCRIPTS = [
    "restore_database.py",
    "restore_database_v2.py",
    "restore_database_v3.py",
    "restore_system.py",
    "verify_backup.py",
]


@pytest.mark.parametrize("script_name", _RESTORE_SCRIPTS)
def test_restore_script_passes_skip_unsupported_sets(script_name):
    """Every restore/verify script must pass skip_unsupported_sets=True to
    filter_dump_lines so that pg_dump directives from Postgres 17+ (e.g.
    SET transaction_timeout) do not abort restores against older psql clients.
    """
    text = (_SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
    assert "skip_unsupported_sets=True" in text, (
        f"{script_name} calls filter_dump_lines without skip_unsupported_sets=True. "
        f"Add the flag to protect against newer pg_dump versions."
    )
