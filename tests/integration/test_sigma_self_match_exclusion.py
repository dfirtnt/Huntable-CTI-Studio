"""Candidate retrieval leaves out a queued rule's own customer-repository copy.

Against the real test database: once a queued rule's PR merges and the customer
repository syncs, the corpus holds ``cust-<yaml id>`` -- byte-identical, so it shares
the proposed rule's exact hash and would win the exact-hash shortcut, and it shares
its canonical class and logsource key. Every retrieval path must skip that row while
still returning genuine near-duplicates.
"""

import uuid

import pytest

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleTable
from src.services.sigma_novelty_service import SigmaNoveltyService, customer_copy_rule_id

pytestmark = [pytest.mark.integration, pytest.mark.integration_full]


def _sync_test_db_url() -> str:
    import os

    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default_url = f"postgresql+asyncpg://cti_user:{password}@localhost:5433/cti_scraper_test"
    return os.getenv("TEST_DATABASE_URL", default_url).replace("+asyncpg", "")


@pytest.fixture
def corpus():
    """A self copy and a genuine duplicate sharing one isolated class, hash and logsource key."""
    db = DatabaseManager(database_url=_sync_test_db_url())
    session = db.get_session()
    tag = uuid.uuid4().hex[:12]
    yaml_id = str(uuid.uuid4())
    shared = {
        "exact_hash": uuid.uuid4().hex + uuid.uuid4().hex[:32],
        "canonical_class": f"test.self_match.{tag}",
        "logsource_key": f"testproduct{tag}|process_creation",
    }
    rows = [
        SigmaRuleTable(
            rule_id=customer_copy_rule_id({"id": yaml_id}),
            title="Self copy",
            logsource={},
            detection={},
            file_path=f"cust/{tag}-self.yml",
            **shared,
        ),
        SigmaRuleTable(
            rule_id=f"sigmahq-{tag}",
            title="Genuine duplicate",
            logsource={},
            detection={},
            file_path=f"rules/{tag}-dup.yml",
            **{**shared, "exact_hash": uuid.uuid4().hex + uuid.uuid4().hex[:32]},
        ),
    ]
    session.add_all(rows)
    session.commit()
    try:
        yield session, yaml_id, shared, tag
    finally:
        session.rollback()
        session.query(SigmaRuleTable).filter(SigmaRuleTable.file_path.like(f"%{tag}%")).delete(
            synchronize_session=False
        )
        session.commit()
        session.close()


def _ids(candidates):
    return sorted(c["rule_id"] for c in candidates)


def test_exact_hash_shortcut_does_not_return_the_self_copy(corpus):
    session, yaml_id, shared, tag = corpus
    service = SigmaNoveltyService(db_session=session)

    without = service.retrieve_candidates(exact_hash=shared["exact_hash"], logsource_key=shared["logsource_key"])
    assert _ids(without) == [customer_copy_rule_id({"id": yaml_id})], "baseline: the self copy wins the shortcut"

    with_exclusion = service.retrieve_candidates(
        exact_hash=shared["exact_hash"],
        logsource_key=shared["logsource_key"],
        exclude_rule_id=customer_copy_rule_id({"id": yaml_id}),
    )
    assert _ids(with_exclusion) == [f"sigmahq-{tag}"]


def test_canonical_class_path_keeps_the_duplicate_and_drops_the_self_copy(corpus):
    session, yaml_id, shared, tag = corpus
    service = SigmaNoveltyService(db_session=session)

    candidates = service.retrieve_candidates(
        exact_hash=None,
        logsource_key=shared["logsource_key"],
        canonical_class=shared["canonical_class"],
        use_deterministic=True,
        exclude_rule_id=customer_copy_rule_id({"id": yaml_id}),
    )

    assert _ids(candidates) == [f"sigmahq-{tag}"]


def test_logsource_fallback_path_keeps_the_duplicate_and_drops_the_self_copy(corpus):
    session, yaml_id, shared, tag = corpus
    service = SigmaNoveltyService(db_session=session)

    candidates = service.retrieve_candidates(
        exact_hash=None,
        logsource_key=shared["logsource_key"],
        exclude_rule_id=customer_copy_rule_id({"id": yaml_id}),
    )

    assert _ids(candidates) == [f"sigmahq-{tag}"]
