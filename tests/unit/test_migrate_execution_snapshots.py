"""Unit tests for bounded execution-snapshot backfill batches."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import migrate_execution_snapshots as migration
from src.services.workflow_config_snapshot import SNAPSHOT_CONFIG_FIELDS

pytestmark = pytest.mark.unit


class Query:
    def __init__(self, batches):
        self.batches = batches

    def filter(self, *_conditions):
        return self

    def order_by(self, *_columns):
        return self

    def limit(self, _size):
        return self

    def count(self):
        return sum(len(batch) for batch in self.batches)

    def all(self):
        return self.batches.pop(0) if self.batches else []


class Session:
    def __init__(self, batches):
        self.query_object = Query(batches)
        self.commits = 0
        self.expirations = 0

    def query(self, _model):
        return self.query_object

    def commit(self):
        self.commits += 1

    def expire_all(self):
        self.expirations += 1


class Database:
    def __init__(self, session):
        self.session = session

    def get_session(self):
        class Context:
            def __enter__(_self):
                return self.session

            def __exit__(_self, *_args):
                return None

        return Context()


def test_migrate_processes_batches_and_commits_each_applied_batch(monkeypatch):
    complete = {field: None for field in SNAPSHOT_CONFIG_FIELDS}
    batches = [
        [SimpleNamespace(id=1, config_snapshot=complete), SimpleNamespace(id=2, config_snapshot={})],
        [SimpleNamespace(id=3, config_snapshot=complete)],
    ]
    session = Session(batches)
    monkeypatch.setattr(migration, "DatabaseManager", lambda: Database(session))
    attached = []
    monkeypatch.setattr(
        migration, "attach_snapshot", lambda _session, execution, _snapshot: attached.append(execution.id)
    )

    assert migration.migrate(apply=True, batch_size=2) == (3, 2, 1)
    assert attached == [1, 3]
    assert session.commits == 2
    assert session.expirations == 2
