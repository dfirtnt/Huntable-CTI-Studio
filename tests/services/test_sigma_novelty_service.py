"""Tests for SIGMA novelty service functionality."""

from unittest.mock import Mock

import pytest

from src.services.sigma_novelty_service import (
    NoveltyLabel,
    SigmaNoveltyService,
    _normalize_atom_identity,
)

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaNoveltyService:
    """Test SigmaNoveltyService functionality."""

    @pytest.fixture
    def service(self):
        """Create SigmaNoveltyService instance."""
        return SigmaNoveltyService()

    @pytest.fixture
    def sample_rule(self):
        """Sample SIGMA rule."""
        return {
            "title": "PowerShell Scheduled Task Creation",
            "id": "test-rule-123",
            "description": "Detects PowerShell scheduled task creation",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "CommandLine|contains": ["schtasks", "/create"],
                    "ParentImage|endswith": "\\powershell.exe",
                },
                "condition": "selection",
            },
            "level": "medium",
        }

    def test_assess_novelty_novel_rule(self, service, sample_rule):
        """Test novelty assessment for novel rule."""
        # Mock retrieve_candidates to return empty list (no similar rules)
        service.retrieve_candidates = Mock(return_value=[])

        result = service.assess_novelty(sample_rule, threshold=0.7)

        assert "novelty_label" in result
        assert result["novelty_label"] == NoveltyLabel.NOVEL
        assert "canonical_class" in result

    def test_assess_novelty_duplicate_rule(self, service, sample_rule):
        """Test novelty assessment for duplicate rule."""
        # Mock retrieve_candidates to return exact match with exact_hash_match flag
        exact_hash = service.generate_exact_hash(service.build_canonical_rule(sample_rule))
        service.retrieve_candidates = Mock(
            return_value=[{"exact_hash": exact_hash, "rule_id": "existing-rule-123", "exact_hash_match": True}]
        )

        result = service.assess_novelty(sample_rule, threshold=0.7)

        assert result["novelty_label"] == NoveltyLabel.DUPLICATE
        assert "canonical_class" in result

    def test_build_canonical_rule(self, service, sample_rule):
        """Test canonical rule building."""
        canonical = service.build_canonical_rule(sample_rule)

        assert canonical.logsource is not None
        assert canonical.detection is not None
        assert "atoms" in canonical.detection

    def test_generate_exact_hash(self, service, sample_rule):
        """Test exact hash generation."""
        canonical = service.build_canonical_rule(sample_rule)
        hash1 = service.generate_exact_hash(canonical)
        hash2 = service.generate_exact_hash(canonical)

        assert hash1 == hash2  # Should be deterministic
        assert len(hash1) == 64  # SHA256 hex length

    def test_normalize_logsource(self, service):
        """Test logsource normalization returns (logsource_key, service) tuple; callers must unpack."""
        logsource = {"category": "process_creation", "product": "windows"}

        logsource_key, service_name = service.normalize_logsource(logsource)

        assert isinstance(logsource_key, str)
        assert logsource_key == "windows|process_creation"
        assert service_name is None  # no "service" in logsource

    def test_normalize_logsource_with_service(self, service):
        """Test logsource with service returns correct key and service."""
        logsource = {"category": "process_creation", "product": "windows", "service": "sysmon"}

        logsource_key, service_name = service.normalize_logsource(logsource)

        assert logsource_key == "windows|process_creation"
        assert service_name == "sysmon"

    def test_normalize_logsource_non_string_values(self, service):
        """Test logsource with non-string product/category/service uses _str_val (v1.2)."""
        # Product/category/service may be stored as numbers or None; normalize should not raise
        logsource = {"category": "process_creation", "product": 123, "service": None}
        logsource_key, service_name = service.normalize_logsource(logsource)
        assert isinstance(logsource_key, str)
        assert "123" in logsource_key or "|" in logsource_key
        assert service_name is None or service_name == ""

    def test_assess_novelty_similar_rule_includes_penalty_fields(self, service, sample_rule):
        """Test assess_novelty top_matches include service_penalty, filter_penalty, weighted_before_penalties."""
        # Similar rule (different detection) so we get one match through similarity path
        similar_rule = {
            "title": "Other Task Creation",
            "id": "existing-456",
            "description": "Different",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"CommandLine|contains": "schtasks", "Image|endswith": "\\cmd.exe"},
                "condition": "selection",
            },
            "level": "medium",
        }
        canonical = service.build_canonical_rule(sample_rule)
        exact_hash = service.generate_exact_hash(canonical)
        # Candidate without exact_hash_match so we go through similarity computation
        service.retrieve_candidates = Mock(
            return_value=[
                {
                    "exact_hash": "other",
                    "rule_id": "existing-456",
                    "exact_hash_match": False,
                    **similar_rule,
                }
            ]
        )

        result = service.assess_novelty(sample_rule, threshold=0.0)

        assert "top_matches" in result
        if result["top_matches"]:
            match = result["top_matches"][0]
            assert "service_penalty" in match
            assert "filter_penalty" in match
            assert "weighted_before_penalties" in match

    def test_compute_similarity_metrics(self, service, sample_rule):
        """Test similarity metrics computation."""
        canonical1 = service.build_canonical_rule(sample_rule)

        # Create similar rule
        similar_rule = sample_rule.copy()
        similar_rule["detection"]["selection"]["CommandLine|contains"] = "schtasks /create /tn test"
        canonical2 = service.build_canonical_rule(similar_rule)

        metrics = service.compute_similarity_metrics(canonical1, canonical2)

        assert "atom_overlap" in metrics
        assert "logsource_match" in metrics
        assert 0.0 <= metrics["atom_overlap"] <= 1.0


