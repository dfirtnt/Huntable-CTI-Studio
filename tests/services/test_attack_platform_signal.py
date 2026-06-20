"""Unit tests for the ATT&CK technique -> platform signal (Phase C).

Extracts ATT&CK (sub-)technique IDs from article text and turns the
platform-discriminative ones into weighted platform votes. See
docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (Phase C).
"""

import pytest

from src.services.attack_platform_signal import (
    extract_technique_ids,
    load_attack_map,
    technique_platform_votes,
)

pytestmark = [pytest.mark.unit]

_MAP = {
    "T1059.001": ["windows"],
    "T1543.002": ["linux"],
    "T1543.001": ["macos"],
    "T1059.004": ["linux", "macos"],
}


def test_extract_finds_techniques_and_subtechniques():
    ids = extract_technique_ids("Used T1059.001 then T1003 and T1543.002 for persistence.")
    assert ids == {"T1059.001", "T1003", "T1543.002"}


def test_extract_dedupes_and_ignores_non_matches():
    ids = extract_technique_ids("T1059.001 again T1059.001; not T123 nor T12345 nor TXXXX")
    assert ids == {"T1059.001"}


def test_extract_empty_on_no_techniques():
    assert extract_technique_ids("no technique ids here") == set()


def test_votes_single_platform_supplements():
    scores, evidence = technique_platform_votes("attacker used T1059.001 (PowerShell)", _MAP)
    assert scores["windows"] == 2.0  # supplement weight, below the classifier evidence floor
    assert scores["linux"] == 0.0
    assert any("T1059.001" in e for e in evidence["windows"])


def test_votes_two_platform_is_weaker_each():
    scores, _ = technique_platform_votes("ran T1059.004 unix shell", _MAP)
    assert scores["linux"] == 1.0
    assert scores["macos"] == 1.0
    assert scores["windows"] == 0.0


def test_votes_accumulate_across_techniques():
    scores, _ = technique_platform_votes("T1543.002 and T1059.004", _MAP)
    assert scores["linux"] == 2.0 + 1.0  # systemd (single) + unix shell (multi)
    assert scores["macos"] == 1.0


def test_votes_ignore_unmapped_techniques():
    scores, evidence = technique_platform_votes("T9999.999 is not mapped", _MAP)
    assert scores == {"windows": 0.0, "linux": 0.0, "macos": 0.0}
    assert all(not v for v in evidence.values())


def test_load_attack_map_reads_seed_file():
    mapping = load_attack_map()
    assert isinstance(mapping, dict)
    # A couple of high-confidence seed entries must be present and correct.
    assert mapping.get("T1059.001") == ["windows"]
    assert mapping.get("T1543.002") == ["linux"]
    assert mapping.get("T1543.001") == ["macos"]
