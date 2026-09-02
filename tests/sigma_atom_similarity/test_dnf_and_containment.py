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


def _dnf_of(detection: dict) -> list[list[tuple]]:
    """Normalize -> AST -> DNF, flattened to comparable literal tuples."""
    from sigma_similarity.ast_builder import build_ast
    from sigma_similarity.detection_normalizer import normalize_detection
    from sigma_similarity.dnf_normalizer import ast_to_dnf

    branches = ast_to_dnf(build_ast(normalize_detection(detection)))
    return [[(neg, a.field, a.operator, a.modifier_chain, a.value) for neg, a in branch] for branch in branches]


def test_double_negation_equals_plain_selection():
    """'not (not selection)' is boolean-equivalent to 'selection'."""
    doubled = _dnf_of({"selection": {"Image": "cmd.exe"}, "condition": "not (not selection)"})
    plain = _dnf_of({"selection": {"Image": "cmd.exe"}, "condition": "selection"})
    assert doubled == plain
    assert doubled == [[(False, "Image", "eq", "", "cmd.exe")]]


def test_double_negation_under_and_keeps_both_atoms_positive():
    """'selection and not (not filter1)' must not collapse the whole AND to an empty DNF."""
    doubled = _dnf_of(
        {
            "selection": {"Image": "cmd.exe"},
            "filter1": {"User": "SYSTEM"},
            "condition": "selection and not (not filter1)",
        }
    )
    plain = _dnf_of(
        {
            "selection": {"Image": "cmd.exe"},
            "filter1": {"User": "SYSTEM"},
            "condition": "selection and filter1",
        }
    )
    assert doubled == plain
    assert len(doubled) == 1
    assert all(neg is False for neg, *_ in doubled[0])


def test_triple_negation_equals_single_negation():
    """'not (not (not filter1))' is boolean-equivalent to 'not filter1'."""
    tripled = _dnf_of(
        {
            "selection": {"Image": "cmd.exe"},
            "filter1": {"User": "SYSTEM"},
            "condition": "selection and not (not (not filter1))",
        }
    )
    single = _dnf_of(
        {
            "selection": {"Image": "cmd.exe"},
            "filter1": {"User": "SYSTEM"},
            "condition": "selection and not filter1",
        }
    )
    assert tripled == single
    assert (True, "User", "eq", "", "SYSTEM") in tripled[0]


def test_double_negation_over_or_group_equals_plain_group():
    """Double negation over a multi-branch OR collapses to the OR itself."""
    doubled = _dnf_of(
        {
            "sel_a": {"Image": "a.exe"},
            "sel_b": {"Image": "b.exe"},
            "condition": "not (not (sel_a or sel_b))",
        }
    )
    plain = _dnf_of({"sel_a": {"Image": "a.exe"}, "sel_b": {"Image": "b.exe"}, "condition": "sel_a or sel_b"})
    assert doubled == plain
    assert len(doubled) == 2


def test_compare_rules_with_double_negation_matches_equivalent_rule():
    """End-to-end: a double-negated rule scores like its collapsed equivalent, not UnsupportedSigmaFeatureError."""
    logsource = {"product": "windows", "category": "process_creation"}
    doubled = {
        "logsource": logsource,
        "detection": {
            "selection": {"Image": "cmd.exe"},
            "filter1": {"User": "SYSTEM"},
            "condition": "selection and not (not filter1)",
        },
    }
    plain = {
        "logsource": logsource,
        "detection": {
            "selection": {"Image": "cmd.exe"},
            "filter1": {"User": "SYSTEM"},
            "condition": "selection and filter1",
        },
    }
    result = compare_rules(doubled, plain)
    assert result.similarity == 1.0
    assert result.surface_score_a == 1.0
    assert result.explanation["reason_flags"] == []
