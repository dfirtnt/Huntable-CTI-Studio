"""Regression: retrying an execution must hydrate its externalized config snapshot.

Snapshot externalization leaves ``config_snapshot = {"snapshot_id": N}`` on the
execution row and moves the real payload -- ``eval_run``, ``subagent_eval``, the
``skip_*`` flags -- onto the snapshot record. The retry path used to
``execution.config_snapshot.copy()``, which after externalization copies only the
pointer: the retry loses every eval flag and silently becomes a normal run, so an
eval retry executes all seven extractors instead of the isolated target (7x
provider spend) and writes results that never score.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.execution_snapshot_store import hydrate_snapshot

pytestmark = pytest.mark.unit


def _execution(*, config_snapshot, snapshot_record=None):
    return SimpleNamespace(
        id=6887,
        config_snapshot=config_snapshot,
        config_snapshot_id=getattr(snapshot_record, "id", None),
        snapshot_record=snapshot_record,
    )


class TestRetryHydratesEvalFlags:
    def test_externalized_snapshot_yields_the_full_payload(self):
        payload = {
            "eval_run": True,
            "subagent_eval": "cmdline",
            "skip_rank_agent": True,
            "ranking_threshold": 6.0,
        }
        execution = _execution(
            config_snapshot={"snapshot_id": 42},
            snapshot_record=SimpleNamespace(id=42, payload=payload),
        )

        assert hydrate_snapshot(execution) == payload

    def test_pointer_copy_would_have_dropped_the_eval_flags(self):
        """Pin the exact defect: copying the row's own JSON loses everything."""
        execution = _execution(
            config_snapshot={"snapshot_id": 42},
            snapshot_record=SimpleNamespace(id=42, payload={"eval_run": True, "subagent_eval": "cmdline"}),
        )

        assert "eval_run" not in execution.config_snapshot.copy()
        assert hydrate_snapshot(execution)["eval_run"] is True

    def test_snapshot_id_pointer_is_not_carried_into_the_retry_config(self):
        """The stray pointer key must not survive into the new snapshot/hash."""
        execution = _execution(
            config_snapshot={"snapshot_id": 42},
            snapshot_record=SimpleNamespace(id=42, payload={"eval_run": True}),
        )

        assert "snapshot_id" not in hydrate_snapshot(execution)

    def test_legacy_inline_snapshot_still_hydrates(self):
        """Pre-externalization rows keep working through the same call."""
        execution = _execution(config_snapshot={"eval_run": True, "subagent_eval": "registry"})

        assert hydrate_snapshot(execution) == {"eval_run": True, "subagent_eval": "registry"}

    def test_missing_snapshot_is_an_empty_dict_not_a_crash(self):
        assert hydrate_snapshot(_execution(config_snapshot=None)) == {}
