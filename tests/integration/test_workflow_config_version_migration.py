"""The version-uniqueness migration, exercised against a real Postgres.

This migration rewrites 185 rows of the live config history, so "I ran it once and
it looked right" is not enough evidence. It builds a scratch database carrying the
live table's shape -- a mostly-unique version column with a handful of numbers
shared by two to five rows -- and asserts the three properties that make the
rewrite safe to run:

  * the row each version has always been addressed by keeps its number;
  * `id` never moves, so the evaluation tables' foreign keys are untouched;
  * running it twice changes nothing the second time.

Plus the outcome: a unique index that rejects a collision, and a sequence that
hands out numbers above everything already stored.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.migrate_workflow_config_version_unique import (  # noqa: E402
    INDEX_NAME,
    SEQUENCE_NAME,
    run_migration,
)
from tests.utils.test_database_url import build_test_database_url  # noqa: E402

pytestmark = pytest.mark.integration

SCRATCH_DB = "cti_scratch_version_migration_" + os.getenv("PYTEST_XDIST_WORKER", "main")

# id -> version. Mirrors the live distribution: unique numbers, one version shared
# by four rows and one by two, and a collision whose rows are not adjacent.
SEED = [
    (1, 10),
    (2, 20),
    (3, 20),
    (4, 20),
    (5, 30),
    (6, 20),
    (7, 40),
    (8, 40),
    (9, 50),
]


def _sync_base_url() -> str:
    return build_test_database_url(asyncpg=False).replace("+asyncpg", "")


def _scratch_url() -> str:
    return _sync_base_url().rsplit("/", 1)[0] + f"/{SCRATCH_DB}"


@pytest.fixture()
def scratch_engine(monkeypatch):
    admin = create_engine(_sync_base_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    admin.dispose()

    engine = create_engine(_scratch_url())
    with engine.connect() as conn:
        conn.execute(
            text("""
                CREATE TABLE agentic_workflow_config (
                    id SERIAL PRIMARY KEY,
                    version INTEGER NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT false,
                    description TEXT
                )
            """)
        )
        for row_id, version in SEED:
            conn.execute(
                text(
                    "INSERT INTO agentic_workflow_config (id, version, description) "
                    "VALUES (:id, :version, :description)"
                ),
                {"id": row_id, "version": version, "description": f"row {row_id}"},
            )
        conn.commit()

    # The script reads DATABASE_URL; point it at the scratch copy only.
    monkeypatch.setenv("DATABASE_URL", _scratch_url())

    yield engine

    engine.dispose()
    admin2 = create_engine(_sync_base_url(), isolation_level="AUTOCOMMIT")
    with admin2.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
    admin2.dispose()


def _rows(engine) -> dict[int, int]:
    with engine.connect() as conn:
        return {r[0]: r[1] for r in conn.execute(text("SELECT id, version FROM agentic_workflow_config")).fetchall()}


class TestVersionUniquenessMigration:
    def test_reports_success_and_converges_to_unique_versions(self, scratch_engine):
        assert run_migration() is True

        with scratch_engine.connect() as conn:
            total, distinct = conn.execute(
                text("SELECT count(*), count(DISTINCT version) FROM agentic_workflow_config")
            ).fetchone()
        assert total == len(SEED)
        assert total == distinct

    def test_the_first_row_of_each_collision_keeps_its_number(self, scratch_engine):
        """Whatever a version has always pointed at is what it still points at."""
        run_migration()
        rows = _rows(scratch_engine)

        # Lowest id wins for each duplicated version; unique versions never move.
        assert rows[2] == 20, "the earliest row holding version 20 was renumbered"
        assert rows[7] == 40, "the earliest row holding version 40 was renumbered"
        assert rows[1] == 10
        assert rows[5] == 30
        assert rows[9] == 50

    def test_only_the_later_rows_of_a_collision_move(self, scratch_engine):
        run_migration()
        rows = _rows(scratch_engine)

        moved = {row_id for row_id, version in rows.items() if version != dict(SEED)[row_id]}
        assert moved == {3, 4, 6, 8}, f"unexpected rows renumbered: {moved}"
        # Everything moved lands above the original maximum.
        assert all(rows[row_id] > 50 for row_id in moved)

    def test_ids_never_change_so_eval_foreign_keys_survive(self, scratch_engine):
        """sigma_evaluations / subagent_evaluations reference id, not version."""
        before = set(_rows(scratch_engine))
        run_migration()
        assert set(_rows(scratch_engine)) == before

    def test_renumbered_rows_record_the_number_they_had(self, scratch_engine):
        run_migration()
        with scratch_engine.connect() as conn:
            descriptions = dict(conn.execute(text("SELECT id, description FROM agentic_workflow_config")).fetchall())

        assert "renumbered from duplicate version 20" in descriptions[3]
        assert "renumbered from duplicate version 40" in descriptions[8]
        # An untouched row keeps its description verbatim.
        assert descriptions[1] == "row 1"

    def test_creates_a_unique_index_that_rejects_a_collision(self, scratch_engine):
        run_migration()

        with scratch_engine.connect() as conn:
            assert conn.execute(text("SELECT 1 FROM pg_indexes WHERE indexname = :i"), {"i": INDEX_NAME}).fetchone()

            with pytest.raises(Exception) as exc_info:
                conn.execute(text("INSERT INTO agentic_workflow_config (version) VALUES (10)"))
                conn.commit()
        assert "unique" in str(exc_info.value).lower()

    def test_the_sequence_starts_above_every_stored_version(self, scratch_engine):
        run_migration()

        with scratch_engine.connect() as conn:
            highest = conn.execute(text("SELECT max(version) FROM agentic_workflow_config")).scalar()
            first = conn.execute(text(f"SELECT nextval('{SEQUENCE_NAME}')")).scalar()
            second = conn.execute(text(f"SELECT nextval('{SEQUENCE_NAME}')")).scalar()

        assert first > highest
        assert second > first

    def test_running_it_twice_is_a_no_op(self, scratch_engine):
        assert run_migration() is True
        after_first = _rows(scratch_engine)

        assert run_migration() is True
        assert _rows(scratch_engine) == after_first

    def test_a_table_with_no_duplicates_is_left_alone(self, scratch_engine):
        with scratch_engine.connect() as conn:
            conn.execute(text("DELETE FROM agentic_workflow_config WHERE id IN (3, 4, 6, 8)"))
            conn.commit()
        before = _rows(scratch_engine)

        assert run_migration() is True
        assert _rows(scratch_engine) == before
