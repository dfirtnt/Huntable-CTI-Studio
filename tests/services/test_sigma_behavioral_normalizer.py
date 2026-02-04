"""Tests for SIGMA behavioral normalizer functionality."""

import pytest
import yaml

from src.services.sigma_behavioral_normalizer import BehavioralCore, SigmaBehavioralNormalizer

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaBehavioralNormalizer:
    """Test SigmaBehavioralNormalizer functionality."""

    @pytest.fixture
    def normalizer(self):
        """Create SigmaBehavioralNormalizer instance."""
        return SigmaBehavioralNormalizer()

    @pytest.fixture
    def sample_rule(self):
        """Sample SIGMA rule."""
        return """
title: PowerShell Scheduled Task Creation
id: test-rule-123
description: Detects PowerShell scheduled task creation
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'schtasks'
        CommandLine|contains: '/create'
        ParentImage|endswith: '\\powershell.exe'
    condition: selection
level: medium
"""

    def test_extract_behavioral_core_success(self, normalizer, sample_rule):
        """Test successful behavioral core extraction."""
        core = normalizer.extract_behavioral_core(sample_rule)

        assert isinstance(core, BehavioralCore)
        assert len(core.behavior_selectors) > 0
        assert len(core.core_hash) > 0
        assert core.selector_count > 0

    def test_extract_behavioral_core_invalid_yaml(self, normalizer):
        """Test extraction with invalid YAML."""
        invalid_rule = "This is not valid YAML"

        core = normalizer.extract_behavioral_core(invalid_rule)

        assert core.selector_count == 0
        assert core.core_hash == ""

    def test_extract_behavioral_core_no_detection(self, normalizer):
        """Test extraction with rule without detection."""
        rule_data = {"title": "Test Rule", "id": "test-123"}

        core = normalizer.extract_behavioral_core(yaml.dump(rule_data))

        assert core.selector_count == 0

    def test_normalize_selector(self, normalizer):
        """Test selector normalization."""
        selector = "CommandLine|contains: 'schtasks /create'"

        normalized = normalizer._normalize_selector(selector)

        assert isinstance(normalized, str)
        assert len(normalized) > 0

    def test_normalize_commandline(self, normalizer):
        """Test commandline normalization."""
        cmdline = "powershell.exe -Command 'schtasks /create /tn test'"

        normalized = normalizer._normalize_commandline(cmdline)

        assert isinstance(normalized, str)
        # Should normalize whitespace and case
        assert "powershell" in normalized.lower()

    def test_normalize_process_chain(self, normalizer):
        """Test process chain normalization."""
        chain = "cmd.exe -> powershell.exe -> schtasks.exe"

        normalized = normalizer._normalize_process_chain(chain)

        assert isinstance(normalized, str)

    def test_generate_hash_consistency(self, normalizer):
        """Test hash generation consistency."""
        selectors = ["CommandLine|contains:schtasks", "ParentImage|endswith:powershell.exe"]

        hash1 = normalizer._generate_hash(selectors)
        hash2 = normalizer._generate_hash(selectors)

        assert hash1 == hash2  # Should be deterministic
        # Hash includes "sha256:" prefix, so total length is 71 (7 + 64)
        assert len(hash1) >= 64  # SHA256 hex length (with optional prefix)

    def test_extract_commandlines(self, normalizer):
        """Test commandline extraction."""
        detection = {"selection": {"CommandLine|contains": "schtasks", "Image": "powershell.exe"}}

        commandlines = normalizer._extract_commandlines(detection)

        assert isinstance(commandlines, list)
        assert len(commandlines) > 0

    def test_extract_process_chains(self, normalizer):
        """Test process chain extraction."""
        detection = {"selection": {"Image": "powershell.exe", "ParentImage": "cmd.exe"}}

        chains = normalizer._extract_process_chains(detection)

        assert isinstance(chains, list)
