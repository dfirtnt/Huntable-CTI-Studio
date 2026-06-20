"""Unit tests for the entity-driven platform classifier (Phase A: Windows/Linux/macOS).

See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md.
The classifier is deterministic keyword/entity KB scoring with margin-based
confidence (no LLM, no embedding model). Tests use an inline KB so thresholds are
predictable, plus one integration test against the shipped KB file.
"""

import pytest

from src.services.platform_classifier import PlatformClassifier, classify_platforms

pytestmark = [pytest.mark.unit]


# Inline KB with controlled weights so confidence thresholds are predictable.
_KB = [
    {"match": "powershell", "platforms": ["windows"], "weight": 2},
    {"match": "lsass", "platforms": ["windows"], "weight": 3},
    {"match": "hklm", "platforms": ["windows"], "weight": 3},
    {"match": "systemctl", "platforms": ["linux"], "weight": 2},
    {"match": "/etc/cron", "platforms": ["linux"], "weight": 3},
    {"match": "launchdaemon", "platforms": ["macos"], "weight": 3},
    {"match": "osascript", "platforms": ["macos"], "weight": 2},
    {"match": "/tmp/", "platforms": ["linux"], "weight": 1},
]


def _clf():
    return PlatformClassifier(entries=_KB)


def test_windows_entities_classify_windows():
    r = _clf().classify("Actor ran powershell, dumped lsass, set HKLM Run key.")
    assert r.platforms == ["windows"]
    assert r.primary == "windows"
    assert r.confidence == "high"
    assert "powershell" in r.evidence["windows"]


def test_linux_entities_classify_linux():
    r = _clf().classify("Used systemctl enable, dropped /etc/cron.d/x, staged in /tmp/p")
    assert r.platforms == ["linux"]
    assert r.confidence == "high"


def test_macos_entities_classify_macos():
    r = _clf().classify("Persisted via a LaunchDaemon plist and ran osascript.")
    assert r.platforms == ["macos"]
    assert r.confidence == "high"


def test_mixed_windows_linux_is_multi_label_and_not_high():
    r = _clf().classify("powershell dumped lsass; also systemctl + /etc/cron.d persistence")
    assert set(r.platforms) == {"windows", "linux"}
    assert r.confidence != "high"  # contested -> not high


def test_dominant_platform_excludes_weak_secondary():
    # Strong Windows + a single weak Linux hint -> Windows only, high.
    r = _clf().classify("powershell, lsass, HKLM run key; payload staged in /tmp/")
    assert r.platforms == ["windows"]
    assert r.confidence == "high"


def test_generic_or_sparse_content_is_unknown_low():
    r = _clf().classify("The threat actor used common tooling and moved laterally.")
    assert r.platforms == []
    assert r.primary == "unknown"
    assert r.confidence == "low"


def test_weak_single_hint_does_not_claim_platform():
    # A lone weak signal (below the evidence floor) must not assert a platform (§5).
    r = _clf().classify("Files were staged in /tmp/ before exfiltration.")
    assert r.platforms == []
    assert r.confidence == "low"


def test_as_os_result_shape_single_platform():
    res = _clf().classify("powershell, lsass, HKLM").as_os_result()
    assert res["operating_system"] == "Windows"
    assert res["method"] == "kb_scoring"
    assert res["platforms_detected"] == ["Windows"]
    assert res["confidence"] == "high"
    assert isinstance(res["similarities"], dict)


def test_as_os_result_shape_multi_platform():
    res = _clf().classify("powershell lsass; systemctl /etc/cron.d").as_os_result()
    assert res["operating_system"] == "multiple"
    assert set(res["platforms_detected"]) == {"Windows", "Linux"}


def test_as_os_result_unknown_when_no_signal():
    res = _clf().classify("no platform signal here").as_os_result()
    assert res["operating_system"] == "Unknown"
    assert res["platforms_detected"] == []


def test_default_kb_file_classifies_obvious_linux():
    # Integration against the shipped KB: an unambiguous Linux article -> linux.
    content = (
        "The malware wrote /etc/systemd/system/evil.service, ran systemctl daemon-reload, "
        "then chmod +x /tmp/payload and added an /etc/cron.d entry for persistence."
    )
    r = classify_platforms(content)
    assert "linux" in r.platforms
    assert r.primary == "linux"


def test_default_kb_file_classifies_obvious_windows():
    content = (
        "powershell.exe -enc ... dumped lsass.exe, created HKLM\\Software\\Microsoft\\Windows\\"
        "CurrentVersion\\Run key and used rundll32.exe."
    )
    r = classify_platforms(content)
    assert "windows" in r.platforms
    assert r.primary == "windows"


# --- Phase C: ATT&CK technique signal integration (supplements the KB, never dominates) ---

_ATTACK = {"T1543.002": ["linux"], "T1547.006": ["linux"], "T1543.001": ["macos"], "T1059.001": ["windows"]}


def test_attack_reinforces_weak_kb_across_the_floor():
    # A weak KB hint (/tmp/, weight 1, below floor) + corroborating Linux technique
    # citations push it over the floor -> classified Linux.
    clf = PlatformClassifier(
        entries=[{"match": "/tmp/", "platforms": ["linux"], "weight": 1}],
        attack_map=_ATTACK,
    )
    r = clf.classify("payload staged in /tmp/ then persisted via T1543.002 and T1547.006")
    assert r.platforms == ["linux"]
    assert any("T1543.002" in e for e in r.evidence["linux"])


def test_attack_reinforces_only_kb_evidenced_platforms():
    # KB says Windows; a cited Linux technique is IGNORED (no KB Linux evidence to reinforce).
    clf = PlatformClassifier(
        entries=[{"match": "powershell", "platforms": ["windows"], "weight": 3}],
        attack_map=_ATTACK,
    )
    r = clf.classify("powershell loader; appendix lists T1543.002 (systemd service)")
    assert r.platforms == ["windows"]
    assert r.evidence["linux"] == []  # ATT&CK linux vote not applied without KB Linux signal


def test_attack_alone_does_not_originate_defers_to_llm():
    # Only technique citations, no host artifacts -> KB stays blank -> Unknown.
    # The LLM adjudicator narrows this tail precisely (ATT&CK must not force a verdict).
    clf = PlatformClassifier(entries=[], attack_map=_ATTACK)
    r = clf.classify("uses T1543.002 and T1547.006 but cites no host artifacts in text")
    assert r.platforms == []
    assert r.primary == "unknown"


def test_attack_empty_map_is_kb_only():
    clf = PlatformClassifier(entries=[], attack_map={})
    r = clf.classify("Cited T1543.002 but ATT&CK signal disabled.")
    assert r.platforms == []
    assert r.primary == "unknown"
