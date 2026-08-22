"""Concurrent config writes must not be handed the same version number.

`_next_workflow_config_version()` used to be `SELECT max(version) + 1`, a
read-modify-write with nothing to reject a tie. Two writers that read the same
maximum both committed it: 164 version numbers in the live table were shared by
two or more rows, the worst by five. Because the UI presents version as the
config's identity and `configVersionSearch` looks configs up by it, that identity
was ambiguous.

Allocation now draws from a sequence, which cannot hand the same number to two
callers whatever their transactions do. These tests run two genuinely concurrent
sessions against Postgres, because the defect only exists between transactions --
a single-session test cannot see it.

Requires the sequence created by scripts/migrate_workflow_config_version_unique.py;
skips where it is absent so a database that has not been migrated does not fail
the suite.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.web.routes.workflow_config import (
    _WORKFLOW_CONFIG_VERSION_SEQUENCE,
    _lock_workflow_config,
    _next_workflow_config_version,
)

pytestmark = pytest.mark.integration


def _sync_test_db_url() -> str:
    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default = f"postgresql://cti_user:{password}@localhost:5433/cti_scraper_test"
    url = os.getenv("TEST_DATABASE_URL", default)
    if "test" not in url.lower():
        raise RuntimeError("Integration tests must use a test database")
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(_sync_test_db_url(), pool_size=5, max_overflow=5)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    with engine.connect() as conn:
        present = conn.execute(text("SELECT to_regclass(:seq)"), {"seq": _WORKFLOW_CONFIG_VERSION_SEQUENCE}).scalar()
    if present is None:
        pytest.skip(
            f"{_WORKFLOW_CONFIG_VERSION_SEQUENCE} not present -- run "
            "scripts/migrate_workflow_config_version_unique.py against the test database"
        )
    return sessionmaker(bind=engine)


class TestVersionAllocationIsRaceFree:
    def test_two_concurrent_allocations_return_distinct_versions(self, session_factory):
        """The original defect, reproduced: two writers, one number."""

        def allocate() -> int:
            session = session_factory()
            try:
                # Same order the write paths use: lock, then allocate.
                _lock_workflow_config(session)
                version = _next_workflow_config_version(session)
                session.commit()
                return version
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = [f.result() for f in [pool.submit(allocate), pool.submit(allocate)]]

        assert first != second, f"both writers were handed version {first}"

    def test_many_concurrent_allocations_are_all_distinct(self, session_factory):
        """Widen the window: the arithmetic version collides readily at this width."""
        workers = 8

        def allocate() -> int:
            session = session_factory()
            try:
                version = _next_workflow_config_version(session)
                session.commit()
                return version
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            versions = [f.result() for f in [pool.submit(allocate) for _ in range(workers)]]

        assert len(set(versions)) == workers, f"duplicate versions allocated: {sorted(versions)}"

    def test_allocation_stays_above_every_stored_version(self, session_factory):
        """A number already in the table would be rejected by the unique index."""
        session = session_factory()
        try:
            highest = session.execute(text("SELECT COALESCE(max(version), 0) FROM agentic_workflow_config")).scalar()
            allocated = _next_workflow_config_version(session)
            session.commit()
        finally:
            session.close()

        assert allocated > int(highest or 0)