# ── Regression: _normalize_atom_identity runtime normalizer (2026-04-08) ──────
# Ensures the transition shim correctly resolves field aliases and folds case
# on precomputed atom identity strings from the database.
# See docs/solutions/logic-errors/sigma-similarity-case-sensitive-atom-matching-2026-04-08.md


class TestNormalizeAtomIdentity:
    """Tests for the runtime atom identity normalizer."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # snake_case fields -> canonical namespace
            ("command_line|contains|contains|all|delete", "process.command_line|contains|contains|all|delete"),
            ("image|endswith|endswith|/vssadmin.exe", "process.image|endswith|endswith|/vssadmin.exe"),
            ("parent_image|endswith|endswith|/cmd.exe", "process.parent_image|endswith|endswith|/cmd.exe"),
            # Already-canonical fields pass through
            ("process.command_line|contains|contains|cl", "process.command_line|contains|contains|cl"),
            ("process.image|endswith|endswith|/wevtutil.exe", "process.image|endswith|endswith|/wevtutil.exe"),
            # PascalCase (old stored format) -> canonical
            ("CommandLine|contains|contains|all|Delete", "process.command_line|contains|contains|all|delete"),
            # Unknown fields lowercased
            ("OriginalFileName|eq||VSSADMIN.EXE", "originalfilename|eq||vssadmin.exe"),
            # Value casing folded
            ("process.command_line|contains|contains|all|Delete", "process.command_line|contains|contains|all|delete"),
        ],
    )
    def test_normalization(self, raw, expected):
        assert _normalize_atom_identity(raw) == expected

    def test_proposed_vs_stored_atoms_intersect(self):
        """Simulate the actual bug: proposed atoms (snake_case) vs stored atoms (canonical)."""
        # Proposed rule atoms (LLM-generated, snake_case fields, mixed-case values)
        proposed = [
            "command_line|contains|contains|all|Delete",
            "command_line|contains|contains|all|Shadows",
            "image|endswith|endswith|/vssadmin.exe",
            "parent_image|endswith|endswith|/cmd.exe",
        ]
        # Stored SigmaHQ atoms (canonical namespace, lowercase values)
        stored = [
            "process.command_line|contains|contains|all|delete",
            "process.command_line|contains|contains|all|shadow",
            "process.image|endswith|endswith|/vssadmin.exe",
            "originalfilename|eq||vssadmin.exe",
        ]

        A1 = {_normalize_atom_identity(a) for a in proposed}
        A2 = {_normalize_atom_identity(a) for a in stored}
        shared = A1 & A2

        # Must share at least vssadmin.exe and delete
        assert len(shared) >= 2, f"Expected >= 2 shared atoms, got {len(shared)}: {shared}"
        assert "process.image|endswith|endswith|/vssadmin.exe" in shared
        assert "process.command_line|contains|contains|all|delete" in shared

    def test_empty_and_malformed_atoms(self):
        """Edge cases: empty string, no pipe separator."""
        assert _normalize_atom_identity("") == ""
        assert _normalize_atom_identity("justafieldname") == "justafieldname"

    def test_assess_novelty_with_snake_case_fields(self):
        """End-to-end: assess_novelty with snake_case fields finds matches against PascalCase candidates."""
        service = SigmaNoveltyService()

        # Proposed rule uses snake_case fields (LLM-generated)
        proposed = {
            "title": "Test Snake Case",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "image|endswith": "\\cmd.exe",
                    "command_line|contains": "whoami",
                },
                "condition": "selection",
            },
        }

        # Candidate uses PascalCase fields (SigmaHQ standard)
        candidate = {
            "title": "Test PascalCase",
            "rule_id": "test-pascal-001",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {
                    "Image|endswith": "\\cmd.exe",
                    "CommandLine|contains": "whoami",
                },
                "condition": "selection",
            },
            "exact_hash_match": False,
            "exact_hash": "different",
        }

        service.retrieve_candidates = Mock(return_value=[candidate])
        result = service.assess_novelty(proposed, threshold=0.0)

        assert result["behavioral_matches_found"] > 0, (
            "Snake_case proposed rule must find behavioral matches against PascalCase candidates"
        )
        top = result["top_matches"][0]
        assert top["atom_jaccard"] > 0.5, (
            f"Expected high Jaccard for identical detection logic, got {top['atom_jaccard']}"
        )
