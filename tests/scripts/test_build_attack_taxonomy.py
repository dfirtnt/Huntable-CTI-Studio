"""Tests for scripts/build_attack_taxonomy.py -- the pure ``build_taxonomy`` transform.

The network fetch is out of scope. These lock the doctrine the Sigma validator depends on:
    - IDs are taken only from the STIX type that legitimately carries that prefix
      (legacy course-of-action objects with T-prefixed IDs must NOT register as techniques);
    - revoked / deprecated status is preserved and ``replaced_by`` is resolved from
      ``revoked-by`` relationships;
    - the same ID across domains merges, and an active record wins over a revoked one;
    - tactic shortnames are collected from active x-mitre-tactic objects only.
"""

import json

import pytest

from scripts.build_attack_taxonomy import build_taxonomy, render_taxonomy

pytestmark = [pytest.mark.unit]


def _ref(external_id, source_name="mitre-attack"):
    return {"source_name": source_name, "external_id": external_id}


def _obj(stix_type, stix_id, external_id, name, *, revoked=False, deprecated=False, **extra):
    obj = {
        "type": stix_type,
        "id": stix_id,
        "name": name,
        "external_references": [_ref(external_id)],
    }
    if revoked:
        obj["revoked"] = True
    if deprecated:
        obj["x_mitre_deprecated"] = True
    obj.update(extra)
    return obj


def _revoked_by(source_ref, target_ref):
    return {
        "type": "relationship",
        "id": f"relationship--{source_ref}-{target_ref}",
        "relationship_type": "revoked-by",
        "source_ref": source_ref,
        "target_ref": target_ref,
    }


def _collection(version):
    return {"type": "x-mitre-collection", "id": "x-mitre-collection--1", "x_mitre_version": version}


@pytest.fixture
def enterprise_bundle():
    return {
        "objects": [
            _collection("19.2"),
            _obj("attack-pattern", "attack-pattern--a", "T1059", "Command and Scripting Interpreter"),
            _obj(
                "attack-pattern",
                "attack-pattern--b",
                "T1059.001",
                "PowerShell",
                x_mitre_is_subtechnique=True,
            ),
            _obj("attack-pattern", "attack-pattern--c", "T1086", "PowerShell", revoked=True),
            _obj("attack-pattern", "attack-pattern--d", "T1064", "Scripting", deprecated=True),
            _revoked_by("attack-pattern--c", "attack-pattern--b"),
            _obj("intrusion-set", "intrusion-set--e", "G0016", "APT29"),
            _obj("malware", "malware--f", "S0154", "Cobalt Strike"),
            _obj("tool", "tool--g", "S0002", "Mimikatz"),
            _obj("course-of-action", "course-of-action--h", "M1038", "Execution Prevention"),
            # Legacy pre-v5 mitigation that reuses a technique-style ID: must not become a technique.
            _obj("course-of-action", "course-of-action--i", "T1059", "Legacy mitigation", deprecated=True),
            _obj("campaign", "campaign--j", "C0001", "Frankenstein"),
            _obj("x-mitre-tactic", "x-mitre-tactic--k", "TA0002", "Execution", x_mitre_shortname="execution"),
            _obj(
                "x-mitre-tactic",
                "x-mitre-tactic--l",
                "TA0099",
                "Old Tactic",
                deprecated=True,
                x_mitre_shortname="old-tactic",
            ),
            # Not a Sigma-taggable object type.
            _obj("x-mitre-data-source", "x-mitre-data-source--m", "DS0009", "Process"),
        ]
    }


