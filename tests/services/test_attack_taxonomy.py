"""Tests for src/services/attack_taxonomy.py -- loader and per-tag check.

Two layers are pinned here:
    - the check itself against a small hand-built taxonomy (errors for unknown / revoked /
      deprecated IDs with actionable text, warnings for unknown tactics, silence for
      non-attack namespaces and for an empty taxonomy);
    - the committed config/attack_taxonomy.json is loadable and contains the IDs the
      rest of the test suite tags rules with.
"""

import json

import pytest

from src.services.attack_taxonomy import (
    DEFAULT_ATTACK_TAXONOMY_PATH,
    EMPTY_TAXONOMY,
    AttackTaxonomy,
    check_attack_tag,
    clear_taxonomy_cache,
    load_attack_taxonomy,
    parse_taxonomy,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture
def taxonomy():
    return AttackTaxonomy(
        version="19.2",
        tactics=frozenset({"execution", "defense-evasion", "command-and-control"}),
        objects={
            "T1059": {"name": "Command and Scripting Interpreter", "kind": "technique", "status": "active"},
            "T1059.001": {"name": "PowerShell", "kind": "sub-technique", "status": "active"},
            "T1086": {"name": "PowerShell", "kind": "technique", "status": "revoked", "replaced_by": "T1059.001"},
            "T1064": {"name": "Scripting", "kind": "technique", "status": "deprecated"},
            "T1999": {"name": "Orphaned", "kind": "technique", "status": "revoked"},
            "G0016": {"name": "APT29", "kind": "group", "status": "active"},
            "S0154": {"name": "Cobalt Strike", "kind": "software", "status": "active"},
            "TA0002": {"name": "Execution", "kind": "tactic", "status": "active", "shortname": "execution"},
        },
    )


@pytest.mark.parametrize(
    "tag",
    [
        "attack.t1059",
        "attack.t1059.001",
        "attack.T1059.001",  # LLMs often upper-case the ID
        "attack.g0016",
        "attack.s0154",
        "attack.ta0002",
        "attack.execution",
        "attack.defense-evasion",
        "attack.defense_evasion",  # legacy underscore form normalizes to the hyphen form
        "attack.command_and_control",
    ],
)
def test_valid_tags_pass(taxonomy, tag):
    assert check_attack_tag(tag, taxonomy) == ([], [])


@pytest.mark.parametrize("tag", ["cve.2021-44228", "car.2019-04-001", "detection.threat-hunting", "tlp.amber"])
def test_other_namespaces_are_ignored(taxonomy, tag):
    assert check_attack_tag(tag, taxonomy) == ([], [])


def test_unknown_technique_is_error(taxonomy):
    errors, warnings = check_attack_tag("attack.t9999", taxonomy)
    assert warnings == []
    assert len(errors) == 1
    assert "unknown ATT&CK technique T9999" in errors[0]
    assert "v19.2" in errors[0]


def test_unknown_subtechnique_names_existing_parent(taxonomy):
    errors, _ = check_attack_tag("attack.t1059.999", taxonomy)
    assert len(errors) == 1
    assert "T1059.999" in errors[0]
    assert "parent technique T1059 (Command and Scripting Interpreter) exists" in errors[0]


def test_unknown_group_and_software_are_errors(taxonomy):
    assert "unknown ATT&CK group G9999" in check_attack_tag("attack.g9999", taxonomy)[0][0]
    assert "unknown ATT&CK software S9999" in check_attack_tag("attack.s9999", taxonomy)[0][0]


def test_revoked_technique_names_replacement(taxonomy):
    errors, warnings = check_attack_tag("attack.t1086", taxonomy)
    assert warnings == []
    assert len(errors) == 1
    assert "revoked ATT&CK technique T1086 (PowerShell)" in errors[0]
    assert "replaced by T1059.001 (PowerShell)" in errors[0]
    assert "use 'attack.t1059.001'" in errors[0]


def test_revoked_without_replacement(taxonomy):
    errors, _ = check_attack_tag("attack.t1999", taxonomy)
    assert len(errors) == 1
    assert "revoked ATT&CK technique T1999 (Orphaned) with no recorded replacement" in errors[0]


def test_deprecated_technique_is_error(taxonomy):
    errors, warnings = check_attack_tag("attack.t1064", taxonomy)
    assert warnings == []
    assert len(errors) == 1
    assert "deprecated ATT&CK technique T1064 (Scripting)" in errors[0]
    assert "remove the tag or choose a current ATT&CK ID" in errors[0]


def test_unknown_tactic_is_warning_not_error(taxonomy):
    errors, warnings = check_attack_tag("attack.persistance", taxonomy)
    assert errors == []
    assert len(warnings) == 1
    assert "not a recognized ATT&CK tactic or ID" in warnings[0]


def test_empty_suffix_is_warning(taxonomy):
    errors, warnings = check_attack_tag("attack.", taxonomy)
    assert errors == []
    assert len(warnings) == 1


def test_empty_taxonomy_disables_check():
    assert check_attack_tag("attack.t9999", EMPTY_TAXONOMY) == ([], [])
    assert check_attack_tag("attack.nonsense", EMPTY_TAXONOMY) == ([], [])


def test_parse_taxonomy_tolerates_junk():
    assert parse_taxonomy(None).is_empty
    assert parse_taxonomy([]).is_empty
    assert parse_taxonomy({"objects": "nope", "tactics": "nope"}).is_empty
    parsed = parse_taxonomy({"_source": "mitre_attack_stix:19.2", "objects": {"t1059": {"status": "active"}, "x": 1}})
    assert parsed.version == "19.2"
    assert parsed.lookup("T1059") == {"status": "active"}
    assert parsed.lookup("t1059") == {"status": "active"}
    assert "X" not in parsed.objects


def test_load_missing_file_returns_empty(tmp_path):
    clear_taxonomy_cache()
    try:
        assert load_attack_taxonomy(tmp_path / "missing.json").is_empty
    finally:
        clear_taxonomy_cache()


def test_load_corrupt_file_returns_empty(tmp_path):
    corrupt = tmp_path / "attack_taxonomy.json"
    corrupt.write_text("{not json", encoding="utf-8")
    clear_taxonomy_cache()
    try:
        assert load_attack_taxonomy(corrupt).is_empty
    finally:
        clear_taxonomy_cache()


def test_load_caches_per_path(tmp_path):
    path = tmp_path / "attack_taxonomy.json"
    path.write_text(json.dumps({"_source": "mitre_attack_stix:1.0", "objects": {"T1059": {"status": "active"}}}))
    clear_taxonomy_cache()
    try:
        first = load_attack_taxonomy(path)
        path.write_text("{}")
        second = load_attack_taxonomy(path)
        assert first is second
        clear_taxonomy_cache()
        assert load_attack_taxonomy(path).is_empty
    finally:
        clear_taxonomy_cache()


def test_committed_taxonomy_is_loadable_and_current():
    """The shipped config/attack_taxonomy.json must cover the IDs used across the test suite."""
    taxonomy = load_attack_taxonomy(DEFAULT_ATTACK_TAXONOMY_PATH)
    assert not taxonomy.is_empty
    assert taxonomy.version not in ("", "unknown")
    for attack_id in ("T1059", "T1059.001", "T1059.003", "T1105", "T1547.001", "T1053.005", "T1003.002", "T1218"):
        entry = taxonomy.lookup(attack_id)
        assert entry is not None, attack_id
        assert entry["status"] == "active", attack_id
    assert taxonomy.lookup("T1086")["status"] == "revoked"
    assert taxonomy.lookup("T1086")["replaced_by"] == "T1059.001"
    assert {"execution", "persistence", "command-and-control", "defense-evasion"} <= taxonomy.tactics
