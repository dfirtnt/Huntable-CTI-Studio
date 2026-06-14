"""Data integrity tests for config/eval_articles_data/sigma/ground_truth.json.

This is the hand-authored (and later vetted-run-bootstrapped) ground truth for
the end-to-end Sigma rule eval. Unlike the extractor ground truth (flat item
lists), each expected rule is a Sigma fragment with logsource + detection, so
the validation here also confirms every expected rule actually *decomposes*
through the scorer's extractor -- an undecomposable expected rule silently
zeroes out its atoms and corrupts the score.

No server or DB needed -- all assertions are against files on disk (the
decomposition check is skipped when sigma_similarity is unavailable).
"""

import json
import pathlib

import pytest

from src.services.sigma_atom_precompute import extract_atom_fields, is_sigma_similarity_available

ROOT = pathlib.Path(__file__).parent.parent.parent / "config" / "eval_articles_data" / "sigma"
GT_PATH = ROOT / "ground_truth.json"


def _load_ground_truth() -> list[dict]:
    assert GT_PATH.exists(), f"sigma ground_truth.json missing: {GT_PATH}"
    with open(GT_PATH) as f:
        return json.load(f)


@pytest.mark.unit
def test_ground_truth_is_valid_json_list():
    data = _load_ground_truth()
    assert isinstance(data, list), "top-level must be a list"
    assert len(data) > 0, "sigma ground_truth.json is empty"


@pytest.mark.unit
def test_entry_schema():
    """Every entry needs url (http str), expected_rule_count (int), expected_rules (list)."""
    data = _load_ground_truth()
    for i, entry in enumerate(data):
        assert isinstance(entry, dict), f"[{i}]: entry must be a dict"
        assert isinstance(entry.get("url"), str) and entry["url"].startswith("http"), (
            f"[{i}]: 'url' must be an http string"
        )
        assert isinstance(entry.get("expected_rule_count"), int), f"[{i}]: 'expected_rule_count' must be an int"
        assert isinstance(entry.get("expected_rules"), list), f"[{i}]: 'expected_rules' must be a list"


@pytest.mark.unit
def test_expected_rule_count_matches_rules():
    data = _load_ground_truth()
    for i, entry in enumerate(data):
        declared = entry["expected_rule_count"]
        actual = len(entry["expected_rules"])
        assert declared == actual, f"[{i}] {entry['url']}: expected_rule_count={declared} but {actual} rules listed"


@pytest.mark.unit
def test_expected_rules_have_logsource_and_detection():
    data = _load_ground_truth()
    for i, entry in enumerate(data):
        for j, rule in enumerate(entry["expected_rules"]):
            assert isinstance(rule, dict), f"[{i}].expected_rules[{j}]: rule must be a dict"
            assert isinstance(rule.get("logsource"), dict), f"[{i}].expected_rules[{j}]: missing 'logsource' dict"
            assert isinstance(rule.get("detection"), dict), f"[{i}].expected_rules[{j}]: missing 'detection' dict"
            assert "condition" in rule["detection"], f"[{i}].expected_rules[{j}]: detection missing 'condition'"


@pytest.mark.unit
def test_no_duplicate_urls():
    data = _load_ground_truth()
    urls = [e["url"] for e in data]
    seen: set[str] = set()
    dupes = [u for u in urls if u in seen or seen.add(u)]
    assert not dupes, f"duplicate URLs in sigma ground_truth.json: {dupes}"


@pytest.mark.unit
def test_ascii_only():
    """Detection fields/values must be ASCII (repo convention)."""
    raw = GT_PATH.read_text()
    try:
        raw.encode("ascii")
    except UnicodeEncodeError as e:
        pytest.fail(f"non-ASCII characters in sigma ground_truth.json: {e}")


@pytest.mark.unit
def test_every_expected_rule_decomposes():
    """Each expected rule must decompose into at least one positive atom.

    A rule that yields no atoms (typo'd field, unsupported feature) would
    silently contribute nothing to recall, making the ground truth a lie.
    """
    if not is_sigma_similarity_available():
        pytest.skip("sigma_similarity not installed; cannot verify decomposition")
    data = _load_ground_truth()
    failures = []
    for entry in data:
        for j, rule in enumerate(entry["expected_rules"]):
            fields = extract_atom_fields(rule, require_canonical_class=False)
            if fields is None or not fields.get("positive_atoms"):
                failures.append(f"{entry['url']} rule[{j}]")
    assert not failures, f"expected rules that did not decompose into atoms: {failures}"
