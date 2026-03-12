"""
Canonical telemetry class resolution for Sigma rules.

Two distinct behaviors (must be explicit at call site):
- Unknown class: If a rule cannot map to any canonical class → raise
  UnknownTelemetryClassError. Caller (similarity_engine) propagates; CLI exits non-zero.
- Class mismatch: If both rules map, but to different canonical classes → do not raise.
  Return SimilarityResult(similarity=0, reason_flags=["canonical_class_mismatch"]).
"""

from sigma_similarity.errors import UnknownTelemetryClassError

# (product, category, service, event_id). None means "any" for that slot.
# Static, versioned. No dynamic inference.
CANONICAL_CLASS_REGISTRY: dict[str, set[tuple[str | None, str | None, str | None, int | None]]] = {
    "windows.process_creation": {
        ("windows", "process_creation", None, None),
        ("windows", None, "sysmon", 1),
        ("windows", None, "security", 4688),
    },
    "linux.process_creation": {
        ("linux", "process_creation", None, None),
    },
}


def _extract_event_id_from_detection(detection: dict) -> int | None:
    """Extract implicit EventID from detection if present. No guessing."""
    if not isinstance(detection, dict):
        return None
    for key, value in detection.items():
        if key == "condition":
            continue
        if not isinstance(value, dict):
            continue
        for field_name, field_value in value.items():
            base = field_name.split("|")[0] if "|" in field_name else field_name
            if base in ("EventID", "EventId", "eventid", "event_id"):
                if isinstance(field_value, int):
                    return field_value
                if isinstance(field_value, list) and len(field_value) == 1 and isinstance(field_value[0], int):
                    return field_value[0]
                return None  # multiple or non-int: no single event_id
    return None


def _rule_to_tuple(rule: dict) -> tuple[str | None, str | None, str | None, int | None]:
    """Derive (product, category, service, event_id) from rule. Explicit extraction only."""
    logsource = rule.get("logsource")
    if not isinstance(logsource, dict):
        return (None, None, None, None)
    product = logsource.get("product")
    category = logsource.get("category")
    service = logsource.get("service")
    if isinstance(product, str):
        product = product.strip().lower() or None
    if isinstance(category, str):
        category = category.strip().lower() or None
    if isinstance(service, str):
        service = service.strip().lower() or None
    event_id = _extract_event_id_from_detection(rule.get("detection") or {})
    return (product, category, service, event_id)


def resolve_canonical_class(rule: dict) -> str:
    """Resolve rule to canonical telemetry class name.

    If the rule cannot map to any canonical class → raise UnknownTelemetryClassError.
    Do NOT return a result for unknown class; caller must re-raise.
    """
    t = _rule_to_tuple(rule)
    for class_name, tuples in CANONICAL_CLASS_REGISTRY.items():
        if t in tuples:
            return class_name
    raise UnknownTelemetryClassError(f"Rule logsource/event_id did not match any canonical class: {t}")
