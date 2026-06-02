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
    # SigmaHQ fragments registry mutations across registry_event / registry_set /
    # registry_add / registry_delete — one telemetry class (same Sysmon EIDs 12-14,
    # same TargetObject/Details fields). Consolidated 2026-06-01 so a registry_set rule
    # is compared against a registry_event rule instead of being false-NOVEL (Option C).
    "windows.registry_event": {
        ("windows", "registry_event", None, None),
        ("windows", "registry_set", None, None),
        ("windows", "registry_add", None, None),
        ("windows", "registry_delete", None, None),
        ("windows", None, "sysmon", 12),  # Object create/delete
        ("windows", None, "sysmon", 13),  # Value Set
        ("windows", None, "sysmon", 14),  # Key/Value Rename
        ("windows", None, "security", 4657),  # Registry value modified
    },
    # File telemetry: SigmaHQ uses file_event / file_delete / file_access / file_rename /
    # file_change — one class (TargetFilename/Image fields; Sysmon EIDs 11/23/26). Added
    # 2026-06-01 (Option C). NOTE: the *.webserver keyword-only family is deliberately NOT
    # added here — Spike A (2026-06-01) showed the precomputed extractor yields empty atoms
    # for keyword-list selections, so routing webserver rules to the precomputed path would
    # regress the working on-the-fly keyword comparison. Gated on the keyword-parity work
    # (Conditional B / collapse-the-extractors issue).
    "windows.file_event": {
        ("windows", "file_event", None, None),
        ("windows", "file_delete", None, None),
        ("windows", "file_access", None, None),
        ("windows", "file_rename", None, None),
        ("windows", "file_change", None, None),
        ("windows", None, "sysmon", 11),  # FileCreate
        ("windows", None, "sysmon", 23),  # FileDelete (archived)
        ("windows", None, "sysmon", 26),  # FileDeleteDetected
    },
    # DLL/image load telemetry (Sysmon EID 7). Added 2026-06-01 (Option B). Field-based
    # (ImageLoaded/Signed/Signature) — verified by spike to produce comparable atoms.
    "windows.image_load": {
        ("windows", "image_load", None, None),
        ("windows", None, "sysmon", 7),
    },
    # Network connection telemetry (Sysmon EID 3). Added 2026-06-01 (Option B). Field-based
    # (DestinationIp/DestinationPort/Initiated/Protocol).
    "windows.network_connection": {
        ("windows", "network_connection", None, None),
        ("windows", None, "sysmon", 3),
    },
    "windows.service": {
        ("windows", "service_creation", None, None),
        ("windows", None, "system", 7045),  # Service install
        ("windows", None, "system", 7036),  # Service start/stop
        ("windows", None, "security", 4697),  # Service install (security log)
    },
    # Known limitation: scheduled-task behavior observable across multiple telemetry sources
    # (schtasks.exe via process_creation, \Tasks\ writes via file_event, TaskCache keys via
    # registry_event) remains in separate canonical buckets. Rules targeting the same task
    # creation behavior across these sources will not be compared and may produce false-NOVEL
    # classifications. This cross-telemetry case is tracked separately.
    "windows.scheduled_task": {
        ("windows", "taskscheduler", None, None),  # category form (forward-compat)
        ("windows", None, "taskscheduler", None),  # service form (standard SigmaHQ)
        ("windows", None, "security", 4698),  # Task created
        ("windows", None, "security", 4699),  # Task deleted
        ("windows", None, "security", 4700),  # Task enabled
        ("windows", None, "security", 4702),  # Task updated
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
