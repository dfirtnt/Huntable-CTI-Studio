"""Canonical class: same class comparable; different class similarity 0; unknown class raises."""

import pytest
from sigma_similarity.canonical_logsource import (
    _extract_event_id_from_detection,
    resolve_canonical_class,
)
from sigma_similarity.errors import UnknownTelemetryClassError
from sigma_similarity.similarity_engine import compare_rules


def test_same_class_comparable(rule_windows_process_creation, rule_windows_process_creation_two):
    r1 = rule_windows_process_creation
    r2 = rule_windows_process_creation_two
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.process_creation"
    assert "canonical_class_mismatch" not in result.explanation["reason_flags"]


def test_different_class_returns_zero_with_reason():
    r_win = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"Image": "x"}, "condition": "selection"},
    }
    r_lin = {
        "logsource": {"product": "linux", "category": "process_creation"},
        "detection": {"selection": {"Image": "y"}, "condition": "selection"},
    }
    result = compare_rules(r_win, r_lin)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


def test_unknown_class_raises():
    r = {
        "logsource": {"product": "unknown_product", "category": "unknown"},
        "detection": {"selection": {"Image": "x"}, "condition": "selection"},
    }
    with pytest.raises(UnknownTelemetryClassError):
        resolve_canonical_class(r)


# --- windows.registry_event resolution ---


