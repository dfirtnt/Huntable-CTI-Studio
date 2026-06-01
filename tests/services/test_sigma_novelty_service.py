"""Tests for SIGMA novelty service functionality."""

from unittest.mock import Mock, patch

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

    def test_extract_atoms_from_list_of_maps_selection(self, service):
        """List-valued selections (Sigma 'list of maps' = OR) must yield atoms from every map.

        Regression: list selections were previously skipped, producing zero atoms and a
        degenerate canonical form that collapsed unrelated rules onto one exact_hash.
        """
        detection = {
            "condition": "selection",
            "selection": [
                {"Image|endswith": "\\curl.exe"},
                {"CommandLine|contains": "dnscat2"},
            ],
        }

        atoms = service.extract_atomic_predicates(detection)

        assert len(atoms) >= 2
        values = " ".join(a.value for a in atoms).lower()
        assert "curl.exe" in values
        assert "dnscat2" in values

    def test_list_of_maps_selections_produce_distinct_exact_hashes(self, service):
        """Two different list-selection rules must not collapse to the same exact_hash."""

        def exact_hash(selection):
            rule = {
                "logsource": {"product": "windows", "category": "process_creation"},
                "detection": {"condition": "selection", "selection": selection},
            }
            return service.generate_exact_hash(service.build_canonical_rule(rule))

        h1 = exact_hash([{"CommandLine|contains": "alpha"}, {"CommandLine|contains": "beta"}])
        h2 = exact_hash([{"Image|endswith": "\\curl.exe"}, {"Product": "curl"}])

        assert h1 != h2

    def test_atomless_rule_not_flagged_duplicate(self, service):
        """A rule with no extractable atoms has no fingerprint and must never be a DUPLICATE.

        Guards the exact_hash short-circuit: an empty-atom canonical hashes to a degenerate
        value shared by unrelated rules, which previously caused false DUPLICATE suppression.
        """
        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"condition": "keywords", "keywords": ["foo", "bar"]},
        }
        # Precondition: a keyword-only detection yields no field atoms.
        assert service.build_canonical_rule(rule).detection["atoms"] == []

        # Even when a stored rule collides on exact_hash, an atom-less rule is not a duplicate.
        service.retrieve_candidates = Mock(
            return_value=[{"exact_hash": "deadbeef", "rule_id": "x", "exact_hash_match": True}]
        )

        result = service.assess_novelty(rule, threshold=0.0)

        assert result["novelty_label"] == NoveltyLabel.NOVEL


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
            # Service creation aliases — many-to-one must collapse to same canonical
            ("ServiceFileName|contains|literal|bits", "serviceimagepath|contains|literal|bits"),
            ("ImagePath|contains|literal|bits", "serviceimagepath|contains|literal|bits"),
            ("StartType|eq|literal|2", "servicestarttype|eq|literal|2"),
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


# ── Regression: silent-pass degradation warnings (2026-04-30) ─────────────────
# assess_novelty() must surface degradation in return dict when the deterministic
# semantic precompute path fails, so the execution trace UI shows the fallback.


class TestAssessNoveltyDegradationWarnings:
    """Verify that fallback paths emit warnings into the return dict."""

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    @pytest.fixture
    def sample_rule(self):
        return {
            "title": "Test Rule",
            "id": "test-warn-001",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {
                "selection": {"CommandLine|contains": "malware.exe"},
                "condition": "selection",
            },
        }

    def test_no_warnings_key_on_clean_run(self, service, sample_rule):
        """Return dict must NOT contain 'warnings' when no degradation occurs."""
        service.retrieve_candidates = Mock(return_value=[])

        result = service.assess_novelty(sample_rule, threshold=0.7)

        assert "warnings" not in result

    def test_warnings_key_present_when_semantic_precompute_raises(self, service, sample_rule):
        """Return dict must contain 'warnings' when semantic precompute throws."""
        service.retrieve_candidates = Mock(return_value=[])

        with (
            patch(
                "src.services.sigma_novelty_service._sigma_compare_rules_available",
                True,
            ),
            patch(
                "src.services.sigma_semantic_precompute.precompute_semantic_fields",
                side_effect=RuntimeError("precompute boom"),
            ),
        ):
            result = service.assess_novelty(sample_rule, threshold=0.7)

        assert "warnings" in result
        assert len(result["warnings"]) == 1
        assert "semantic_precompute_failed" in result["warnings"][0]

    def test_engine_used_is_legacy_when_semantic_precompute_raises(self, service, sample_rule):
        """engine_used must be 'legacy' when semantic precompute fails."""
        service.retrieve_candidates = Mock(return_value=[])

        with (
            patch(
                "src.services.sigma_novelty_service._sigma_compare_rules_available",
                True,
            ),
            patch(
                "src.services.sigma_semantic_precompute.precompute_semantic_fields",
                side_effect=RuntimeError("precompute boom"),
            ),
        ):
            result = service.assess_novelty(sample_rule, threshold=0.7)

        assert result["engine_used"] == "legacy"

    def test_warnings_logged_when_semantic_precompute_raises(self, service, sample_rule, caplog):
        """A logger.warning must be emitted (not just silently suppressed) on precompute failure."""
        import logging

        service.retrieve_candidates = Mock(return_value=[])

        with (
            patch(
                "src.services.sigma_novelty_service._sigma_compare_rules_available",
                True,
            ),
            patch(
                "src.services.sigma_semantic_precompute.precompute_semantic_fields",
                side_effect=RuntimeError("precompute boom"),
            ),
            caplog.at_level(logging.WARNING, logger="src.services.sigma_novelty_service"),
        ):
            service.assess_novelty(sample_rule, threshold=0.7)

        assert any("semantic precompute" in r.message for r in caplog.records)

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


