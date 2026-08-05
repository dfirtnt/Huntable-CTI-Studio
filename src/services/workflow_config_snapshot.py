"""Immutable configuration snapshots for agentic workflow executions.

An execution's ``config_snapshot`` is the single source of truth for how that run
behaves. It is resolved and hashed once, before dispatch, and persisted in the same
transaction as the execution row. Workflow nodes read the snapshot and never re-read
the active configuration, so editing prompts, models, or thresholds after dispatch
cannot change a run that is already queued or in flight.

Before this module the dispatch snapshot omitted ``agent_prompts`` (and therefore the
disabled-sub-agent settings nested under it), ``sigma_fallback_enabled``, and
``auto_trigger_hunt_score_threshold``. Because ``agent_prompts`` was missing, the
completeness gate in ``run_workflow()`` always failed and the worker fell back to
``get_active_config()`` at execution time — minutes or hours after dispatch. Every node
that called ``get_active_config()`` directly had the same exposure.

Legacy executions dispatched before this module still carry partial snapshots.
:func:`snapshot_is_complete` identifies them so the workflow can keep its existing
active-config fallback for those rows only.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

# Bump when the field set below changes in a way that makes older snapshots
# non-comparable. Stored on every snapshot so a run's schema is self-describing.
SNAPSHOT_SCHEMA_VERSION = 1

SNAPSHOT_HASH_KEY = "snapshot_hash"
SNAPSHOT_SCHEMA_VERSION_KEY = "snapshot_schema_version"

# Keys excluded from the hash: the hash itself (self-reference), and provenance that
# describes *who* dispatched rather than *how* the run behaves. Two runs of identical
# configuration triggered by different people must hash identically — that is what
# makes the hash usable for reproducibility comparisons.
_HASH_EXCLUDED_KEYS = frozenset({SNAPSHOT_HASH_KEY, "initiated_by"})

# Every configuration field a workflow node reads. Adding a field that affects execution
# without adding it here reintroduces the runtime-lookup bug, so this tuple is the
# contract: `tests/services/test_workflow_config_snapshot.py` asserts it covers every
# behavior-affecting column on AgenticWorkflowConfigTable.
SNAPSHOT_CONFIG_FIELDS: tuple[str, ...] = (
    # Thresholds
    "min_hunt_score",
    "ranking_threshold",
    "similarity_threshold",
    "junk_filter_threshold",
    "auto_trigger_hunt_score_threshold",
    # Resolved prompts and models (models carry the per-agent `*_provider` keys;
    # prompts carry ExtractAgentSettings.disabled_agents)
    "agent_prompts",
    "agent_models",
    # Toggles and fallback behavior
    "rank_agent_enabled",
    "sigma_fallback_enabled",
    "cmdline_attention_preprocessor_enabled",
    "proc_tree_attention_preprocessor_enabled",
    # Identity of the configuration this snapshot was resolved from
    "config_id",
    "config_version",
)

# Defaults applied when no active configuration exists, mirroring the column defaults on
# AgenticWorkflowConfigTable. A snapshot is always complete, even in that degraded case.
_FIELD_DEFAULTS: dict[str, Any] = {
    "min_hunt_score": 97.0,
    "ranking_threshold": 6.0,
    "similarity_threshold": 0.5,
    "junk_filter_threshold": 0.8,
    "auto_trigger_hunt_score_threshold": 100.0,
    "agent_prompts": {},
    "agent_models": {},
    "rank_agent_enabled": True,
    "sigma_fallback_enabled": False,
    "cmdline_attention_preprocessor_enabled": True,
    "proc_tree_attention_preprocessor_enabled": True,
    "config_id": None,
    "config_version": None,
}

_JSONB_FIELDS = frozenset({"agent_prompts", "agent_models"})

# Snapshot keys whose source column is named differently on AgenticWorkflowConfigTable.
# Without this the identity of the configuration silently snapshots as None, because the
# row has no `config_id`/`config_version` attribute at all.
_FIELD_SOURCE_ATTRS: dict[str, str] = {
    "config_id": "id",
    "config_version": "version",
}


def _resolve_field(config: Any, field: str) -> Any:
    """Read one field off a config row, falling back to its column default.

    ``getattr`` with a default rather than direct access: config rows predating a column
    addition, and the ``None`` config case, must both still yield a complete snapshot.

    JSONB values are deep-copied. The ORM hands back the live mutable dict attached to
    the session's identity map, so keeping the reference would let a later edit of the
    active configuration reach into an already-dispatched execution's snapshot — the
    precise failure this module exists to prevent.
    """
    default = _FIELD_DEFAULTS[field]
    if config is None:
        return copy.deepcopy(default)
    value = getattr(config, _FIELD_SOURCE_ATTRS.get(field, field), default)
    if value is None:
        # NULL JSONB columns normalize to {} so downstream `.get()` calls are safe;
        # config_id/config_version legitimately stay None.
        return copy.deepcopy(default) if field in _JSONB_FIELDS or default is not None else None
    return copy.deepcopy(value) if field in _JSONB_FIELDS else value


def canonical_snapshot_hash(snapshot: dict[str, Any]) -> str:
    """SHA-256 over the canonicalized snapshot.

    Canonical form is JSON with sorted keys and no insertion-order or whitespace
    sensitivity, so two snapshots that differ only in dict ordering hash identically.
    """
    payload = {k: v for k, v in snapshot.items() if k not in _HASH_EXCLUDED_KEYS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_config_snapshot(config: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve *config* into a complete, hashed, immutable execution snapshot.

    Args:
        config: an ``AgenticWorkflowConfigTable`` row, or None to snapshot the column
            defaults (a run with no active configuration is still reproducible).
        extra: run-scoped keys layered on top — eval flags (``eval_run``,
            ``subagent_eval``, ``skip_rank_agent``), fixture content, ``initiated_by``.
            These are part of the run's contract and are hashed with it, except for the
            provenance keys listed in ``_HASH_EXCLUDED_KEYS``.

    Returns:
        A dict carrying every field in ``SNAPSHOT_CONFIG_FIELDS`` plus
        ``snapshot_schema_version`` and ``snapshot_hash``.
    """
    snapshot: dict[str, Any] = {field: _resolve_field(config, field) for field in SNAPSHOT_CONFIG_FIELDS}
    snapshot[SNAPSHOT_SCHEMA_VERSION_KEY] = SNAPSHOT_SCHEMA_VERSION

    if extra:
        # Callers layering eval flags must not be able to drop the schema version or
        # forge a hash; both are recomputed/reasserted below.
        for key, value in extra.items():
            if key != SNAPSHOT_HASH_KEY:
                snapshot[key] = value
        snapshot[SNAPSHOT_SCHEMA_VERSION_KEY] = SNAPSHOT_SCHEMA_VERSION

    snapshot[SNAPSHOT_HASH_KEY] = canonical_snapshot_hash(snapshot)
    return snapshot


def rehash_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *snapshot* with a freshly computed hash.

    For paths that legitimately derive a new snapshot from an old one — a retry that
    intentionally picks up current models — so the new execution's hash describes the
    configuration it will actually run under rather than the one it was copied from.
    """
    rehashed = dict(snapshot)
    rehashed.setdefault(SNAPSHOT_SCHEMA_VERSION_KEY, SNAPSHOT_SCHEMA_VERSION)
    rehashed[SNAPSHOT_HASH_KEY] = canonical_snapshot_hash(rehashed)
    return rehashed


def snapshot_is_complete(snapshot: Any) -> bool:
    """True when *snapshot* carries every field a workflow node needs.

    Executions dispatched before this module return False; ``run_workflow()`` keeps its
    active-config fallback for exactly those rows.
    """
    if not isinstance(snapshot, dict):
        return False
    return all(field in snapshot for field in SNAPSHOT_CONFIG_FIELDS)
