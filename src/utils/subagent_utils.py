"""Utilities for normalizing subagent identifiers."""

from typing import Any

# Maps lower-cased agent names to their canonical subagent alias
AGENT_TO_SUBAGENT = {
    "cmdlineextract": "cmdline",
    "proctreeextract": "process_lineage",
    "huntqueriesextract": "hunt_queries",
}

# Reverse map from canonical alias to agent name (CamelCase)
SUBAGENT_TO_AGENT = {alias: agent for agent, alias in AGENT_TO_SUBAGENT.items()}

# Acceptable alias values mapped to canonical names
SUBAGENT_CANONICAL = {
    "cmdline": "cmdline",
    "cmdlineextract": "cmdline",
    "commandline": "cmdline",
    "cmdline_items": "cmdline",
    "process_lineage": "process_lineage",
    "processlineage": "process_lineage",
    "process-lineage": "process_lineage",
    "proctreeextract": "process_lineage",
    "hunt_queries": "hunt_queries",
    "huntqueries": "hunt_queries",
    "hunt-queries": "hunt_queries",
    "huntqueriesextract": "hunt_queries",
    "hunt_queries_edr": "hunt_queries_edr",
    "huntqueriesedr": "hunt_queries_edr",
    "hunt-queries-edr": "hunt_queries_edr",
    "hunt_queries_sigma": "hunt_queries_sigma",
    "huntqueriessigma": "hunt_queries_sigma",
    "hunt-queries-sigma": "hunt_queries_sigma",
}

__all__ = [
    "normalize_subagent_name",
    "build_subagent_lookup_values",
    "AGENT_TO_SUBAGENT",
    "SUBAGENT_TO_AGENT",
]


def normalize_subagent_name(value: Any) -> str | None:
    """Return the canonical alias for a given subagent identifier."""
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    return SUBAGENT_CANONICAL.get(normalized)


def build_subagent_lookup_values(raw_subagent: str | None) -> tuple[str | None, set[str]]:
    """Return canonical alias plus a set of matchable subagent names for querying."""
    candidates: set[str] = set()

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
