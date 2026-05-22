"""Tests for scripts/_restore_common.py filter helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from _restore_common import filter_dump_lines, rewrite_fk_to_not_valid  # noqa: E402

# ---------------------------------------------------------------------------
# rewrite_fk_to_not_valid
# ---------------------------------------------------------------------------


def test_fk_rewrite_appends_not_valid():
    line = "    ADD CONSTRAINT fk_articles_source FOREIGN KEY (source_id) REFERENCES sources(id);\n"
    result = rewrite_fk_to_not_valid(line)
    assert "NOT VALID" in result
    assert result.endswith(";\n")


def test_fk_rewrite_idempotent_when_already_present():
    line = "    ADD CONSTRAINT fk FOREIGN KEY (x) REFERENCES y(id) NOT VALID;\n"
    assert rewrite_fk_to_not_valid(line) == line


def test_fk_rewrite_ignores_non_fk_lines():
    line = "ALTER TABLE ONLY public.content_hashes\n"
    assert rewrite_fk_to_not_valid(line) == line


# ---------------------------------------------------------------------------
# filter_dump_lines — PK deduplication
# ---------------------------------------------------------------------------

_FIRST_PK_BLOCK = "ALTER TABLE ONLY public.content_hashes\n    ADD CONSTRAINT content_hashes_pkey PRIMARY KEY (id);\n"

_SECOND_PK_BLOCK = "ALTER TABLE ONLY public.content_hashes\n    ADD CONSTRAINT content_hashes_pkey PRIMARY KEY (id);\n"


def _run(lines: list[str], **kwargs) -> list[str]:
    return list(filter_dump_lines(lines, **kwargs))


def test_first_pk_constraint_is_kept():
    lines = _FIRST_PK_BLOCK.splitlines(keepends=True)
    result = _run(lines)
    assert any("ADD CONSTRAINT content_hashes_pkey PRIMARY KEY" in line for line in result)
    assert any("ALTER TABLE" in line for line in result)


def test_duplicate_pk_constraint_is_dropped():
    lines = (_FIRST_PK_BLOCK + _SECOND_PK_BLOCK).splitlines(keepends=True)
    result = _run(lines)
    pk_lines = [line for line in result if "ADD CONSTRAINT content_hashes_pkey PRIMARY KEY" in line]
    assert len(pk_lines) == 1, f"Expected 1 PK line, got {len(pk_lines)}: {pk_lines}"


def test_duplicate_pk_drops_its_alter_table_line_too():
    lines = (_FIRST_PK_BLOCK + _SECOND_PK_BLOCK).splitlines(keepends=True)
    result = _run(lines)
    alter_lines = [line for line in result if "ALTER TABLE" in line and "content_hashes" in line]
    assert len(alter_lines) == 1, f"Expected 1 ALTER TABLE line, got {len(alter_lines)}"


def test_distinct_pk_constraints_both_kept():
    block_a = "ALTER TABLE ONLY public.content_hashes\n    ADD CONSTRAINT content_hashes_pkey PRIMARY KEY (id);\n"
    block_b = "ALTER TABLE ONLY public.simhash_buckets\n    ADD CONSTRAINT simhash_buckets_pkey PRIMARY KEY (id);\n"
    lines = (block_a + block_b).splitlines(keepends=True)
    result = _run(lines)
    assert any("content_hashes_pkey" in line for line in result)
    assert any("simhash_buckets_pkey" in line for line in result)


def test_deduplicate_disabled_passes_both_pk_lines():
    lines = (_FIRST_PK_BLOCK + _SECOND_PK_BLOCK).splitlines(keepends=True)
    result = _run(lines, dedup_primary_keys=False)
    pk_lines = [line for line in result if "ADD CONSTRAINT content_hashes_pkey PRIMARY KEY" in line]
    assert len(pk_lines) == 2


# ---------------------------------------------------------------------------
# filter_dump_lines — FK rewrite still works alongside PK dedup
# ---------------------------------------------------------------------------


def test_fk_rewrite_and_pk_dedup_coexist():
    pk_block = "ALTER TABLE ONLY public.content_hashes\n    ADD CONSTRAINT content_hashes_pkey PRIMARY KEY (id);\n"
    fk_block = (
        "ALTER TABLE ONLY public.content_hashes\n"
        "    ADD CONSTRAINT content_hashes_article_id_fkey FOREIGN KEY (article_id) REFERENCES articles(id);\n"
    )
    lines = (pk_block + fk_block).splitlines(keepends=True)
    result = _run(lines, rewrite_fk_constraints=True, dedup_primary_keys=True)

    pk_lines = [line for line in result if "PRIMARY KEY" in line]
    fk_lines = [line for line in result if "FOREIGN KEY" in line]

    assert len(pk_lines) == 1
    assert len(fk_lines) == 1
    assert "NOT VALID" in fk_lines[0]
    assert "NOT VALID" not in pk_lines[0]


# ---------------------------------------------------------------------------
# filter_dump_lines — skip_db_lifecycle
# ---------------------------------------------------------------------------


def test_skip_db_lifecycle_drops_create_database():
    lines = [
        "CREATE DATABASE cti_scraper;\n",
        "SELECT 1;\n",
    ]
    result = _run(lines, skip_db_lifecycle=True)
    assert not any("CREATE DATABASE" in line for line in result)
    assert any("SELECT 1" in line for line in result)


# ---------------------------------------------------------------------------
# filter_dump_lines — skip_unsupported_sets
# ---------------------------------------------------------------------------


def test_skip_unsupported_sets_drops_transaction_timeout():
    lines = [
        "SET transaction_timeout = 0;\n",
        "SET search_path = public;\n",
    ]
    result = _run(lines, skip_unsupported_sets=True)
    assert not any("transaction_timeout" in line for line in result)
    assert any("search_path" in line for line in result)


# ---------------------------------------------------------------------------
# filter_dump_lines — trailing ALTER TABLE flush
# ---------------------------------------------------------------------------


def test_trailing_alter_table_is_flushed():
    """An ALTER TABLE at EOF (not followed by ADD CONSTRAINT) must not be lost."""
    lines = ["ALTER TABLE ONLY public.articles ENABLE ROW LEVEL SECURITY;\n"]
    result = _run(lines)
    assert any("ALTER TABLE" in line for line in result)


# ---------------------------------------------------------------------------
# Contract: every restore-script caller must pass skip_unsupported_sets=True
# ---------------------------------------------------------------------------

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "scripts"

_RESTORE_SCRIPTS_WITH_FILTER = [
    "restore_database.py",
    "restore_database_v2.py",
    "restore_database_v3.py",
    "restore_system.py",
    "verify_backup.py",
]


@pytest.mark.parametrize("script_name", _RESTORE_SCRIPTS_WITH_FILTER)
def test_restore_script_passes_skip_unsupported_sets(script_name: str) -> None:
    """Every restore script that calls filter_dump_lines must pass skip_unsupported_sets=True.

    Without this flag, newer pg_dump versions that emit SET transaction_timeout
    and similar directives will cause restore failures on older Postgres clients.
    """
    source = (_SCRIPTS_ROOT / script_name).read_text()
    assert "skip_unsupported_sets=True" in source, (
        f"{script_name} calls filter_dump_lines without skip_unsupported_sets=True. "
        "Add skip_unsupported_sets=True to the filter_dump_lines call in that script."
    )
