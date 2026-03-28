"""AST snapshot tests: stable string representation for given rules."""


from sigma_similarity.ast_builder import ast_to_snapshot_string, build_ast
from sigma_similarity.detection_normalizer import normalize_detection


def test_ast_snapshot_single_selection(rule_windows_process_creation):
    norm = normalize_detection(rule_windows_process_creation["detection"])
    ast = build_ast(norm)
    snap = ast_to_snapshot_string(ast)
    assert "ATOM(" in snap
    assert "cmd.exe" in snap or "image" in snap.lower()


def test_ast_snapshot_and_condition(rule_with_and):
    norm = normalize_detection(rule_with_and["detection"])
    ast = build_ast(norm)
    snap = ast_to_snapshot_string(ast)
    assert "AND(" in snap
    assert "ATOM(" in snap


def test_ast_snapshot_deterministic(rule_with_and):
    norm = normalize_detection(rule_with_and["detection"])
    ast1 = build_ast(norm)
    ast2 = build_ast(norm)
    assert ast_to_snapshot_string(ast1) == ast_to_snapshot_string(ast2)


def test_ast_snapshot_or_condition(rule_with_or):
    norm = normalize_detection(rule_with_or["detection"])
    ast = build_ast(norm)
    snap = ast_to_snapshot_string(ast)
    assert "OR(" in snap


def test_ast_list_without_all_modifier_produces_or():
    """List values without |all modifier -> OR of atoms (Sigma default)."""
    detection = {
        "selection": {"CommandLine|contains": ["net user", "net group"]},
        "condition": "selection",
    }
    norm = normalize_detection(detection)
    ast = build_ast(norm)
    snap = ast_to_snapshot_string(ast)
    assert "OR(" in snap
    assert "net user" in snap
    assert "net group" in snap


def test_ast_list_with_all_modifier_produces_and():
    """List values with |all modifier -> AND of atoms."""
    detection = {
        "selection": {"CommandLine|contains|all": ["net user", "net group"]},
        "condition": "selection",
    }
    norm = normalize_detection(detection)
    ast = build_ast(norm)
    snap = ast_to_snapshot_string(ast)
    assert "AND(" in snap
    assert "net user" in snap
    assert "net group" in snap
