"""Unit tests for content-addressed execution configuration snapshots."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.services.execution_snapshot_store import attach_snapshot, hydrate_snapshot, store_snapshot

pytestmark = pytest.mark.unit


def _session(existing=None):
    session = Mock()
    session.query.return_value.filter.return_value.first.return_value = existing
    return session


def test_store_reuses_existing_content_hash():
    existing = SimpleNamespace(id=8, content_hash="hash", payload={"snapshot_hash": "hash"})
    session = _session(existing)

    assert store_snapshot(session, {"snapshot_hash": "hash"}) is existing
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_attach_compacts_execution_to_snapshot_reference():
    record = SimpleNamespace(id=12, content_hash="hash", payload={"snapshot_hash": "hash"})
    session = _session(record)
    execution = SimpleNamespace(config_snapshot=None, config_snapshot_id=None)

    attach_snapshot(session, execution, {"snapshot_hash": "hash", "agent_prompts": {"RankAgent": {}}})

    assert execution.config_snapshot_id == 12
    assert execution.config_snapshot == {"snapshot_id": 12}


def test_hydrate_prefers_immutable_record_and_preserves_legacy_fallback():
    assert hydrate_snapshot(
        SimpleNamespace(
            snapshot_record=SimpleNamespace(payload={"agent_prompts": {"RankAgent": {}}}), config_snapshot={}
        )
    ) == {"agent_prompts": {"RankAgent": {}}}
    assert hydrate_snapshot(SimpleNamespace(snapshot_record=None, config_snapshot={"legacy": True})) == {"legacy": True}
