"""Direct tests for OSDetectionService.detect_os (entity-KB-first; embeddings retired).

detect_os was previously only exercised via mocks (tests/api/test_detect_os_api.py)
and a live probe. These lock the real integration: the entity-KB gate decides,
the embedding classifier/similarity path is gone, and low-signal content returns
Unknown rather than a noisy guess. The registry scan needs no model load (lazy), so these
run fast against the shipped config/keyword_registry.yaml.
"""

import pytest

from src.services.os_detection_service import OSDetectionService

pytestmark = [pytest.mark.unit]


@pytest.fixture
def svc():
    return OSDetectionService()


@pytest.mark.asyncio
async def test_detect_os_linux_via_kb(svc):
    res = await svc.detect_os("Persistence via /etc/cron.d and systemctl; staged payload in /dev/shm.")
    assert res["operating_system"] == "Linux"
    assert res["method"] == "kb_scoring"
    assert res["platforms_detected"] == ["Linux"]


@pytest.mark.asyncio
async def test_detect_os_windows_via_kb(svc):
    res = await svc.detect_os("powershell.exe dumped lsass and wrote an HKLM Run key.")
    assert res["operating_system"] == "Windows"
    assert res["method"] == "kb_scoring"


@pytest.mark.asyncio
async def test_detect_os_macos_via_kb(svc):
    res = await svc.detect_os("Persisted with a LaunchDaemon, used osascript and dscl.")
    assert res["operating_system"] == "MacOS"
    assert res["method"] == "kb_scoring"


@pytest.mark.asyncio
async def test_detect_os_no_signal_is_unknown(svc):
    res = await svc.detect_os("The threat actor moved laterally and exfiltrated sensitive data.")
    assert res["operating_system"] == "Unknown"
    assert res["confidence"] == "low"


@pytest.mark.asyncio
async def test_detect_os_uses_precomputed_verdict(svc):
    """Phase 3: a verdict computed at ingest time (article_metadata['os_classification']) is
    consumed as-is — no re-scan. Proven by giving Windows-reading content but a macOS precomputed
    verdict: the precomputed verdict wins (content is not re-classified)."""
    precomputed = {
        "operating_system": "MacOS",
        "method": "kb_scoring",
        "confidence": "high",
        "similarities": {"Windows": 0.0, "Linux": 0.0, "MacOS": 1.0},
        "max_similarity": 1.0,
        "platforms_detected": ["MacOS"],
        "evidence": {"macos": ["osascript", "dscl"]},
    }
    res = await svc.detect_os(
        "powershell.exe dumped lsass and wrote an HKLM Run key", precomputed=precomputed
    )
    assert res["operating_system"] == "MacOS"
    assert res == precomputed  # non-low verdict returned verbatim, content ignored


@pytest.mark.asyncio
async def test_detect_os_precomputed_low_still_runs_windows_safety_net(svc):
    """A precomputed 'low' verdict still flows through the deterministic Windows-keyword safety
    net, exactly like the fresh-scan path (parity)."""
    low = {
        "operating_system": "Unknown",
        "method": "kb_scoring",
        "confidence": "low",
        "similarities": {},
        "platforms_detected": [],
        "evidence": {},
    }
    content = "rundll32.exe spawned powershell.exe which touched HKLM and lsass.exe via cmd.exe"
    res = await svc.detect_os(content, precomputed=low)
    assert res["operating_system"] == "Windows"
    assert res["method"] == "keyword_match"


@pytest.mark.asyncio
async def test_detect_os_precomputed_none_falls_back_to_scan(svc):
    """No precomputed verdict -> legacy fresh-scan behavior is unchanged (go-forward safety)."""
    res = await svc.detect_os("Persisted with a LaunchDaemon, used osascript and dscl.", precomputed=None)
    assert res["operating_system"] == "MacOS"
    assert res["method"] == "kb_scoring"


@pytest.mark.asyncio
async def test_detect_os_never_uses_embedding_methods(svc):
    """Regression: the embedding classifier/similarity path is retired — detect_os must
    only ever report deterministic methods, never 'similarity' or 'classifier'."""
    for content in (
        "systemctl enable evil.service; chmod +x /tmp/x",
        "powershell -enc ...; lsass dump",
        "a vague article with no host artifacts at all",
    ):
        res = await svc.detect_os(content)
        assert res["method"] in {"kb_scoring", "keyword_match"}, res["method"]