def test_build_taxonomy_registers_ids_by_type(enterprise_bundle):
    payload = build_taxonomy({"enterprise-attack": enterprise_bundle})
    objects = payload["objects"]

    assert payload["_source"] == "mitre_attack_stix:19.2"
    assert payload["_domains"] == {"enterprise-attack": "19.2"}
    assert objects["T1059"] == {
        "name": "Command and Scripting Interpreter",
        "kind": "technique",
        "status": "active",
        "domains": ["enterprise"],
    }
    assert objects["T1059.001"]["kind"] == "sub-technique"
    assert objects["G0016"]["kind"] == "group"
    assert objects["S0154"]["kind"] == "software"
    assert objects["S0002"]["kind"] == "software"
    assert objects["M1038"]["kind"] == "mitigation"
    assert objects["C0001"]["kind"] == "campaign"
    assert objects["TA0002"] == {
        "name": "Execution",
        "kind": "tactic",
        "status": "active",
        "domains": ["enterprise"],
        "shortname": "execution",
    }
    assert "DS0009" not in objects


def test_build_taxonomy_legacy_mitigation_does_not_shadow_technique(enterprise_bundle):
    """A course-of-action with a T-prefixed ID is not a technique and must not touch T1059."""
    objects = build_taxonomy({"enterprise-attack": enterprise_bundle})["objects"]
    assert objects["T1059"]["status"] == "active"
    assert objects["T1059"]["kind"] == "technique"
    assert objects["T1059"]["name"] == "Command and Scripting Interpreter"


def test_build_taxonomy_revoked_and_deprecated(enterprise_bundle):
    objects = build_taxonomy({"enterprise-attack": enterprise_bundle})["objects"]
    assert objects["T1086"]["status"] == "revoked"
    assert objects["T1086"]["replaced_by"] == "T1059.001"
    assert objects["T1064"]["status"] == "deprecated"
    assert "replaced_by" not in objects["T1064"]


def test_build_taxonomy_tactics_active_only(enterprise_bundle):
    payload = build_taxonomy({"enterprise-attack": enterprise_bundle})
    assert payload["tactics"] == ["execution"]
    assert payload["objects"]["TA0099"]["status"] == "deprecated"


def test_build_taxonomy_merges_domains_active_wins():
    revoked_in_ics = {
        "objects": [
            _collection("19.2"),
            _obj("intrusion-set", "intrusion-set--x", "G0074", "Dragonfly 2.0", revoked=True),
            _obj("intrusion-set", "intrusion-set--y", "G0035", "Dragonfly"),
            _revoked_by("intrusion-set--x", "intrusion-set--y"),
        ]
    }
    active_in_mobile = {
        "objects": [
            _collection("19.1"),
            _obj("intrusion-set", "intrusion-set--x2", "G0074", "Dragonfly 2.0 (mobile)"),
            _obj(
                "x-mitre-tactic", "x-mitre-tactic--t", "TA0030", "Defense Evasion", x_mitre_shortname="defense-evasion"
            ),
        ]
    }
    payload = build_taxonomy({"ics-attack": revoked_in_ics, "mobile-attack": active_in_mobile})
    record = payload["objects"]["G0074"]
    assert record["status"] == "active"
    assert record["domains"] == ["ics", "mobile"]
    assert "replaced_by" not in record
    assert payload["objects"]["G0035"]["domains"] == ["ics"]
    assert payload["tactics"] == ["defense-evasion"]
    # Highest known collection version stamps _source; per-domain versions are kept.
    assert payload["_source"] == "mitre_attack_stix:19.2"
    assert payload["_domains"] == {"ics-attack": "19.2", "mobile-attack": "19.1"}


def test_build_taxonomy_unknown_version_degrades():
    payload = build_taxonomy({"enterprise-attack": {"objects": []}})
    assert payload["_source"] == "mitre_attack_stix:unknown"
    assert payload["objects"] == {}
    assert payload["tactics"] == []


def test_render_taxonomy_is_valid_json_one_object_per_line(enterprise_bundle):
    payload = {"_note": "n", **build_taxonomy({"enterprise-attack": enterprise_bundle})}
    text = render_taxonomy(payload)
    assert json.loads(text) == payload
    object_lines = [line for line in text.splitlines() if line.startswith('    "')]
    assert len(object_lines) == len(payload["objects"])
    assert text.endswith("}\n")
