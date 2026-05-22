"""Contract tests for ContentFilter.extract_features_v3().

v3 is the contract-aligned feature extractor designed alongside the
2026-05-21 calibration session. Each feature approximates "would an
ExtractAgent sub-agent emit an artifact from this chunk?" or maps to a
documented exclusion category from rank-agent.md / extractor-standard.md.

These tests lock the contract so we don't accidentally regress to v2's
problems (no registry-path detection, ip_count as a positive signal,
length leakage, no SIGMA/YARA structural detection).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

# Add src/ so the bare 'utils.content_filter' import works
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture(scope="module")
def cf_v3():
    from src.utils.content_filter import ContentFilter

    return ContentFilter(feature_version="v3")


@pytest.fixture(scope="module")
def cf_v2():
    from src.utils.content_filter import ContentFilter

    return ContentFilter(feature_version="v2")


# ---------- Samples ----------

_CMDLINE_SAMPLE = (
    "The attacker ran sc delete SgrmAgent and bcdedit /set {current} "
    "disableelamdrivers yes to disable Defender, followed by "
    "powershell -w hidden -ep bypass -c IEX(New-Object Net.WebClient)..."
)

_REGISTRY_SAMPLE = (
    "Persistence was established by writing a value under "
    "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\"
    "SpecialAccounts\\Userlist pointing to a hidden admin account."
)

_SIGMA_SAMPLE = (
    "title: Gatekeeper disable\n"
    "logsource:\n  category: process_creation\n  product: macos\n"
    "detection:\n  selection:\n    cmdline:\n      - spctl --master-disable\n"
    "  condition: selection\n"
    "falsepositives:\n  - Unknown\n"
    "level: high"
)

_YARA_SAMPLE = (
    "rule conti_locker {\n"
    '  meta:\n    author = "DFIR"\n'
    '  strings:\n    $s1 = "AppPolicyGetProcessTerminationMethod" fullword ascii\n'
    '    $s2 = "operator co_await" fullword ascii\n'
    "  condition: uint16(0) == 0x5a4d and 1 of them\n"
    "}"
)

_BEACON_CONFIG_SAMPLE = (
    'Cobalt Strike config: { "beacontype": ["HTTPS"], "sleeptime": 50845, '
    '"jitter": 33, "maxgetsize": 2796804, "spawnto": "AAAAAA", '
    '"polling": 30, "maxdns": 255, "watermark": "12345" }'
)

_IOC_LIST_SAMPLE = (
    "Indicators: 38.180.61.247, 195.2.70.38, 91.142.74.28, "
    "evil[.]com, malicious[.]example[.]org, "
    "d41d8cd98f00b204e9800998ecf8427e, "
    "5d41402abc4b2a76b9719d911017c592, "
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)

_MARKETING_SAMPLE = (
    "Our managed security platform empowers your team to streamline threat "
    "detection. Book a demo today to see how our solution can transform "
    "your operations. Read our white paper and sign up for the newsletter."
)

_EDUCATIONAL_SAMPLE = (
    "The spctl utility is used to manage Gatekeeper. Attackers could use "
    "this technique to bypass code-signing checks. Defenders should "
    "monitor for unusual invocations. In this post we will demonstrate "
    "how to detect such activity."
)

_ATTACKER_PATH_SAMPLE = (
    "The Betruger backdoor was dropped to C:\\Users\\Public\\Music\\ccs.exe "
    "and a loader was written to C:\\ProgramData\\Roning\\goldendays.dll."
)


# ---------- Contract: feature count ----------


class TestFeatureCount:
    def test_v3_has_20_features(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert len(feats) == 20, f"v3 contract: 20 features. Got {len(feats)}: {sorted(feats.keys())}"

    def test_v3_feature_order_is_stable(self, cf_v3) -> None:
        """Feature dict ordering is the model's positional contract."""
        a = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        b = cf_v3.extract_features_v3(_REGISTRY_SAMPLE)
        assert list(a.keys()) == list(b.keys()), (
            "Feature key order must be stable across calls -- the RF uses positional indexing."
        )

    def test_v3_returns_only_floats(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        for k, v in feats.items():
            assert isinstance(v, float), f"Feature {k} is {type(v).__name__}, must be float"


# ---------- Contract: dropped problematic features ----------


class TestNoLengthLeakage:
    """v3 must not have any length-derived features."""

    def test_no_sentence_count(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert "sentence_count" not in feats

    def test_no_word_count_feature(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert "word_count" not in feats
        assert "char_count" not in feats

    def test_no_avg_word_length(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert "avg_word_length" not in feats


class TestNoStandaloneIpUrl:
    """v3 must not have ip_count/url_count as standalone positive features.

    These were misleading in v1/v2: atomic IOCs are NEGATIVE signals, not
    neutral 'technical content'. v3 captures them in atomic_ioc_density.
    """

    def test_no_ip_count(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_IOC_LIST_SAMPLE)
        assert "ip_count" not in feats

    def test_no_url_count(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_IOC_LIST_SAMPLE)
        assert "url_count" not in feats


# ---------- Contract: positive signal detection ----------


class TestCmdlineSignal:
    def test_detects_sc_delete(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert feats["cmdline_artifact_count"] >= 1.0

    def test_no_cmdline_in_pure_marketing(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_MARKETING_SAMPLE)
        assert feats["cmdline_artifact_count"] == 0.0


class TestRegistrySignal:
    def test_detects_hive_rooted_path(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_REGISTRY_SAMPLE)
        assert feats["registry_hive_path_count"] >= 1.0

    def test_no_registry_in_marketing(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_MARKETING_SAMPLE)
        assert feats["registry_hive_path_count"] == 0.0

    def test_no_registry_for_shorthand(self, cf_v3) -> None:
        """Per RegistryExtract contract: shorthand without hive root must NOT count."""
        text = "Persistence via the Run key for AppInit_DLLs and IFEO."
        feats = cf_v3.extract_features_v3(text)
        assert feats["registry_hive_path_count"] == 0.0


class TestHuntQuerySignal:
    def test_detects_sigma_rule_body(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_SIGMA_SAMPLE)
        # SIGMA has title:, logsource:, detection:, selection:, condition:, falsepositives:
        assert feats["hunt_query_count"] >= 5.0


class TestAttackerPathSignal:
    def test_detects_users_public(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_ATTACKER_PATH_SAMPLE)
        assert feats["attacker_placed_path_count"] >= 1.0

    def test_detects_programdata_custom(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_ATTACKER_PATH_SAMPLE)
        # Both C:\Users\Public\Music\ccs.exe and C:\ProgramData\Roning\goldendays.dll
        assert feats["attacker_placed_path_count"] >= 2.0


# ---------- Contract: negative content detection ----------


class TestYaraExclusion:
    def test_detects_yara_rule_body(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_YARA_SAMPLE)
        assert feats["yara_rule_indicator"] == 1.0

    def test_no_yara_in_huntable_sample(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert feats["yara_rule_indicator"] == 0.0


class TestBeaconConfigExclusion:
    def test_detects_cobalt_strike_config(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_BEACON_CONFIG_SAMPLE)
        assert feats["beacon_config_indicator"] == 1.0

    def test_no_beacon_indicator_in_cmdline(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert feats["beacon_config_indicator"] == 0.0


class TestAtomicIocDensity:
    def test_high_density_on_ioc_list(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_IOC_LIST_SAMPLE)
        # IOC list with hashes + IPs + defanged domains, very few words
        assert feats["atomic_ioc_density"] > 0.1

    def test_hash_count_on_ioc_list(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_IOC_LIST_SAMPLE)
        assert feats["hash_count"] >= 3.0  # MD5 + MD5 + SHA256


class TestEducationalPhrases:
    def test_detects_educational(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_EDUCATIONAL_SAMPLE)
        assert feats["educational_phrase_count"] >= 3.0

    def test_no_educational_in_cmdline(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        # The cmdline sample has none of "could be used"/"is used to"/etc.
        assert feats["educational_phrase_count"] == 0.0


# ---------- Contract: refined perfect_pattern_count ----------


class TestRefinedPerfectPatterns:
    """Noisy 2-char discriminators (MZ, C:\\, D:\\) must NOT inflate
    perfect_pattern_count -- they fired on base64 blobs and CS configs
    in v1/v2."""

    def test_mz_alone_does_not_count(self, cf_v3) -> None:
        text = "YAnJRJj6gpW7oZ1fGv4b+d2xjo8yQM798A3UWadQSGbnsmzV+2k/KmfqAlvYqIrC"
        feats = cf_v3.extract_features_v3(text)
        # "mz" appears in base64 but MZ is in the noisy set
        assert feats["perfect_pattern_count"] == 0.0

    def test_real_discriminators_still_count(self, cf_v3) -> None:
        # 'rundll32.exe' is a real perfect discriminator that should still count
        text = "The malware launches rundll32.exe to load the payload DLL."
        feats = cf_v3.extract_features_v3(text)
        assert feats["perfect_pattern_count"] >= 1.0


# ---------- Contract: aggregate features ----------


class TestExtractorSignalStrength:
    def test_increases_with_signals(self, cf_v3) -> None:
        marketing_feats = cf_v3.extract_features_v3(_MARKETING_SAMPLE)
        cmdline_feats = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert cmdline_feats["extractor_signal_strength"] > marketing_feats["extractor_signal_strength"]

    def test_zero_for_pure_marketing(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3(_MARKETING_SAMPLE)
        assert feats["extractor_signal_strength"] == 0.0


# ---------- Contract: train/serve parity ----------


class TestTrainServeParity:
    """The model uses positional feature indexing; train and inference
    MUST produce identical feature dicts for the same input."""

    def test_idempotent(self, cf_v3) -> None:
        a = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        b = cf_v3.extract_features_v3(_CMDLINE_SAMPLE)
        assert a == b

    def test_empty_text_returns_all_zeros_safely(self, cf_v3) -> None:
        feats = cf_v3.extract_features_v3("")
        # Must not crash on empty input; structure must be consistent
        assert len(feats) == 20
        # has_code_blocks should be 0 for empty
        assert feats["has_code_blocks"] == 0.0


# ---------- Cross-version comparison ----------


class TestV3ImprovesOverV2:
    """Sanity check that v3 captures signals v2 misses."""

    def test_v3_captures_registry_v2_misses(self, cf_v3, cf_v2) -> None:
        v2_feats = cf_v2.extract_features_v2(_REGISTRY_SAMPLE)
        v3_feats = cf_v3.extract_features_v3(_REGISTRY_SAMPLE)
        # v2 has no registry-specific feature; v3 does
        assert "registry_hive_path_count" not in v2_feats
        assert v3_feats["registry_hive_path_count"] >= 1.0

    def test_v3_captures_yara_v2_misses(self, cf_v3, cf_v2) -> None:
        v2_feats = cf_v2.extract_features_v2(_YARA_SAMPLE)
        v3_feats = cf_v3.extract_features_v3(_YARA_SAMPLE)
        # v2 has no YARA-specific feature
        assert "yara_rule_indicator" not in v2_feats
        assert v3_feats["yara_rule_indicator"] == 1.0
