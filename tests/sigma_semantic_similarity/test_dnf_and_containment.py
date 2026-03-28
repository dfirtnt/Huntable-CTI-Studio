"""DNF expansion limit returns result; containment thresholds."""


from sigma_similarity.containment_estimator import compute_containment
from sigma_similarity.similarity_engine import compare_rules


def test_containment_equivalent():
    B, oa, ob = compute_containment(9, 10, 10, 5.0, 5.0)
    assert B == 1.0
    assert oa == 0.9
    assert ob == 0.9


def test_containment_subset():
    B, oa, ob = compute_containment(9, 10, 20, 2.0, 5.0)
    assert B == 0.85
    assert oa >= 0.9


def test_containment_superset():
    B, oa, ob = compute_containment(9, 20, 10, 5.0, 2.0)
    assert B == 0.75
    assert ob >= 0.9


def test_containment_else():
    B, _, _ = compute_containment(5, 10, 10, 3.0, 3.0)
    assert B == 0.65


def test_dnf_expansion_limit_returns_result_not_crash():
    # Build two rules that when combined would explode branches (many ORs).
    # Actually triggering 65+ branches is tricky with simple rules. We can test
    # that when DeterministicExpansionLimitError is raised inside engine it's
    # caught and we get a result. So we'd need to mock or build a rule that
    # has 65+ branches. E.g. condition = "s1 or s2 or s3 or ... s65" with 65
    # selections. That would give 65 branches. So create detection with 65
    # selection blocks and condition "s1 or s2 or ... or s65".
    parts = [f"selection{i}" for i in range(65)]
    condition = " or ".join(parts)
    detection = {"condition": condition}
    for i in range(65):
        detection[f"selection{i}"] = {"Image": f"x{i}.exe"}
    r = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": detection,
    }
    r2 = {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"Image": "y.exe"}, "condition": "selection"},
    }
    result = compare_rules(r, r2)
    assert "dnf_expansion_limit" in result.explanation["reason_flags"]
    assert result.similarity == 0.0
