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
    # macOS process telemetry — sibling of windows/linux. Category-only (no Sysmon).
    # Added 2026-06-02. Kept distinct from windows/linux: same category, different OS
    # telemetry; cross-OS comparison would be false-similar.
    "macos.process_creation": {
        ("macos", "process_creation", None, None),
    },
    # Clean Sysmon host-telemetry categories — each 1:1 with a Sysmon EID, all
    # field-based (no keyword ambiguity). Added 2026-06-02; same risk profile as
    # image_load (EID 7) / network_connection (EID 3).
    "windows.process_access": {  # Sysmon EID 10 — SourceImage/TargetImage/GrantedAccess/CallTrace
        ("windows", "process_access", None, None),
        ("windows", None, "sysmon", 10),
    },
    "windows.pipe_created": {  # Sysmon EID 17 (create) + 18 (connect) — PipeName
        ("windows", "pipe_created", None, None),
        ("windows", None, "sysmon", 17),
        ("windows", None, "sysmon", 18),
    },
    "windows.create_remote_thread": {  # Sysmon EID 8 — SourceImage/TargetImage/StartModule
        ("windows", "create_remote_thread", None, None),
        ("windows", None, "sysmon", 8),
    },
    "windows.driver_load": {  # Sysmon EID 6 — ImageLoaded/Signature/Signed
        ("windows", "driver_load", None, None),
        ("windows", None, "sysmon", 6),
    },
    "windows.create_stream_hash": {  # Sysmon EID 15 — ADS write; TargetFilename/Contents
        ("windows", "create_stream_hash", None, None),
        ("windows", None, "sysmon", 15),
    },
    # Windows DNS query telemetry — Sysmon EID 22 AND the native DNS-Client
    # channel (Microsoft-Windows-DNS-Client/Operational, EID 3008). Both use the
    # QueryName field, so they are one class. Kept distinct from network.dns
    # (zeek/generic, `query` field) — bridging QueryName↔query is a field-alias
    # decision, not a mechanical merge.
    "windows.dns_query": {
        ("windows", "dns_query", None, None),
        ("windows", None, "sysmon", 22),
        ("windows", None, "dns-client", 3008),
        ("windows", None, "dns-client", None),
    },
    # Network/generic DNS query telemetry — SigmaHQ generic `category: dns`
    # (cross-platform) and zeek `service: dns`. Both use the `query` field, so they
    # are field-compatible and comparable. Added 2026-06-02.
    "network.dns": {
        (None, "dns", None, None),
        ("zeek", None, "dns", None),
    },
    # PowerShell telemetry — three SEPARATE logging mechanisms, kept as distinct
    # classes (different EID + field each). Added 2026-06-02. Unlike registry_*
    # (one EID range, one field → merged in Option C), these are genuinely different
    # telemetry sources and different fidelity. Cross-source comparison of the same
    # tradecraft (ScriptBlockText vs Payload vs Data) is a separate field-alias
    # decision with false-merge risk — deliberately NOT done here.
    "windows.ps_script": {  # Script Block Logging, EID 4104 — ScriptBlockText
        ("windows", "ps_script", None, None),
        ("windows", None, "powershell", 4104),
    },
    "windows.ps_module": {  # Module Logging, EID 4103 — Payload/ContextInfo
        ("windows", "ps_module", None, None),
        ("windows", None, "powershell", 4103),
    },
    "windows.ps_classic_start": {  # Classic PowerShell log, EID 400 — Data/HostApplication
        ("windows", "ps_classic_start", None, None),
        ("windows", None, "powershell-classic", 400),
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
    # 2026-06-01 (Option C).
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
    # Web access-log telemetry (SigmaHQ `category: webserver`, no product). Added
    # 2026-06-02 once Conditional B (commit 5514381b) gave the precomputed extractor
    # keyword-list parity — webserver rules are predominantly keyword selections
    # (XSS/SSTI/Log4j/path-traversal) that Spike A (2026-06-01) showed extracted to
    # empty atoms before that fix. The cs-* fields (cs-method/cs-uri-stem/cs-uri-query/
    # sc-status) are not in FIELD_ALIAS_MAP, so they resolve as-is (lowercased) — still
    # comparable rule-to-rule since both sides use the same SigmaHQ field names. `proxy`
    # is a sibling web category with overlapping fields but distinct telemetry; it is
    # tracked in the long-tail Coverage-Chain item, not folded in here.
    "web.webserver": {
        (None, "webserver", None, None),
    },
    # Web proxy access logs (SigmaHQ `category: proxy`, no product). Sibling of
    # webserver — overlapping cs-*/c-uri/c-useragent fields + keyword lists
    # (de-risked by Conditional B) — but DISTINCT telemetry (proxy logs ≠ origin
    # access logs), so a separate class. Added 2026-06-02.
    "web.proxy": {
        (None, "proxy", None, None),
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