class TestSnakeCaseFieldAliasNormalization:
    """
    build_canonical_rule must normalise snake_case field names to the same
    canonical form as their PascalCase equivalents so that compute_atom_jaccard
    produces 1.0 for rules that differ only in field name convention.
    """

    def _make_rule(self, field_map: dict) -> dict:
        """Return a minimal process_creation rule dict with the given detection fields."""
        return {
            "title": "Test Rule",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": field_map, "condition": "selection"},
        }

    def test_parent_image_snake_and_pascal_produce_same_canonical_field(self):
        """parent_image and ParentImage must resolve to the same canonical field."""
        service = SigmaNoveltyService()
        canon_snake = service.build_canonical_rule(self._make_rule({"parent_image|contains": "*\\\\powershell.exe"}))
        canon_pascal = service.build_canonical_rule(self._make_rule({"ParentImage|contains": "*\\\\powershell.exe"}))

        # detection["atoms"] holds dicts (built via dataclasses.asdict)
        fields_snake = {a["field"] for a in canon_snake.detection["atoms"]}
        fields_pascal = {a["field"] for a in canon_pascal.detection["atoms"]}
        assert fields_snake == fields_pascal, (
            f"parent_image canonical field {fields_snake!r} != ParentImage canonical field {fields_pascal!r}"
        )

    def test_compute_atom_jaccard_is_one_for_rules_differing_only_in_field_case(self):
        """
        Two rules identical except parent_image vs ParentImage must score
        atom_jaccard == 1.0 in the pairwise comparison path.
        """
        service = SigmaNoveltyService()

        rule_snake = self._make_rule(
            {
                "parent_image|contains": "*\\\\powershell.exe",
                "Image|contains": "*\\\\powershell.exe",
            }
        )
        rule_pascal = self._make_rule(
            {
                "ParentImage|contains": "*\\\\powershell.exe",
                "Image|contains": "*\\\\powershell.exe",
            }
        )

        canonical_snake = service.build_canonical_rule(rule_snake)
        canonical_pascal = service.build_canonical_rule(rule_pascal)
        jaccard = service.compute_atom_jaccard(canonical_snake, canonical_pascal)

        assert jaccard == 1.0, (
            f"Expected atom_jaccard 1.0 for rules differing only in parent_image vs "
            f"ParentImage field casing, got {jaccard}"
        )

    def test_explainability_shows_no_missing_atoms_for_field_casing_only_diff(self):
        """
        generate_explainability must report shared_atoms only (no added_atoms /
        removed_atoms) when both rules detect the same behaviour.
        """
        service = SigmaNoveltyService()

        rule_snake = self._make_rule({"parent_image|contains": "*\\\\powershell.exe"})
        rule_pascal = self._make_rule({"ParentImage|contains": "*\\\\powershell.exe"})

        canonical_snake = service.build_canonical_rule(rule_snake)
        canonical_pascal = service.build_canonical_rule(rule_pascal)
        expl = service.generate_explainability(canonical_snake, canonical_pascal, {})

        assert len(expl["shared_atoms"]) == 1, f"Expected 1 shared atom, got {expl['shared_atoms']}"
        assert expl["added_atoms"] == [], f"Unexpected added_atoms: {expl['added_atoms']}"
        assert expl["removed_atoms"] == [], f"Unexpected removed_atoms: {expl['removed_atoms']}"


class TestAggressiveNormalizationSnakeCase:
    """build_canonical_rule must apply aggressive normalization to snake_case
    CommandLine fields (command_line, process_command_line, parent_command_line)
    the same as it does to their PascalCase equivalents."""

    def _make_rule(self, field_map: dict) -> dict:
        return {
            "title": "Test",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": field_map, "condition": "selection"},
        }

    def test_snake_case_command_line_gets_aggressive_normalization(self):
        """command_line and CommandLine must produce the same canonical atom value."""
        service = SigmaNoveltyService()
        # Extra whitespace and backslash — aggressive normalization collapses these
        value = 'powershell.exe  -enc  "abc"'

        canon_snake = service.build_canonical_rule(self._make_rule({"command_line|contains": value}))
        canon_pascal = service.build_canonical_rule(self._make_rule({"CommandLine|contains": value}))

        atoms_snake = {a["value"] for a in canon_snake.detection["atoms"]}
        atoms_pascal = {a["value"] for a in canon_pascal.detection["atoms"]}
        assert atoms_snake == atoms_pascal, (
            f"command_line atoms {atoms_snake!r} != CommandLine atoms {atoms_pascal!r} — "
            f"aggressive normalization not applied to snake_case field"
        )

    def test_jaccard_is_one_for_rules_differing_only_in_commandline_field_case(self):
        """Two rules identical except command_line vs CommandLine must score 1.0."""
        service = SigmaNoveltyService()
        value = "powershell.exe -enc abc"

        canon_a = service.build_canonical_rule(self._make_rule({"command_line|contains": value}))
        canon_b = service.build_canonical_rule(self._make_rule({"CommandLine|contains": value}))
        assert service.compute_atom_jaccard(canon_a, canon_b) == 1.0
