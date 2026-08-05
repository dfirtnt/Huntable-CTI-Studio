"""Regression coverage for immutable workflow execution configuration.

The property under test: once an execution is dispatched, editing the active workflow
configuration cannot change how that execution behaves, and every node reports the same
snapshot hash.

Before this, the dispatch snapshot omitted ``agent_prompts``, which made the
completeness gate in ``run_workflow()`` fail every time, so the worker re-read
``get_active_config()`` at execution time — minutes or hours after dispatch.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.database.models import AgenticWorkflowConfigTable  # noqa: E402
from src.services.workflow_config_snapshot import (  # noqa: E402
    SNAPSHOT_CONFIG_FIELDS,
    SNAPSHOT_HASH_KEY,
    SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION_KEY,
    build_config_snapshot,
    canonical_snapshot_hash,
    rehash_snapshot,
    snapshot_is_complete,
)


def make_config(**overrides):
    """A stand-in for an AgenticWorkflowConfigTable row."""
    base = {
        "id": 42,
        "version": 7,
        "min_hunt_score": 97.0,
        "ranking_threshold": 6.0,
        "similarity_threshold": 0.5,
        "junk_filter_threshold": 0.8,
        "auto_trigger_hunt_score_threshold": 100.0,
        "agent_prompts": {
            "RankAgent": {"prompt": "rank v1"},
            "SigmaAgent": {"prompt": "sigma v1"},
            "ExtractAgentSettings": {"disabled_agents": ["ServicesExtract"]},
        },
        "agent_models": {"RankAgent": "m1", "RankAgent_provider": "lmstudio"},
        "rank_agent_enabled": True,
        "sigma_fallback_enabled": False,
        "cmdline_attention_preprocessor_enabled": True,
        "proc_tree_attention_preprocessor_enabled": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestSnapshotSchemaCompleteness:
    """Subtask: the snapshot schema must cover everything an execution depends on."""

    def test_snapshot_carries_every_declared_field(self) -> None:
        snapshot = build_config_snapshot(make_config())
        missing = [f for f in SNAPSHOT_CONFIG_FIELDS if f not in snapshot]
        assert not missing, f"snapshot missing declared fields: {missing}"
        assert snapshot_is_complete(snapshot)

    def test_snapshot_covers_every_behavior_affecting_config_column(self) -> None:
        """Guards against a new config column silently escaping the snapshot.

        A column that affects execution but is absent from SNAPSHOT_CONFIG_FIELDS
        reintroduces the runtime-lookup bug for that setting.
        """
        non_behavioral = {
            "id",  # captured as config_id
            "version",  # captured as config_version
            "is_active",  # selection criterion, not behavior
            "description",  # operator annotation
            "created_at",
            "updated_at",
        }
        columns = {c.name for c in AgenticWorkflowConfigTable.__table__.columns} - non_behavioral
        uncovered = sorted(columns - set(SNAPSHOT_CONFIG_FIELDS))
        assert not uncovered, (
            f"AgenticWorkflowConfigTable columns not captured in the execution snapshot: {uncovered}. "
            "Add them to SNAPSHOT_CONFIG_FIELDS (and bump SNAPSHOT_SCHEMA_VERSION) or list them as "
            "non-behavioral in this test."
        )

    def test_resolved_prompts_and_disabled_agents_are_captured(self) -> None:
        """agent_prompts carries the disabled-sub-agent settings; its absence was the original bug."""
        snapshot = build_config_snapshot(make_config())
        assert snapshot["agent_prompts"]["ExtractAgentSettings"]["disabled_agents"] == ["ServicesExtract"]
        assert snapshot["agent_models"]["RankAgent_provider"] == "lmstudio"

    def test_missing_config_still_yields_a_complete_snapshot(self) -> None:
        snapshot = build_config_snapshot(None)
        assert snapshot_is_complete(snapshot)
        assert snapshot["min_hunt_score"] == 97.0
        assert snapshot["agent_prompts"] == {}
        assert snapshot["config_id"] is None

    def test_null_jsonb_columns_normalize_to_dicts(self) -> None:
        snapshot = build_config_snapshot(make_config(agent_prompts=None, agent_models=None))
        assert snapshot["agent_prompts"] == {}
        assert snapshot["agent_models"] == {}

    def test_schema_version_is_stamped(self) -> None:
        snapshot = build_config_snapshot(make_config())
        assert snapshot[SNAPSHOT_SCHEMA_VERSION_KEY] == SNAPSHOT_SCHEMA_VERSION

    def test_extra_keys_cannot_forge_the_hash_or_schema_version(self) -> None:
        snapshot = build_config_snapshot(
            make_config(),
            extra={SNAPSHOT_HASH_KEY: "forged", SNAPSHOT_SCHEMA_VERSION_KEY: 999},
        )
        assert snapshot[SNAPSHOT_HASH_KEY] != "forged"
        assert snapshot[SNAPSHOT_SCHEMA_VERSION_KEY] == SNAPSHOT_SCHEMA_VERSION


class TestSnapshotHashing:
    """Subtask: resolve and hash before dispatch; all nodes see the same hash."""

    def test_identical_config_hashes_identically(self) -> None:
        assert (
            build_config_snapshot(make_config())[SNAPSHOT_HASH_KEY]
            == build_config_snapshot(make_config())[SNAPSHOT_HASH_KEY]
        )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("min_hunt_score", 50.0),
            ("ranking_threshold", 9.0),
            ("similarity_threshold", 0.9),
            ("junk_filter_threshold", 0.1),
            ("auto_trigger_hunt_score_threshold", 10.0),
            ("rank_agent_enabled", False),
            ("sigma_fallback_enabled", True),
            ("cmdline_attention_preprocessor_enabled", False),
            ("proc_tree_attention_preprocessor_enabled", False),
            ("agent_models", {"RankAgent": "m2"}),
            ("agent_prompts", {"RankAgent": {"prompt": "rank v2"}}),
            ("version", 8),
        ],
    )
    def test_any_behavioral_change_changes_the_hash(self, field, value) -> None:
        baseline = build_config_snapshot(make_config())[SNAPSHOT_HASH_KEY]
        changed = build_config_snapshot(make_config(**{field: value}))[SNAPSHOT_HASH_KEY]
        assert changed != baseline, f"changing {field} did not change the snapshot hash"

    def test_hash_ignores_key_insertion_order(self) -> None:
        a = {"alpha": 1, "beta": {"x": 1, "y": 2}}
        b = {"beta": {"y": 2, "x": 1}, "alpha": 1}
        assert canonical_snapshot_hash(a) == canonical_snapshot_hash(b)

    def test_hash_ignores_who_dispatched(self) -> None:
        """Same configuration triggered by different people must compare equal."""
        one = build_config_snapshot(make_config(), extra={"initiated_by": {"user_id": "alice"}})
        two = build_config_snapshot(make_config(), extra={"initiated_by": {"user_id": "bob"}})
        assert one[SNAPSHOT_HASH_KEY] == two[SNAPSHOT_HASH_KEY]

    def test_run_scoped_flags_are_hashed(self) -> None:
        """Eval flags change how a run behaves, so they must be part of its identity."""
        plain = build_config_snapshot(make_config())[SNAPSHOT_HASH_KEY]
        evaluated = build_config_snapshot(make_config(), extra={"eval_run": True})[SNAPSHOT_HASH_KEY]
        assert plain != evaluated

    def test_rehash_updates_a_derived_snapshot(self) -> None:
        original = build_config_snapshot(make_config())
        derived = dict(original)
        derived["agent_models"] = {"RankAgent": "swapped-on-retry"}
        rehashed = rehash_snapshot(derived)
        assert rehashed[SNAPSHOT_HASH_KEY] != original[SNAPSHOT_HASH_KEY]
        assert rehashed[SNAPSHOT_HASH_KEY] == canonical_snapshot_hash(derived)


class TestLegacySnapshotDetection:
    def test_pre_change_partial_snapshot_is_incomplete(self) -> None:
        """The exact shape trigger_workflow() used to persist — no agent_prompts."""
        legacy = {
            "min_hunt_score": 97.0,
            "ranking_threshold": 6.0,
            "similarity_threshold": 0.5,
            "junk_filter_threshold": 0.8,
            "agent_models": {},
            "rank_agent_enabled": True,
            "cmdline_attention_preprocessor_enabled": True,
            "proc_tree_attention_preprocessor_enabled": True,
            "config_id": 1,
            "config_version": 1,
        }
        assert not snapshot_is_complete(legacy)

    @pytest.mark.parametrize("value", [None, {}, "not-a-dict", 42, []])
    def test_non_dict_snapshots_are_incomplete(self, value) -> None:
        assert not snapshot_is_complete(value)


class TestConfigChangesAfterDispatchCannotAffectExecution:
    """The end-to-end property the task is about."""

    def test_snapshot_is_decoupled_from_the_config_row(self) -> None:
        config = make_config()
        snapshot = build_config_snapshot(config)
        hash_at_dispatch = snapshot[SNAPSHOT_HASH_KEY]

        # Operator edits the active configuration after dispatch — including mutating the
        # nested prompt dict in place, which a shallow copy would have leaked.
        config.agent_prompts["RankAgent"]["prompt"] = "rank v2 EDITED"
        config.agent_models["RankAgent"] = "different-model"
        config.rank_agent_enabled = False
        config.sigma_fallback_enabled = True
        config.junk_filter_threshold = 0.1

        assert snapshot["rank_agent_enabled"] is True
        assert snapshot["sigma_fallback_enabled"] is False
        assert snapshot["junk_filter_threshold"] == 0.8
        assert snapshot["agent_models"]["RankAgent"] == "m1"
        assert snapshot["agent_prompts"]["RankAgent"]["prompt"] == "rank v1"
        assert snapshot[SNAPSHOT_HASH_KEY] == hash_at_dispatch
        assert canonical_snapshot_hash(snapshot) == hash_at_dispatch

    def test_every_node_reads_the_same_snapshot_hash(self) -> None:
        """Nodes read state["config"], seeded once from execution.config_snapshot."""
        from src.workflows.agentic_workflow import (
            _snapshot_agent_models,
            _snapshot_agent_prompts,
            _snapshot_config,
        )

        snapshot = build_config_snapshot(make_config())
        state = {"config": dict(snapshot), "execution_id": 1}

        # Simulating the four former get_active_config() call sites.
        os_detection_view = _snapshot_agent_prompts(state)
        rank_view = _snapshot_config(state)
        sigma_view = _snapshot_config(state)
        similarity_view = _snapshot_agent_models(state)

        assert rank_view[SNAPSHOT_HASH_KEY] == snapshot[SNAPSHOT_HASH_KEY]
        assert sigma_view[SNAPSHOT_HASH_KEY] == snapshot[SNAPSHOT_HASH_KEY]
        assert os_detection_view == snapshot["agent_prompts"]
        assert similarity_view == snapshot["agent_models"]

    def test_accessors_read_a_pydantic_workflow_state_not_just_a_dict(self) -> None:
        """LangGraph hands nodes a WorkflowState model, not a dict.

        An ``isinstance(state, dict)`` guard in the accessors resolves to an empty
        config on every real run — which silently disables sigma_fallback_enabled,
        the configured junk-filter threshold, and every snapshot prompt.
        """
        from src.workflows.agentic_workflow import (
            _snapshot_agent_models,
            _snapshot_agent_prompts,
            _snapshot_config,
        )

        snapshot = build_config_snapshot(make_config())

        class FakeWorkflowState:
            """Duck-types the .get() access LangGraph's pydantic state supports."""

            def __init__(self, payload):
                self._payload = payload

            def get(self, key, default=None):
                return self._payload.get(key, default)

        state = FakeWorkflowState({"config": snapshot, "execution_id": 1})
        assert _snapshot_config(state)["sigma_fallback_enabled"] is False
        assert _snapshot_config(state)["junk_filter_threshold"] == 0.8
        assert _snapshot_agent_prompts(state) == snapshot["agent_prompts"]
        assert _snapshot_agent_models(state) == snapshot["agent_models"]

    def test_accessors_fall_back_to_attribute_access(self) -> None:
        from src.workflows.agentic_workflow import _snapshot_config

        snapshot = build_config_snapshot(make_config())
        assert _snapshot_config(SimpleNamespace(config=snapshot))["config_id"] == 42

    def test_snapshot_accessors_tolerate_malformed_state(self) -> None:
        from src.workflows.agentic_workflow import (
            _snapshot_agent_models,
            _snapshot_agent_prompts,
            _snapshot_config,
        )

        for bad in ({}, {"config": None}, {"config": "nope"}, "not-a-dict"):
            assert _snapshot_config(bad) == {}
            assert _snapshot_agent_prompts(bad) == {}
            assert _snapshot_agent_models(bad) == {}
