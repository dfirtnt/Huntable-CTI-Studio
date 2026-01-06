"""Utilities for normalizing subagent identifiers."""
from typing import Any, Optional, Set, Tuple

# Maps lower-cased agent names to their canonical subagent alias
AGENT_TO_SUBAGENT = {
    "cmdlineextract": "cmdline",
    "sigextract": "sigma_queries",
    "eventcodeextract": "event_ids",
    "proctreeextract": "process_lineage",
    "regextract": "registry_keys",
}

# Reverse map from canonical alias to agent name (CamelCase)
SUBAGENT_TO_AGENT = {alias: agent for agent, alias in AGENT_TO_SUBAGENT.items()}

# Acceptable alias values mapped to canonical names
SUBAGENT_CANONICAL = {
    "cmdline": "cmdline",
    "cmdlineextract": "cmdline",
    "commandline": "cmdline",
    "cmdline_items": "cmdline",
    "sigma_queries": "sigma_queries",
    "sigmaqueries": "sigma_queries",
    "sigextract": "sigma_queries",
    "event_ids": "event_ids",
    "eventids": "event_ids",
    "eventcodeextract": "event_ids",
    "process_lineage": "process_lineage",
    "processlineage": "process_lineage",
    "process-lineage": "process_lineage",
    "proctreeextract": "process_lineage",
    "registry_keys": "registry_keys",
    "registrykeys": "registry_keys",
    "regextract": "registry_keys",
}

__all__ = [
    "normalize_subagent_name",
    "build_subagent_lookup_values",
    "AGENT_TO_SUBAGENT",
    "SUBAGENT_TO_AGENT",
]


def normalize_subagent_name(value: Any) -> Optional[str]:
    """Return the canonical alias for a given subagent identifier."""
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    return SUBAGENT_CANONICAL.get(normalized)


def build_subagent_lookup_values(raw_subagent: Optional[str]) -> Tuple[Optional[str], Set[str]]:
    """Return canonical alias plus a set of matchable subagent names for querying."""
    candidates: Set[str] = set()

    if raw_subagent:
        raw_value = str(raw_subagent).strip()
        if raw_value:
            candidates.add(raw_value)
            candidates.add(raw_value.lower())

    canonical = normalize_subagent_name(raw_subagent)
    if canonical:
        candidates.add(canonical)
        agent_name = SUBAGENT_TO_AGENT.get(canonical)
        if agent_name:
            candidates.add(agent_name)
            candidates.add(agent_name.lower())

    return canonical, candidates
