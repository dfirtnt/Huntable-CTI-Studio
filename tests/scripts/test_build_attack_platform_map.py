"""Tests for scripts/build_attack_platform_map.py — pure helpers.

The network fetch is out of scope; these lock the two pure transforms:
    _collection_version  -- the version stamp written to ``_source`` (the thing that
                            was reading 'unknown' off the deprecated mitre/cti bundle)
    build_map            -- the platform-discriminative filtering doctrine

Regression intent: the version stamp must come out as the embedded ATT&CK collection
version (e.g. '19.1'), and must degrade to 'unknown' rather than 'None' when the
collection object or its version field is absent.
"""

import pytest

from scripts.build_attack_platform_map import _collection_version, build_map

pytestmark = [pytest.mark.unit]


def _collection(version):
    obj = {"type": "x-mitre-collection", "name": "Enterprise ATT&CK"}
    if version is not None:
        obj["x_mitre_version"] = version
    return obj


def test_collection_version_extracted():
    bundle = {"objects": [_collection("19.1"), {"type": "attack-pattern"}]}
    assert _collection_version(bundle) == "19.1"


def test_collection_version_missing_object_is_unknown():
    bundle = {"objects": [{"type": "attack-pattern"}]}
    assert _collection_version(bundle) == "unknown"


def test_collection_version_missing_field_is_unknown_not_none():
    """A collection object with no x_mitre_version must not stamp the literal 'None'."""
    bundle = {"objects": [_collection(None)]}
    assert _collection_version(bundle) == "unknown"


def test_collection_version_coerced_to_str():
    bundle = {"objects": [_collection(19)]}
    result = _collection_version(bundle)
    assert result == "19"
    assert isinstance(result, str)


def _attack_pattern(tid, platforms, *, revoked=False, deprecated=False):
    return {
        "type": "attack-pattern",
        "revoked": revoked,
        "x_mitre_deprecated": deprecated,
        "x_mitre_platforms": platforms,
        "external_references": [{"source_name": "mitre-attack", "external_id": tid}],
    }


def test_build_map_keeps_only_discriminative():
    bundle = {
        "objects": [
            _attack_pattern("T1000", ["Windows"]),  # single -> kept
            _attack_pattern("T1001", ["Linux", "macOS"]),  # two -> kept
            _attack_pattern("T1002", ["Windows", "Linux", "macOS"]),  # all three -> dropped
            _attack_pattern("T1003", ["Network", "Containers"]),  # out of scope -> dropped
            _attack_pattern("T1004", ["Windows"], revoked=True),  # revoked -> dropped
            _attack_pattern("T1005", ["Linux"], deprecated=True),  # deprecated -> dropped
        ]
    }
    result = build_map(bundle)
    assert result == {"T1000": ["windows"], "T1001": ["linux", "macos"]}


def test_build_map_platforms_in_scope_order():
    """Platforms are ordered windows -> linux -> macos regardless of source order."""
    bundle = {"objects": [_attack_pattern("T1000", ["macOS", "Windows"])]}
    assert build_map(bundle)["T1000"] == ["windows", "macos"]
