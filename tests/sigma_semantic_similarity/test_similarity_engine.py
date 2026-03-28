"""Similarity engine: full result shape, no_shared_atoms, determinism."""

import json

from sigma_similarity.similarity_engine import compare_rules


def test_full_result_shape(rule_windows_process_creation, rule_windows_process_creation_two):
    r1 = rule_windows_process_creation
    r2 = rule_windows_process_creation_two
    result = compare_rules(r1, r2)
    assert hasattr(result, "similarity")
    assert hasattr(result, "jaccard")
    assert hasattr(result, "containment_factor")
    assert hasattr(result, "filter_penalty")
    assert hasattr(result, "surface_score_a")
    assert hasattr(result, "surface_score_b")
    assert hasattr(result, "canonical_class")
    assert "reason_flags" in result.explanation
    assert "overlap_ratio_a" in result.explanation
    assert "overlap_ratio_b" in result.explanation
    assert 0 <= result.similarity <= 1
    assert result.surface_score_a >= 1
    assert result.surface_score_b >= 1


def test_no_shared_atoms_returns_full_result_with_reason():
    r1 = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"Image": "a.exe"}, "condition": "selection"},
    }
    r2 = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"Image": "b.exe"}, "condition": "selection"},
    }
    result = compare_rules(r1, r2)
    assert result.similarity == 0.0
    assert "no_shared_atoms" in result.explanation["reason_flags"]
    assert result.surface_score_a >= 1
    assert result.surface_score_b >= 1


def test_determinism_identical_json(rule_windows_process_creation, rule_with_and):
    r1 = rule_windows_process_creation
    r2 = rule_with_and
    a = compare_rules(r1, r2)
    b = compare_rules(r1, r2)
    out_a = json.dumps(a.to_dict(), sort_keys=True, separators=(",", ":"))
    out_b = json.dumps(b.to_dict(), sort_keys=True, separators=(",", ":"))
    assert out_a == out_b
