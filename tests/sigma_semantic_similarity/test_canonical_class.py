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
