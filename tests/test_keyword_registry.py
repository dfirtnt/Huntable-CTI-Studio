"""Phase 1 parity gate for the faceted keyword registry (spec 2026-06-20 §7/§8/§10, decision D-A).

The registry (`config/keyword_registry.yaml`) is the single source of truth; HUNT_SCORING_KEYWORDS
is derived from it. These lock:
- **P1** — the derived dict is byte-equal to the pre-migration snapshot (hunt score unchanged).
- **G3** — the registry's platform entries reproduce `platform_classification_kb.yaml`.
- **P3** — `project_platform` agrees with the in-production `classify_platforms`.
- registry hygiene — every entry is well-formed.
"""

import json
from pathlib import Path

import pytest
import yaml

from src.utils.content import HUNT_SCORING_KEYWORDS
from src.utils.keyword_registry import (
    build_hunt_scoring_keywords,
    load_registry,
    platform_entries,
    project_huntability,
    project_platform,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEGACY = json.loads((ROOT / "tests/fixtures/hunt_scoring_keywords_legacy.json").read_text(encoding="utf-8"))
VALID_TIERS = {"perfect", "good", "lolbas", "intelligence", "negative"}
VALID_PLATFORMS = {"windows", "linux", "macos"}


def test_derived_hunt_scoring_keywords_byte_equal_to_legacy():
    """P1: the dict the scorer/junk-filter consume is byte-equal to the pre-migration snapshot."""
    assert HUNT_SCORING_KEYWORDS == LEGACY


def test_build_projection_byte_equal_to_legacy():
    assert build_hunt_scoring_keywords() == LEGACY


def test_registry_entries_well_formed():
    reg = load_registry()
    assert reg, "registry empty"
    for e in reg:
        assert e.get("match"), e
        assert "tier" in e or "platforms" in e, f"entry has neither facet: {e}"
        if "tier" in e:
            assert e["tier"] in VALID_TIERS, e
        if "platforms" in e:
            assert e["platforms"] and all(p in VALID_PLATFORMS for p in e["platforms"]), e


def test_platform_entries_subsume_platform_kb():
    """G3: the registry's platform entries reproduce config/platform_classification_kb.yaml."""
    kb = yaml.safe_load((ROOT / "config/platform_classification_kb.yaml").read_text(encoding="utf-8"))
    kb_set = {
        (e["match"], tuple(e["platforms"]), e.get("weight", 1))
        for e in kb.get("entities", [])
        if e.get("match") and e.get("platforms")
    }
    reg_set = {(e["match"], tuple(e["platforms"]), e["weight"]) for e in platform_entries()}
    assert kb_set <= reg_set, f"missing from registry: {kb_set - reg_set}"


@pytest.mark.parametrize(
    "content",
    [
        "Persistence via /etc/cron.d and systemctl; staged payload in /dev/shm.",
        "powershell.exe dumped lsass and wrote an HKLM Run key.",
        "Persisted with a LaunchDaemon, used osascript and dscl.",
        "The threat actor moved laterally and exfiltrated sensitive data.",
        "Linux backdoor uses ld.so.preload and a systemd service; Windows variant uses rundll32.",
    ],
)
def test_project_platform_matches_live_classifier(content):
    """P3: project_platform's verdict matches the in-production classify_platforms (parity)."""
    from src.services.platform_classifier import classify_platforms

    got = project_platform(content)
    want = classify_platforms(content)
    assert got.platforms == want.platforms, (content, got.platforms, want.platforms)
    assert got.primary == want.primary
    assert got.confidence == want.confidence


def test_project_huntability_delegates_to_scorer():
    from src.utils.content import ThreatHuntingScorer

    content = "rundll32.exe and powershell.exe; osascript do shell script"
    assert project_huntability("t", content) == ThreatHuntingScorer.score_threat_hunting_content("t", content)


# --- Phase 2: OS classification computed at scoring time, stored in article_metadata ---


def test_build_os_classification_macos():
    from src.utils.keyword_registry import build_os_classification

    r = build_os_classification("Persisted with a LaunchDaemon, used osascript and dscl.")
    assert r["operating_system"] == "MacOS"
    assert r["platforms_detected"] == ["MacOS"]
    assert r["method"] == "kb_scoring"


def test_build_os_classification_unknown_on_no_signal():
    from src.utils.keyword_registry import build_os_classification

    r = build_os_classification("The actor moved laterally and exfiltrated sensitive data.")
    assert r["operating_system"] == "Unknown"
    assert r["platforms_detected"] == []


def test_build_os_classification_trims_evidence():
    from src.utils.keyword_registry import build_os_classification

    content = " ".join(
        ["osascript", "launchctl", "dscl", "kextload", "launchdaemon", "launchagent", "tcc.db"] * 4
    )
    r = build_os_classification(content, max_evidence=3)
    assert all(len(items) <= 3 for items in r["evidence"].values()), r["evidence"]


def test_load_registry_raises_on_malformed():
    """The registry is required: a malformed file raises loudly rather than silently returning an
    empty set (a silent fallback would yield silently-wrong hunt scores). Decision in
    keyword_registry.load_registry docstring."""
    import tempfile
    from pathlib import Path as _Path

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write("some_other_key: true\n")  # valid YAML, but no 'keywords' list
        bad_path = fh.name
    try:
        with pytest.raises(ValueError, match="no 'keywords' list"):
            load_registry(_Path(bad_path))
    finally:
        _Path(bad_path).unlink()


def test_build_os_classification_multiple_platforms():
    """The 'multiple' branch: content with strong macOS AND Linux evidence yields a multi-label
    verdict (operating_system == 'multiple'), the path Phase 3 must round-trip."""
    from src.utils.keyword_registry import build_os_classification

    content = (
        "Persisted with a LaunchDaemon, used osascript, dscl, and tcc.db on macOS; the Linux "
        "variant drops via /etc/cron.d, a systemd service, and stages in /dev/shm."
    )
    r = build_os_classification(content)
    assert r["operating_system"] == "multiple", r
    assert len(r["platforms_detected"]) >= 2, r["platforms_detected"]


def test_build_os_classification_has_detect_os_shape():
    """Contract: the stored record carries the OSDetectionService.detect_os keys so
    os_detection_node can consume it unchanged in Phase 3."""
    from src.utils.keyword_registry import build_os_classification

    r = build_os_classification("Persisted with a LaunchDaemon, used osascript and dscl.")
    assert set(r) >= {
        "operating_system",
        "method",
        "confidence",
        "similarities",
        "max_similarity",
        "platforms_detected",
        "evidence",
    }, set(r)


@pytest.mark.asyncio
async def test_enhance_metadata_stores_os_classification_at_scoring_time():
    """Phase 2: the canonical ingest seam (ContentProcessor._enhance_metadata) stores
    os_classification alongside the hunt score, without disturbing the hunt score."""
    from datetime import datetime

    from src.core.processor import ContentProcessor
    from src.models.article import ArticleCreate

    article = ArticleCreate(
        title="macOS stealer analysis",
        canonical_url="https://example.test/phase2",
        content="Persisted with a LaunchDaemon, used osascript and dscl.",
        source_id=1,
        published_at=datetime(2026, 1, 1),
    )
    enhanced = await ContentProcessor()._enhance_metadata(article)
    assert "threat_hunting_score" in enhanced  # hunt score still produced
    assert enhanced["os_classification"]["operating_system"] == "MacOS"
    assert enhanced["os_classification"]["platforms_detected"] == ["MacOS"]