def test_registry_event_category_resolves():
    r = {
        "logsource": {"product": "windows", "category": "registry_event"},
        "detection": {"s": {"TargetObject|contains": "\\Run"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.registry_event"


@pytest.mark.parametrize("event_id", [12, 13, 14])
def test_sysmon_registry_event_ids_resolve(event_id):
    r = {
        "logsource": {"product": "windows", "service": "sysmon"},
        "detection": {"s": {"EventID": event_id}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.registry_event"


def test_security_4657_resolves_registry_event():
    r = {
        "logsource": {"product": "windows", "service": "security"},
        "detection": {"s": {"EventID": 4657}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.registry_event"


# --- windows.registry_event family consolidation (Option C) ---
# SigmaHQ fragments registry mutations across registry_event / registry_set /
# registry_add / registry_delete. They are one telemetry class; all must resolve
# to windows.registry_event so a registry_set rule is compared against a
# registry_event rule (and vice versa) instead of being false-NOVEL.


@pytest.mark.parametrize("category", ["registry_event", "registry_set", "registry_add", "registry_delete"])
def test_registry_family_categories_resolve_to_one_class(category):
    r = {
        "logsource": {"product": "windows", "category": category},
        "detection": {"s": {"TargetObject|contains": "\\Run"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.registry_event"


def test_registry_set_and_registry_event_are_comparable():
    """The consolidation payoff: a registry_set rule and a registry_event rule
    detecting the same key are the same canonical class (not false-NOVEL)."""
    r_set = {
        "logsource": {"product": "windows", "category": "registry_set"},
        "detection": {"s": {"TargetObject|contains": "\\CurrentVersion\\Run"}, "condition": "s"},
    }
    r_event = {
        "logsource": {"product": "windows", "category": "registry_event"},
        "detection": {"s": {"TargetObject|contains": "\\CurrentVersion\\Run"}, "condition": "s"},
    }
    result = compare_rules(r_set, r_event)
    assert result.canonical_class == "windows.registry_event"
    assert "canonical_class_mismatch" not in result.explanation["reason_flags"]
    assert result.similarity >= 0.8


# --- windows.file_event family (Option C, new class) ---


@pytest.mark.parametrize("category", ["file_event", "file_delete", "file_access", "file_rename", "file_change"])
def test_file_family_categories_resolve_to_one_class(category):
    r = {
        "logsource": {"product": "windows", "category": category},
        "detection": {"s": {"TargetFilename|endswith": "\\evil.exe"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.file_event"


def test_file_delete_and_file_event_are_comparable():
    r_del = {
        "logsource": {"product": "windows", "category": "file_delete"},
        "detection": {"s": {"TargetFilename|endswith": "\\payload.dll"}, "condition": "s"},
    }
    r_evt = {
        "logsource": {"product": "windows", "category": "file_event"},
        "detection": {"s": {"TargetFilename|endswith": "\\payload.dll"}, "condition": "s"},
    }
    result = compare_rules(r_del, r_evt)
    assert result.canonical_class == "windows.file_event"
    assert "canonical_class_mismatch" not in result.explanation["reason_flags"]
    assert result.similarity >= 0.8


def test_file_event_vs_registry_event_mismatch():
    r_file = {
        "logsource": {"product": "windows", "category": "file_event"},
        "detection": {"s": {"TargetFilename|endswith": "\\x.exe"}, "condition": "s"},
    }
    r_reg = {
        "logsource": {"product": "windows", "category": "registry_set"},
        "detection": {"s": {"TargetObject|contains": "\\Run"}, "condition": "s"},
    }
    result = compare_rules(r_file, r_reg)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- windows.image_load (Option B) ---


def test_image_load_category_resolves():
    r = {
        "logsource": {"product": "windows", "category": "image_load"},
        "detection": {"s": {"ImageLoaded|endswith": "\\evil.dll"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.image_load"


def test_sysmon_eid7_resolves_image_load():
    r = {
        "logsource": {"product": "windows", "service": "sysmon"},
        "detection": {"s": {"EventID": 7}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.image_load"


def test_two_image_load_rules_comparable():
    r1 = {
        "logsource": {"product": "windows", "category": "image_load"},
        "detection": {"s": {"ImageLoaded|endswith": "\\amsi.dll"}, "condition": "s"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "image_load"},
        "detection": {"s": {"ImageLoaded|endswith": "\\amsi.dll"}, "condition": "s"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.image_load"
    assert result.similarity >= 0.8


# --- windows.network_connection (Option B) ---


def test_network_connection_category_resolves():
    r = {
        "logsource": {"product": "windows", "category": "network_connection"},
        "detection": {"s": {"DestinationPort": 4444}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.network_connection"


def test_sysmon_eid3_resolves_network_connection():
    r = {
        "logsource": {"product": "windows", "service": "sysmon"},
        "detection": {"s": {"EventID": 3}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.network_connection"


def test_image_load_vs_network_connection_mismatch():
    r_img = {
        "logsource": {"product": "windows", "category": "image_load"},
        "detection": {"s": {"ImageLoaded|endswith": "\\x.dll"}, "condition": "s"},
    }
    r_net = {
        "logsource": {"product": "windows", "category": "network_connection"},
        "detection": {"s": {"DestinationPort": 4444}, "condition": "s"},
    }
    result = compare_rules(r_img, r_net)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- web.webserver (Coverage-Chain, unblocked by Conditional B / keyword parity) ---
# Webserver rules are predominantly keyword-list selections (XSS/SSTI/Log4j/path
# traversal). Spike A (2026-06-01) deferred this class because the precomputed
# extractor produced *empty* atoms for keyword lists; Conditional B (5514381b)
# fixed that, so webserver rules now extract real |contains| atoms and can join
# the deterministic candidate pool without regressing keyword comparison.


def test_webserver_category_resolves():
    r = {
        "logsource": {"category": "webserver"},
        "detection": {"keywords": [".git/"], "condition": "keywords"},
    }
    assert resolve_canonical_class(r) == "web.webserver"


def test_webserver_keyword_rule_not_atom_less():
    """Spike A regression guard: a pure-keyword webserver rule must extract
    non-empty positive atoms via the precomputed pipeline (else it would be
    misrouted as atom-less / false-NOVEL)."""
    from sigma_similarity.ast_builder import build_ast
    from sigma_similarity.atom_extractor import extract_positive_atoms
    from sigma_similarity.detection_normalizer import normalize_detection
    from sigma_similarity.dnf_normalizer import ast_to_dnf

    # "Java Payload Strings" shape (real corpus rule).
    detection = {
        "keywords": ["getRuntime().exec(", "new+java.", "${@java"],
        "condition": "keywords",
    }
    pos = extract_positive_atoms(ast_to_dnf(build_ast(normalize_detection(detection))))
    assert pos, "webserver keyword rule extracted zero atoms (Spike A regression)"
    assert "|contains|contains|getruntime().exec(" in pos


def test_two_webserver_keyword_rules_comparable():
    """Two webserver keyword rules sharing keywords are comparable (high
    similarity), not false-NOVEL — the behavior Spike A blocked."""
    r1 = {
        "logsource": {"category": "webserver"},
        "detection": {"keywords": ["${jndi:ldap:/", "${jndi:rmi:/"], "condition": "keywords"},
    }
    r2 = {
        "logsource": {"category": "webserver"},
        "detection": {"keywords": ["${jndi:ldap:/", "${jndi:rmi:/"], "condition": "keywords"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "web.webserver"
    assert result.similarity >= 0.8


def test_webserver_mixed_field_and_keyword_rule_resolves():
    """The Kemp CVE shape: dict field selection + keyword selection both
    contribute atoms and the rule still resolves to web.webserver."""
    from sigma_similarity.ast_builder import build_ast
    from sigma_similarity.atom_extractor import extract_positive_atoms
    from sigma_similarity.detection_normalizer import normalize_detection
    from sigma_similarity.dnf_normalizer import ast_to_dnf

    detection = {
        "condition": "all of selection_*",
        "selection_path": {"cs-method": "GET", "cs-uri-stem|contains|all": ["/access/set", "param=enableapi"]},
        "selection_keywords": ["Basic Jz", "Basic c7"],
    }
    r = {"logsource": {"category": "webserver"}, "detection": detection}
    assert resolve_canonical_class(r) == "web.webserver"
    pos = extract_positive_atoms(ast_to_dnf(build_ast(normalize_detection(detection))))
    # Both the field atoms and the keyword atoms are present.
    assert any(a.startswith("cs-method|") for a in pos)
    assert "|contains|contains|basic jz" in pos


def test_webserver_vs_process_creation_mismatch():
    r_web = {
        "logsource": {"category": "webserver"},
        "detection": {"keywords": [".git/"], "condition": "keywords"},
    }
    r_proc = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"s": {"Image|endswith": "\\cmd.exe"}, "condition": "s"},
    }
    result = compare_rules(r_web, r_proc)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- Sysmon host-telemetry categories + macOS process_creation (Coverage-Chain) ---
# Clean field-based categories, 1:1 with a Sysmon EID — the same risk profile as
# image_load/network_connection (Option B). No keyword ambiguity: every rule uses
# dict field selections the extractor has always modeled. macOS process_creation
# is the windows/linux sibling (no Sysmon; category-only).


@pytest.mark.parametrize(
    "category,expected_class,field",
    [
        ("process_access", "windows.process_access", "CallTrace|contains"),
        ("pipe_created", "windows.pipe_created", "PipeName"),
        ("create_remote_thread", "windows.create_remote_thread", "TargetImage|endswith"),
        ("driver_load", "windows.driver_load", "ImageLoaded|contains"),
        ("create_stream_hash", "windows.create_stream_hash", "Image|endswith"),
        ("dns_query", "windows.dns_query", "QueryName|contains"),
    ],
)
def test_sysmon_category_resolves(category, expected_class, field):
    r = {
        "logsource": {"product": "windows", "category": category},
        "detection": {"s": {field: "x"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == expected_class


@pytest.mark.parametrize(
    "event_id,expected_class",
    [
        (6, "windows.driver_load"),
        (8, "windows.create_remote_thread"),
        (10, "windows.process_access"),
        (15, "windows.create_stream_hash"),
        (17, "windows.pipe_created"),
        (18, "windows.pipe_created"),
        (22, "windows.dns_query"),
    ],
)
def test_sysmon_event_ids_resolve(event_id, expected_class):
    r = {
        "logsource": {"product": "windows", "service": "sysmon"},
        "detection": {"s": {"EventID": event_id}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == expected_class


def test_two_process_access_rules_comparable():
    r1 = {
        "logsource": {"product": "windows", "category": "process_access"},
        "detection": {"s": {"TargetImage|endswith": "\\lsass.exe"}, "condition": "s"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "process_access"},
        "detection": {"s": {"TargetImage|endswith": "\\lsass.exe"}, "condition": "s"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.process_access"
    assert result.similarity >= 0.8


def test_pipe_created_vs_driver_load_mismatch():
    r_pipe = {
        "logsource": {"product": "windows", "category": "pipe_created"},
        "detection": {"s": {"PipeName": "\\evil"}, "condition": "s"},
    }
    r_drv = {
        "logsource": {"product": "windows", "category": "driver_load"},
        "detection": {"s": {"ImageLoaded|endswith": "\\evil.sys"}, "condition": "s"},
    }
    result = compare_rules(r_pipe, r_drv)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


def test_macos_process_creation_resolves():
    r = {
        "logsource": {"product": "macos", "category": "process_creation"},
        "detection": {"s": {"CommandLine|contains": "osascript"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "macos.process_creation"


def test_macos_and_windows_process_creation_are_distinct_classes():
    """Same category, different product → different telemetry, must not compare."""
    r_mac = {
        "logsource": {"product": "macos", "category": "process_creation"},
        "detection": {"s": {"Image|endswith": "/bash"}, "condition": "s"},
    }
    r_win = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"s": {"Image|endswith": "\\cmd.exe"}, "condition": "s"},
    }
    result = compare_rules(r_mac, r_win)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- web.proxy + network.dns + Windows DNS-Client fold (Coverage-Chain) ---
# proxy is the webserver sibling (web access telemetry, cs-*/c-uri/c-useragent
# fields + keyword lists — de-risked by Conditional B). DNS splits by FIELD schema,
# not just source: generic `category: dns` and zeek `service: dns` both use the
# `query` field → one class (network.dns); Windows Sysmon EID 22 and DNS-Client
# EID 3008 both use `QueryName` → folded into windows.dns_query. The two DNS
# families are kept apart (query vs QueryName) — bridging them is a field-alias
# decision, not a mechanical add.


def test_proxy_category_resolves():
    r = {
        "logsource": {"category": "proxy"},
        "detection": {"selection": {"c-uri|endswith": ".class"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == "web.proxy"


def test_two_proxy_rules_comparable():
    r1 = {
        "logsource": {"category": "proxy"},
        "detection": {"selection": {"c-uri|contains": "/evil"}, "condition": "selection"},
    }
    r2 = {
        "logsource": {"category": "proxy"},
        "detection": {"selection": {"c-uri|contains": "/evil"}, "condition": "selection"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "web.proxy"
    assert result.similarity >= 0.8


def test_proxy_vs_webserver_are_distinct_classes():
    """Proxy and webserver share cs-*/c-uri fields but are distinct telemetry."""
    r_proxy = {
        "logsource": {"category": "proxy"},
        "detection": {"selection": {"c-uri|contains": "/x"}, "condition": "selection"},
    }
    r_web = {
        "logsource": {"category": "webserver"},
        "detection": {"keywords": ["/x"], "condition": "keywords"},
    }
    result = compare_rules(r_proxy, r_web)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


def test_generic_dns_category_resolves():
    r = {
        "logsource": {"category": "dns"},
        "detection": {"selection": {"query": "api.telegram.org"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == "network.dns"


def test_zeek_dns_service_resolves():
    r = {
        "logsource": {"product": "zeek", "service": "dns"},
        "detection": {"selection": {"query|contains": "evil"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == "network.dns"


def test_generic_and_zeek_dns_comparable():
    r_generic = {
        "logsource": {"category": "dns"},
        "detection": {"selection": {"query|contains": "evil.com"}, "condition": "selection"},
    }
    r_zeek = {
        "logsource": {"product": "zeek", "service": "dns"},
        "detection": {"selection": {"query|contains": "evil.com"}, "condition": "selection"},
    }
    result = compare_rules(r_generic, r_zeek)
    assert result.canonical_class == "network.dns"
    assert result.similarity >= 0.8


def test_windows_dns_client_folds_into_dns_query():
    """Windows DNS-Client (EID 3008, QueryName) joins windows.dns_query (Sysmon EID 22)."""
    r = {
        "logsource": {"product": "windows", "service": "dns-client"},
        "detection": {"selection": {"EventID": 3008, "QueryName|contains": "ufile.io"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == "windows.dns_query"


def test_network_dns_and_windows_dns_query_are_distinct_classes():
    """Different field schemas (query vs QueryName) → separate classes, no false merge."""
    r_net = {
        "logsource": {"category": "dns"},
        "detection": {"selection": {"query|contains": "evil"}, "condition": "selection"},
    }
    r_win = {
        "logsource": {"product": "windows", "category": "dns_query"},
        "detection": {"selection": {"QueryName|contains": "evil"}, "condition": "selection"},
    }
    result = compare_rules(r_net, r_win)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- PowerShell telemetry sources (Coverage-Chain) ---
# Three SigmaHQ categories, three logging mechanisms, three distinct fields and
# EIDs: ps_script (Script Block Logging, EID 4104, ScriptBlockText), ps_module
# (Module Logging, EID 4103, Payload), ps_classic_start (classic log, EID 400,
# Data). Kept as SEPARATE classes — unlike the registry_* family (one EID range /
# one field), these are genuinely different telemetry. Whether the same tradecraft
# expressed across these sources should compare is a separate field-alias decision.


@pytest.mark.parametrize(
    "category,expected_class,field",
    [
        ("ps_script", "windows.ps_script", "ScriptBlockText|contains"),
        ("ps_module", "windows.ps_module", "Payload|contains"),
        ("ps_classic_start", "windows.ps_classic_start", "Data|contains"),
    ],
)
def test_powershell_category_resolves(category, expected_class, field):
    r = {
        "logsource": {"product": "windows", "category": category},
        "detection": {"selection": {field: "Invoke-Mimikatz"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == expected_class


def test_two_ps_script_rules_comparable():
    r1 = {
        "logsource": {"product": "windows", "category": "ps_script"},
        "detection": {"selection": {"ScriptBlockText|contains": "IEX"}, "condition": "selection"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "ps_script"},
        "detection": {"selection": {"ScriptBlockText|contains": "IEX"}, "condition": "selection"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.ps_script"
    assert result.similarity >= 0.8


def test_ps_script_vs_ps_module_are_distinct_classes():
    """Different PowerShell telemetry sources are not compared (separate classes)."""
    r_script = {
        "logsource": {"product": "windows", "category": "ps_script"},
        "detection": {"selection": {"ScriptBlockText|contains": "IEX"}, "condition": "selection"},
    }
    r_module = {
        "logsource": {"product": "windows", "category": "ps_module"},
        "detection": {"selection": {"Payload|contains": "IEX"}, "condition": "selection"},
    }
    result = compare_rules(r_script, r_module)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- EventCode recognized as EventID (Splunk / Windows EventLog field alias) ---
# SigmaAgent and Splunk-backend rules use `EventCode` (the Windows EventLog / Splunk
# CIM field name) for what Sysmon/SigmaHQ call `EventID`. The canonical-class resolver
# must treat them identically — otherwise a `service: sysmon` + `EventCode: N` rule
# resolves to no class and gets degraded dedup. Queue id 23 is exactly this shape
# (EventCode: 22 → Sysmon DNS query). Finding A of the extractor-alignment review.


@pytest.mark.parametrize("field", ["EventCode", "eventcode", "event_code", "EventID", "EventId", "event_id"])
def test_event_id_extracted_from_eventcode_and_eventid_aliases(field):
    detection = {"selection": {field: 22, "Image|endswith": "\\vbc.exe"}, "condition": "selection"}
    assert _extract_event_id_from_detection(detection) == 22


def test_eventcode_single_item_list_resolves():
    detection = {"selection": {"EventCode": [7]}, "condition": "selection"}
    assert _extract_event_id_from_detection(detection) == 7


def test_eventcode_multiple_values_no_single_id():
    """Mirror EventID behavior: a multi-value list yields no single event_id."""
    detection = {"selection": {"EventCode": [1, 22]}, "condition": "selection"}
    assert _extract_event_id_from_detection(detection) is None


def test_sysmon_eventcode_22_resolves_dns_query():
    """Queue id 23 shape: service:sysmon + EventCode:22 → windows.dns_query."""
    r = {
        "logsource": {"product": "windows", "service": "sysmon"},
        "detection": {"selection": {"EventCode": 22, "Image|endswith": "\\vbc.exe"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == "windows.dns_query"


def test_sysmon_eventcode_1_resolves_process_creation():
    r = {
        "logsource": {"product": "windows", "service": "sysmon"},
        "detection": {"selection": {"EventCode": 1, "Image|endswith": "\\x.exe"}, "condition": "selection"},
    }
    assert resolve_canonical_class(r) == "windows.process_creation"


# --- windows.service resolution ---


def test_service_creation_category_resolves():
    r = {
        "logsource": {"product": "windows", "category": "service_creation"},
        "detection": {"s": {"ServiceName|contains": "malware"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.service"


@pytest.mark.parametrize("event_id", [7045, 7036])
def test_system_service_event_ids_resolve(event_id):
    r = {
        "logsource": {"product": "windows", "service": "system"},
        "detection": {"s": {"EventID": event_id}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.service"


def test_security_4697_resolves_service():
    r = {
        "logsource": {"product": "windows", "service": "security"},
        "detection": {"s": {"EventID": 4697}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.service"


# --- windows.scheduled_task resolution ---


def test_taskscheduler_service_resolves():
    r = {
        "logsource": {"product": "windows", "service": "taskscheduler"},
        "detection": {"s": {"TaskName|contains": "\\malware"}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.scheduled_task"


@pytest.mark.parametrize("event_id", [4698, 4699, 4700, 4702])
def test_security_scheduled_task_event_ids_resolve(event_id):
    r = {
        "logsource": {"product": "windows", "service": "security"},
        "detection": {"s": {"EventID": event_id}, "condition": "s"},
    }
    assert resolve_canonical_class(r) == "windows.scheduled_task"


# --- cross-class mismatch ---


def test_registry_vs_process_creation_mismatch():
    r_reg = {
        "logsource": {"product": "windows", "category": "registry_event"},
        "detection": {"s": {"TargetObject": "HKLM\\\\Run"}, "condition": "s"},
    }
    r_proc = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"s": {"Image": "reg.exe"}, "condition": "s"},
    }
    result = compare_rules(r_reg, r_proc)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


def test_service_vs_registry_mismatch():
    r_svc = {
        "logsource": {"product": "windows", "category": "service_creation"},
        "detection": {"s": {"ServiceName": "evil_svc"}, "condition": "s"},
    }
    r_reg = {
        "logsource": {"product": "windows", "category": "registry_event"},
        "detection": {"s": {"TargetObject": "HKLM\\\\Run"}, "condition": "s"},
    }
    result = compare_rules(r_svc, r_reg)
    assert result.similarity == 0.0
    assert "canonical_class_mismatch" in result.explanation["reason_flags"]


# --- same-class duplicate detection ---


def test_two_registry_rules_same_class_comparable():
    r1 = {
        "logsource": {"product": "windows", "category": "registry_event"},
        "detection": {"s": {"TargetObject|contains": "\\CurrentVersion\\Run"}, "condition": "s"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "registry_event"},
        "detection": {"s": {"TargetObject|contains": "\\CurrentVersion\\Run"}, "condition": "s"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.registry_event"
    assert result.similarity >= 0.8
    assert "canonical_class_mismatch" not in result.explanation["reason_flags"]


def test_two_service_rules_same_class_comparable():
    r1 = {
        "logsource": {"product": "windows", "category": "service_creation"},
        "detection": {"s": {"ServiceName|contains": "backdoor"}, "condition": "s"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "service_creation"},
        "detection": {"s": {"ServiceName|contains": "backdoor"}, "condition": "s"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.service"
    assert result.similarity >= 0.8


def test_two_scheduled_task_rules_same_class_comparable():
    r1 = {
        "logsource": {"product": "windows", "service": "taskscheduler"},
        "detection": {"s": {"TaskName|contains": "\\Updates\\evil"}, "condition": "s"},
    }
    r2 = {
        "logsource": {"product": "windows", "service": "taskscheduler"},
        "detection": {"s": {"TaskName|contains": "\\Updates\\evil"}, "condition": "s"},
    }
    result = compare_rules(r1, r2)
    assert result.canonical_class == "windows.scheduled_task"
    assert result.similarity >= 0.8
