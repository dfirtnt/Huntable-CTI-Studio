"""Canonical class: same class comparable; different class similarity 0; unknown class raises."""

import pytest
from sigma_similarity.canonical_logsource import resolve_canonical_class
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
