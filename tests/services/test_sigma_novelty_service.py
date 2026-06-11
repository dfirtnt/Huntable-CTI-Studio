"""Tests for SIGMA novelty service functionality."""

from unittest.mock import Mock, patch

import pytest

from src.services.sigma_novelty_service import (
    NoveltyLabel,
    SigmaNoveltyService,
    _atom_identity_to_display,
    _normalize_atom_identity,
)

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


def _service_atoms(service: SigmaNoveltyService, detection: dict, logsource: dict | None = None) -> list[dict]:
    rule = {
        "logsource": logsource or {"product": "windows", "category": "process_creation"},
        "detection": detection,
    }
    return service.build_canonical_rule(rule).detection["atoms"]


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

        atoms = _service_atoms(service, detection)

        assert len(atoms) >= 2
        values = " ".join(a["value"] for a in atoms).lower()
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

    def test_atomless_rule_emits_no_atoms_extracted_flag(self, service):
        """The atom-less guard must emit a machine-readable `no_atoms_extracted`
        flag (not just a free-text warning), so downstream routing can send the
        rule to needs_review instead of silently enqueuing it as a confident
        novel. The free-text warning alone was dropped by summarize_rule_novelty.
        """
        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {}, "condition": "selection"},
        }
        service.retrieve_candidates = Mock(return_value=[])
        result = service.assess_novelty(rule, threshold=0.0)
        assert result["novelty_label"] == NoveltyLabel.NOVEL
        assert result.get("no_atoms_extracted") is True

    def test_atomless_rule_not_flagged_duplicate(self, service):
        """A rule with no extractable atoms has no fingerprint and must never be a DUPLICATE.

        Guards the exact_hash short-circuit: an empty-atom canonical hashes to a degenerate
        value shared by unrelated rules, which previously caused false DUPLICATE suppression.

        Post-Item-12: keyword-list selections now produce atoms, so the truly-atom-less
        fixture must be a selection with no field-value pairs at all (or no selection
        block). The guard still applies as defense-in-depth for malformed rules.
        """
        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {}, "condition": "selection"},
        }
        # Precondition: an empty selection yields no atoms.
        assert service.build_canonical_rule(rule).detection["atoms"] == []

        # Even when a stored rule collides on exact_hash, an atom-less rule is not a duplicate.
        service.retrieve_candidates = Mock(
            return_value=[{"exact_hash": "deadbeef", "rule_id": "x", "exact_hash_match": True}]
        )

        result = service.assess_novelty(rule, threshold=0.0)

        assert result["novelty_label"] == NoveltyLabel.NOVEL


# ── Item 11: atom-less exact_hash root-cause closure (2026-06-01) ─────────────
# generate_exact_hash returns None for atom-less canonical rules so the
# sigma_rules.exact_hash column is NULL for keyword-only Sigma detections and
# no SHA256 collisions can form across unrelated rules in the database. The
# bd71d9cc assess_novelty:280 guard already handles the downstream
# manifestation; this closes the upstream root cause so the latent pattern
# can never become observable if that guard is later refactored.
# Spec: docs/development/sigma-novelty-audit-followup-2026-06-01.md (Item 11)


class TestExactHashAtomLessReturnsNone:
    """generate_exact_hash returns None when canonical_rule has zero atoms."""

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    def test_atomless_empty_selection_rule_returns_none(self, service):
        """Truly-atom-less shape: a selection with no field-value pairs. Post-Item-12,
        keyword-list selections produce atoms; this test migrated to use empty-dict
        selections to keep covering the Item-11 contract.
        """
        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {}, "condition": "selection"},
        }
        canonical = service.build_canonical_rule(rule)
        assert canonical.detection["atoms"] == []
        assert service.generate_exact_hash(canonical) is None

    def test_atom_bearing_rule_still_returns_sha256(self, service):
        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"CommandLine|contains": "powershell.exe"},
                "condition": "selection",
            },
        }
        canonical = service.build_canonical_rule(rule)
        assert canonical.detection["atoms"]
        h = service.generate_exact_hash(canonical)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_two_distinct_atomless_rules_both_return_none(self, service):
        """The latent collision: two unrelated atom-less rules previously hashed
        to the same value. After the fix both are None, and SQL NULL = NULL
        evaluates to false, so retrieve_candidates cannot return either as an
        exact-hash duplicate of the other. Post-Item-12, atom-less rules are
        empty-selection rules (keywords now produce atoms).
        """
        rule_a = {
            "logsource": {"product": "cisco", "category": "application"},
            "detection": {"selection": {}, "condition": "selection"},
        }
        rule_b = {
            "logsource": {"product": "linux", "category": "network_connection"},
            "detection": {"sel": {}, "condition": "sel"},
        }
        assert service.generate_exact_hash(service.build_canonical_rule(rule_a)) is None
        assert service.generate_exact_hash(service.build_canonical_rule(rule_b)) is None

    def test_retrieve_candidates_skips_exact_match_when_proposed_hash_is_none(self):
        """SQLAlchemy translates column == None to SQL IS NULL — which would
        match every atom-less row (now NULL per the guard above) and surface
        one as a false DUPLICATE. retrieve_candidates must skip the
        exact-match short-circuit entirely when the proposed hash is None.
        """
        mock_session = Mock()
        query_mock = mock_session.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.all.return_value = []
        # If the exact-hash branch IS called, .first() would return this row —
        # the test asserts the branch is skipped so the row never surfaces.
        atomless_row = Mock()
        atomless_row.rule_id = "atomless-collider"
        atomless_row.title = "Atom-less Rule"
        atomless_row.logsource = {}
        atomless_row.detection = {}
        atomless_row.positive_atoms = None
        query_mock.first.return_value = atomless_row

        service = SigmaNoveltyService(db_session=mock_session)
        result = service.retrieve_candidates(
            exact_hash=None,
            logsource_key="windows|process_creation",
            top_k=20,
        )

        call_names = [c[0] for c in query_mock.method_calls]
        assert "first" not in call_names, (
            f"retrieve_candidates called .first() despite exact_hash=None; "
            f"this would surface an atom-less row via SQL IS NULL. "
            f"Call sequence: {call_names}"
        )
        assert not any(c.get("phase1_path") == "exact_hash" for c in result), (
            "retrieve_candidates returned an exact-hash phase1_path match for None hash"
        )


# ── Item 12: keyword-list selections produce atoms (2026-06-01) ───────────────
# Top-level selections whose value is a list of scalars are Sigma keyword
# selections — field-less contains-match against the raw event. The legacy
# extractor previously dropped them entirely, collapsing rules whose unique
# detection signal lived in keyword scalars onto identical atom sets (the
# residual collisions surfaced by Item 11's verification). After this fix,
# each scalar becomes an atom with field="" and op="contains", so behaviorally
# distinct rules produce distinct atom sets and distinct exact_hash values.
# Spec: docs/development/sigma-novelty-audit-followup-2026-06-01.md (Item 12)
# Patzke refs: Introducing Sigma Value Modifiers / Generic Log Sources.


class TestKeywordListSelectionsProduceAtoms:
    """The service canonical path handles top-level list-of-scalars selections."""

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    def test_keyword_list_of_strings_produces_one_atom_per_scalar(self, service):
        detection = {
            "keywords": ["<script>", "onerror=", "javascript:"],
            "condition": "keywords",
        }
        atoms = _service_atoms(service, detection)
        values = sorted(a["value"] for a in atoms)
        assert values == sorted(["<script>", "onerror=", "javascript:"])
        for a in atoms:
            assert a["field"] == ""
            assert a["op"] == "contains"
            assert a["op_type"] == "literal"
            assert a["polarity"] == "positive"

    def test_xss_vs_ssti_rules_produce_distinct_atom_sets(self, service):
        """The actual residual collision Item 12 closes: both rules share the
        cs-method=GET selection and sc-status=404 filter; only the keywords
        differ. Pre-fix they hashed identically; post-fix the keyword atoms
        differentiate them.
        """
        xss = {
            "select_method": {"cs-method": "GET"},
            "keywords": ["=<script>", "onerror=", "javascript:alert"],
            "filter": {"sc-status": 404},
            "condition": "select_method and keywords and not filter",
        }
        ssti = {
            "select_method": {"cs-method": "GET"},
            "keywords": ["={{", "=${", "freemarker.template.utility.Execute"],
            "filter": {"sc-status": 404},
            "condition": "select_method and keywords and not filter",
        }
        xss_keys = {(a["field"], a["op"], a["value"], a["polarity"]) for a in _service_atoms(service, xss)}
        ssti_keys = {(a["field"], a["op"], a["value"], a["polarity"]) for a in _service_atoms(service, ssti)}
        assert xss_keys != ssti_keys
        # Both still carry the shared boilerplate
        shared = xss_keys & ssti_keys
        assert any(k[2] == "get" for k in shared), "shared cs-method=GET atom should be in both"
        # XSS has unique keyword content that SSTI lacks
        xss_only = xss_keys - ssti_keys
        assert any("script" in k[2].lower() for k in xss_only)

    def test_keyword_list_of_ints_produces_atoms(self, service):
        """auditd-style: initselection: [0, 6] — integer scalars."""
        detection = {
            "initselection": [0, 6],
            "condition": "initselection",
        }
        atoms = _service_atoms(service, detection)
        values = sorted(a["value"] for a in atoms)
        assert values == ["0", "6"]
        assert all(a["field"] == "" and a["op"] == "contains" for a in atoms)

    def test_keyword_list_negated_in_condition_has_negative_polarity(self, service):
        detection = {
            "selection": {"EventID": 4624},
            "keywords": ["error", "fail"],
            "condition": "selection and not keywords",
        }
        atoms = _service_atoms(service, detection)
        keyword_atoms = [a for a in atoms if a["field"] == ""]
        assert len(keyword_atoms) == 2
        assert all(a["polarity"] == "negative" for a in keyword_atoms)

    def test_mixed_list_of_dicts_and_scalars(self, service):
        """Edge case: a list containing both maps and scalars. Both contributors
        should produce atoms — dicts via the block path, scalars via the keyword path.
        """
        detection = {
            "mixed": [{"Image|endswith": "\\foo.exe"}, "scalar_keyword"],
            "condition": "mixed",
        }
        atoms = _service_atoms(service, detection)
        values = [a["value"] for a in atoms]
        assert "/foo.exe" in values
        assert "scalar_keyword" in values
        # The dict contributed a field-bearing atom; the scalar contributed a keyword atom.
        field_atoms = [a for a in atoms if a["field"] != ""]
        keyword_atoms = [a for a in atoms if a["field"] == ""]
        assert len(field_atoms) == 1
        assert len(keyword_atoms) == 1

    def test_existing_dict_only_selection_unchanged(self, service):
        """Regression guard: pure-dict selections continue to produce field-bearing
        atoms exactly as before (no double-extraction, no keyword atoms).
        """
        detection = {
            "selection": {"CommandLine|contains": "powershell.exe"},
            "condition": "selection",
        }
        atoms = _service_atoms(service, detection)
        assert len(atoms) == 1
        assert atoms[0]["field"] != ""
        assert atoms[0]["value"] == "powershell.exe"

    def test_former_keyword_only_rule_no_longer_atomless(self, service):
        """Direct assertion that Item 12 reduces the Item-11 atom-less population:
        rules that were the canonical Item-11 bug shape now produce atoms and
        no longer hit the atom-less guard at assess_novelty:280.
        """
        rule = {
            "logsource": {"product": "windows"},
            "detection": {"keywords": ["foo", "bar"], "condition": "keywords"},
        }
        canonical = service.build_canonical_rule(rule)
        atoms = canonical.detection["atoms"]
        assert len(atoms) == 2
        # And exact_hash is now real (not None per the Item-11 guard).
        assert service.generate_exact_hash(canonical) is not None

    def test_filter_keyword_list_positively_referenced_has_positive_polarity(self, service):
        """Real-world shape: SigmaHQ's "Remote File Copy" rule (`7a14080d-…`) names a
        selection `filter` but references it POSITIVELY in the condition
        (`condition: tools and filter`) — the @ and : scalars are refinements, not
        exclusions. Polarity must follow the condition, not the selection's name.

        Regression guard for a bug where _polarity_for_selection_key short-circuited
        on key.startswith("filter") and stamped the atoms negative regardless of
        the condition string.
        """
        detection = {
            "tools": ["scp ", "rsync ", "sftp "],
            "filter": ["@", ":"],
            "condition": "tools and filter",
        }
        atoms = _service_atoms(service, detection)
        filter_atoms = [a for a in atoms if a["value"] in ("@", ":")]
        assert len(filter_atoms) == 2
        assert all(a["polarity"] == "positive" for a in filter_atoms), (
            f"filter atoms must be positive when condition positively references the "
            f"selection; got polarities: {[a['polarity'] for a in filter_atoms]}"
        )

    def test_filter_keyword_list_negated_in_condition_has_negative_polarity(self, service):
        """Companion to the positive-reference test above: when the condition
        explicitly negates a filter selection (`not filter`), the polarity flips.
        """
        detection = {
            "tools": ["scp ", "rsync ", "sftp "],
            "filter": ["benign1", "benign2"],
            "condition": "tools and not filter",
        }
        atoms = _service_atoms(service, detection)
        filter_atoms = [a for a in atoms if a["value"] in ("benign1", "benign2")]
        assert len(filter_atoms) == 2
        assert all(a["polarity"] == "negative" for a in filter_atoms), (
            f"filter atoms must be negative when condition explicitly negates the "
            f"selection; got polarities: {[a['polarity'] for a in filter_atoms]}"
        )


# ── Regression guard: _extract_block_atoms polarity for dict-valued filter ────
# Companion to TestKeywordListSelectionsProduceAtoms's filter-polarity tests.
# The dict-block polarity logic at sigma_novelty_service.py:755-761 is correct
# (key.startswith("filter") is the OUTER fast-path; the INNER `f"not {key}" in
# condition` is the actual decision). These tests lock that contract in so a
# future refactor that extracts a polarity helper from _extract_block_atoms
# cannot repeat the bug fixed in commit f2347bf7, where the keyword-path helper
# treated startswith("filter") as sufficient for negative polarity.


class TestDictBlockSelectionPolarity:
    """_extract_block_atoms produces correct polarity for dict-valued filter blocks."""

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    def test_dict_filter_positively_referenced_has_positive_polarity(self, service):
        """Dict-block analog of test_filter_keyword_list_positively_referenced_…:
        a `filter`-named dict block that's referenced POSITIVELY in the condition
        (`selection and filter`) yields positive polarity. Naming is not enough.
        """
        detection = {
            "selection": {"CommandLine|contains": "powershell"},
            "filter": {"Image|endswith": "\\benign.exe"},
            "condition": "selection and filter",
        }
        atoms = _service_atoms(service, detection)
        filter_atoms = [a for a in atoms if a["value"] == "/benign.exe"]
        assert len(filter_atoms) == 1
        assert filter_atoms[0]["polarity"] == "positive", (
            f"dict filter block must be positive when condition positively references the "
            f"selection; got polarity: {filter_atoms[0]['polarity']}"
        )

    def test_dict_filter_negated_in_condition_has_negative_polarity(self, service):
        """Companion to the positive-reference test: explicit `not filter` in the
        condition flips the dict-block polarity to negative.
        """
        detection = {
            "selection": {"CommandLine|contains": "powershell"},
            "filter": {"Image|endswith": "\\benign.exe"},
            "condition": "selection and not filter",
        }
        atoms = _service_atoms(service, detection)
        filter_atoms = [a for a in atoms if a["value"] == "/benign.exe"]
        assert len(filter_atoms) == 1
        assert filter_atoms[0]["polarity"] == "negative", (
            f"dict filter block must be negative when condition explicitly negates the "
            f"selection; got polarity: {filter_atoms[0]['polarity']}"
        )


# ── compute_atom_jaccard: two atom-less rules are incomparable, not identical ──
# Two rules with no positive behavioral atoms share no measurable signal. The
# prior `return 1.0` for two empty positive-atom sets could mark unrelated
# atom-less / filter-only rules as a perfect match in the legacy fallback path
# (sigma_novelty_service.py:442) and the /sigma-ab-test diagnostic
# (sigma_ab_test.py:102). Returning 0.0 routes them to NOVEL, consistent with the
# Item 11 atom-less guard. Closes the secondary bug noted on the "Similarity
# System bugs" Todoist task (the primary list-selection reproduction was already
# closed by bd71d9cc / Item 1 and Item 12).


class TestComputeAtomJaccardEmptySets:
    """compute_atom_jaccard must not treat two atom-less rules as identical."""

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    def test_two_empty_positive_atom_rules_score_zero(self, service):
        r1 = service.build_canonical_rule(
            {"logsource": {"product": "windows"}, "detection": {"selection": {}, "condition": "selection"}}
        )
        r2 = service.build_canonical_rule(
            {"logsource": {"product": "linux"}, "detection": {"sel": {}, "condition": "sel"}}
        )
        # Precondition: both have empty atom sets.
        assert r1.detection["atoms"] == []
        assert r2.detection["atoms"] == []
        assert service.compute_atom_jaccard(r1, r2) == 0.0

    def test_identical_atom_bearing_rules_still_score_one(self, service):
        """Regression guard: the fix touches ONLY the both-empty case. Two rules
        with identical real atoms must still score 1.0.
        """
        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {"CommandLine|contains": "powershell.exe"}, "condition": "selection"},
        }
        r = service.build_canonical_rule(rule)
        assert service.compute_atom_jaccard(r, r) == 1.0


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


# ── Precomputed-path explainability display format (3-slot → human-readable) ──
# The precomputed (deterministic) path stores raw `field|modifier_chain|value`
# identities; _atom_identity_to_display renders them in the same `field|op:value`
# shape as the full-parse path's _atom_to_string so both surfaces match.


class TestAtomIdentityToDisplay:
    """`_atom_identity_to_display` mirrors the full-parse `_atom_to_string` format."""

    def test_modifier_atom_renders_field_op_value(self):
        assert _atom_identity_to_display("process.image|endswith|/php.exe") == "process.image|endswith:/php.exe"

    def test_no_double_modifier_in_output(self):
        # The old 4-slot bug surfaced `process.image|endswith|endswith|/php.exe`.
        out = _atom_identity_to_display("process.image|endswith|/php.exe")
        assert out.count("endswith") == 1

    def test_eq_atom_empty_chain_renders_field_value(self):
        # Empty modifier chain (`field||value`) ⟹ default eq ⟹ `field:value`.
        assert _atom_identity_to_display("originalfilename||powershell.exe") == "originalfilename:powershell.exe"

    def test_all_modifier_chain_uses_leading_op(self):
        # `contains|all` ⟹ op is the leading token `contains`.
        assert (
            _atom_identity_to_display("process.command_line|contains|all|delete")
            == "process.command_line|contains:delete"
        )

    def test_keyword_atom_field_less(self):
        assert _atom_identity_to_display("|contains|whoami") == "|contains:whoami"

    def test_malformed_passes_through(self):
        assert _atom_identity_to_display("justafield") == "justafield"


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
                "src.services.sigma_atom_precompute.extract_atom_fields",
                side_effect=RuntimeError("precompute boom"),
            ),
        ):
            result = service.assess_novelty(sample_rule, threshold=0.7)

        assert "warnings" in result
        assert len(result["warnings"]) == 1
        assert "atom_precompute_failed" in result["warnings"][0]

    def test_engine_used_is_legacy_when_semantic_precompute_raises(self, service, sample_rule):
        """engine_used must be 'legacy' when semantic precompute fails."""
        service.retrieve_candidates = Mock(return_value=[])

        with (
            patch(
                "src.services.sigma_novelty_service._sigma_compare_rules_available",
                True,
            ),
            patch(
                "src.services.sigma_atom_precompute.extract_atom_fields",
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
                "src.services.sigma_atom_precompute.extract_atom_fields",
                side_effect=RuntimeError("precompute boom"),
            ),
            caplog.at_level(logging.WARNING, logger="src.services.sigma_novelty_service"),
        ):
            service.assess_novelty(sample_rule, threshold=0.7)

        assert any("atom extraction" in r.message for r in caplog.records)

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


class TestRetrieveCandidatesDeterministicOrdering:
    """Spec Item 7 (P1: sort LIMIT).

    The two fallback candidate-retrieval queries in retrieve_candidates use
    .limit(top_k) without a preceding .order_by(). Without a stable sort,
    Postgres returns whichever rows it likes — different across runs, replicas,
    after VACUUM. Both fallbacks must order before LIMIT so the same input
    produces the same top-k every call.
    """

    @pytest.mark.parametrize(
        "use_deterministic, canonical_class",
        [
            (False, None),  # else-branch fallback
            (True, "windows.process_creation"),  # if-branch's empty-canonical_class fallback
        ],
        ids=["else_branch", "canonical_class_empty_fallback"],
    )
    def test_fallback_path_orders_before_limit(self, use_deterministic, canonical_class):
        """retrieve_candidates' fallback paths must call .order_by() before .limit()."""
        mock_session = Mock()
        # Fluent query chain: every method returns the same mock so the chain composes.
        query_mock = mock_session.query.return_value
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.all.return_value = []

        # For canonical_class path: the initial .filter(canonical_class=X).all() must
        # return [] so the code falls through to the logsource_key + LIMIT path.
        if use_deterministic:
            # First .all() (canonical_class branch) returns []; second .all() (fallback) returns [].
            query_mock.all.side_effect = [[], []]

        # Stub exact_hash lookup so it doesn't short-circuit before the fallback.
        # The exact_hash query is via .filter(exact_hash=...).first() and must return None.
        query_mock.first.return_value = None

        service = SigmaNoveltyService(db_session=mock_session)
        service.retrieve_candidates(
            exact_hash="not-a-real-hash",
            logsource_key="windows|process_creation",
            top_k=20,
            canonical_class=canonical_class,
            use_deterministic=use_deterministic,
        )

        call_names = [c[0] for c in query_mock.method_calls]
        assert "limit" in call_names, f"limit must be called; got: {call_names}"
        assert "order_by" in call_names, (
            f"order_by must be called before limit for deterministic candidate retrieval; "
            f"got call sequence: {call_names}"
        )
        assert call_names.index("order_by") < call_names.index("limit"), (
            f"order_by must come BEFORE limit; got call sequence: {call_names}"
        )


# ---------------------------------------------------------------------------
# Extractor convergence (/compare slice of the extractor-collapse task).
# Bug: `not N of filter_*` atoms mis-polarized as positive by the in-src
# extractor polluted atom_jaccard on /sigma-ab-test (Todoist 6gqhWHxjgpWGHGP3).
# Fix direction (b): pairwise comparison converges onto the precompute
# (sigma_similarity package) extractor via compare_precomputed_atoms.
# ---------------------------------------------------------------------------


class TestComparePrecomputedSemantics:
    """Unit tests for SigmaNoveltyService.compare_precomputed_atoms.

    The single scorer for the precomputed-atom path: assess_novelty's
    stored-atom branch and /sigma-ab-test /compare both call this.
    Pure set math over semantic-field dicts; no YAML parsing.
    """

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    @staticmethod
    def _sem(positive, negative, surface=4, canonical_class="windows.process_creation"):
        return {
            "canonical_class": canonical_class,
            "positive_atoms": list(positive),
            "negative_atoms": list(negative),
            "surface_score": surface,
        }

    def test_filter_only_difference_penalized_once_not_jaccard_polluted(self, service):
        """Filter atoms affect the score through exactly ONE mechanism (the
        filter penalty). They must not leak into the positive jaccard set:
        identical positives + divergent filters => jaccard stays 1.0 and the
        whole difference lands in filter_penalty (no double-count)."""
        positives = ["fielda|contains|x", "fieldb|endswith|y", "fieldc||z"]
        sem_a = self._sem(positives, ["neg1|contains|f1", "neg2|contains|f2"])
        sem_b = self._sem(positives, [])

        result = service.compare_precomputed_atoms(sem_a, sem_b)

        assert result is not None
        assert result["atom_jaccard"] == 1.0
        assert result["logic_shape_similarity"] == 1.0
        assert result["filter_penalty"] == pytest.approx(0.5)  # min(0.5, 2/3)
        assert result["service_penalty"] == 0.0
        # similarity = jaccard * containment - filter_penalty: the ONLY place
        # the filter difference is counted.
        assert result["similarity"] == pytest.approx(0.5)
        assert result["weighted_before_penalties"] == pytest.approx(1.0)
        assert result["similarity_engine"] == "deterministic"

    def test_explainability_sets_and_display_formatting(self, service):
        """shared/added/removed come from positive sets only; filter
        differences from negative sets; all rendered via the shared
        3-slot display format (field|op:value)."""
        sem_a = self._sem(["fielda|contains|x", "shared||v"], ["neg1|contains|f"])
        sem_b = self._sem(["fieldb|endswith|y", "shared||v"], [])

        result = service.compare_precomputed_atoms(sem_a, sem_b)

        assert result["shared_atoms"] == ["shared:v"]
        assert result["added_atoms"] == ["fieldb|endswith:y"]
        assert result["removed_atoms"] == ["fielda|contains:x"]
        assert result["filter_differences"] == ["neg1|contains:f"]

    def test_atom_details_carry_containment_and_class(self, service):
        positives = ["fielda|contains|x"]
        sem_a = self._sem(positives, [], surface=3)
        sem_b = self._sem(positives, [], surface=3)

        result = service.compare_precomputed_atoms(sem_a, sem_b)

        details = result["atom_details"]
        assert details["canonical_class"] == "windows.process_creation"
        assert details["jaccard"] == 1.0
        assert details["containment_factor"] == 1.0
        assert details["overlap_ratio_a"] == 1.0
        assert details["overlap_ratio_b"] == 1.0
        assert details["surface_score_a"] == 3.0
        assert details["surface_score_b"] == 3.0
        assert details["reason_flags"] == []

    def test_disjoint_positive_sets_flag_no_shared_atoms(self, service):
        """Non-exe disjoint positives: jaccard 0, containment floor 0.65,
        similarity 0, reason flag set."""
        sem_a = self._sem(["regkey|contains|run"], [])
        sem_b = self._sem(["svc.name||foo"], [])

        result = service.compare_precomputed_atoms(sem_a, sem_b)

        assert result["atom_jaccard"] == 0.0
        assert result["logic_shape_similarity"] == 0.65
        assert result["similarity"] == 0.0
        assert result["atom_details"]["reason_flags"] == ["no_shared_atoms"]

    def test_empty_positive_sets_score_zero(self, service):
        sem_a = self._sem([], ["neg1|contains|f"])
        sem_b = self._sem([], [])

        result = service.compare_precomputed_atoms(sem_a, sem_b)

        assert result["atom_jaccard"] == 0.0
        assert result["similarity"] == 0.0
        assert result["filter_penalty"] == 0.0
        assert result["atom_details"]["reason_flags"] == ["no_shared_atoms"]

    def test_returns_none_when_package_primitives_unavailable(self, service, monkeypatch):
        """Callers fall back to the legacy in-src path when the
        sigma_similarity package is not importable."""
        monkeypatch.setattr("src.services.sigma_novelty_service.compute_containment", None)
        sem = self._sem(["fielda|contains|x"], [])

        assert service.compare_precomputed_atoms(sem, sem) is None

    def test_field_alias_normalization_applies_to_both_sides(self, service):
        """LLM-style snake_case fields and stored canonical fields must
        resolve to the same atom identity (regression for the runtime
        alias safety net)."""
        sem_a = self._sem(["command_line|contains|whoami"], [])
        sem_b = self._sem(["process.command_line|contains|WHOAMI"], [])

        result = service.compare_precomputed_atoms(sem_a, sem_b)

        assert result["atom_jaccard"] == 1.0


class TestPackageExtractorConvergence:
    """AC pins for the convergence: the package extractor (the single
    extractor /compare now uses) classifies `not N of filter_*` polarity
    correctly, and live extraction matches the stored DB atom snapshot."""

    # DB snapshot 2026-06-10 (sigma_rules.id=2002, SigmaHQ 178e615d-...,
    # "Suspicious Command Patterns In Scheduled Task Creation" family pair).
    # If the package's atom identity logic changes intentionally, update this
    # snapshot AND run recompute-atoms so stored atoms stay in lockstep.
    RULE_2002_LOGSOURCE = {"product": "windows", "category": "process_creation"}
    RULE_2002_DETECTION = {
        "condition": "all of selection_* and not 1 of filter_main_* and not 1 of filter_optional_*",
        "selection_user": {"LogonId": "0x3e7", "User|contains": ["AUTHORI", "AUTORI"]},
        "selection_shell": [
            {"Image|endswith": ["\\powershell.exe", "\\powershell_ise.exe", "\\pwsh.exe", "\\cmd.exe"]},
            {"OriginalFileName": ["PowerShell.EXE", "powershell_ise.EXE", "pwsh.dll", "Cmd.Exe"]},
        ],
        "filter_main_generic": {
            "ParentImage|contains": [
                ":\\Program Files (x86)\\",
                ":\\Program Files\\",
                ":\\ProgramData\\",
                ":\\Windows\\System32\\",
                ":\\Windows\\SysWOW64\\",
                ":\\Windows\\Temp\\",
                ":\\Windows\\WinSxS\\",
            ]
        },
        "filter_optional_asgard": {
            "CommandLine|contains": ':\\WINDOWS\\system32\\cmd.exe /c "',
            "CurrentDirectory|contains": ":\\WINDOWS\\Temp\\asgard2-agent\\",
        },
        "filter_main_parent_null": {"ParentImage": None},
        "filter_main_parent_empty": {"ParentImage": ["", "-"]},
        "filter_optional_manageengine": {
            "Image|endswith": "\\cmd.exe",
            "ParentImage|endswith": ":\\ManageEngine\\ADManager Plus\\pgsql\\bin\\postgres.exe",
        },
        "filter_optional_ibm_spectrumprotect": {
            "CommandLine|contains": ":\\IBM\\SpectrumProtect\\webserver\\scripts\\",
            "ParentImage|contains": ":\\IBM\\SpectrumProtect\\webserver\\scripts\\",
        },
    }
    RULE_2002_STORED_POS = [
        "logonid||0x3e7",
        "originalfilename||cmd.exe",
        "originalfilename||powershell.exe",
        "originalfilename||powershell_ise.exe",
        "originalfilename||pwsh.dll",
        "process.image|endswith|/cmd.exe",
        "process.image|endswith|/powershell.exe",
        "process.image|endswith|/powershell_ise.exe",
        "process.image|endswith|/pwsh.exe",
        "user|contains|authori",
        "user|contains|autori",
    ]
    RULE_2002_STORED_NEG = [
        "currentdirectory|contains|:/windows/temp/asgard2-agent/",
        "process.command_line|contains|:/ibm/spectrumprotect/webserver/scripts/",
        'process.command_line|contains|:/windows/system32/cmd.exe /c "',
        "process.image|endswith|/cmd.exe",
        "process.parent_image|contains|:/ibm/spectrumprotect/webserver/scripts/",
        "process.parent_image|contains|:/program files (x86)/",
        "process.parent_image|contains|:/program files/",
        "process.parent_image|contains|:/programdata/",
        "process.parent_image|contains|:/windows/system32/",
        "process.parent_image|contains|:/windows/syswow64/",
        "process.parent_image|contains|:/windows/temp/",
        "process.parent_image|contains|:/windows/winsxs/",
        "process.parent_image|endswith|:/manageengine/admanager plus/pgsql/bin/postgres.exe",
        "process.parent_image||",
        "process.parent_image||-",
    ]

    def test_not_n_of_filter_wildcard_atoms_classified_negative(self):
        """Regression (Todoist 6gqhWHxjgpWGHGP3): atoms under selections
        negated via `not N of <prefix>_*` wildcard-quantified references are
        polarity=negative and therefore excluded from the positive jaccard set."""
        pytest.importorskip("sigma_similarity")
        from src.services.sigma_atom_precompute import precompute_atom_fields

        rule = {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"Image|endswith": "\\evil.exe"},
                "filter_main_legit": {"ParentImage|contains": ":\\Program Files\\"},
                "filter_optional_tool": {"CommandLine|contains": "safedeploy"},
                "condition": "selection and not 1 of filter_main_* and not 1 of filter_optional_*",
            },
        }

        sem = precompute_atom_fields(rule)

        assert sem is not None
        positives = sem["positive_atoms"]
        negatives = sem["negative_atoms"]
        assert len(positives) == 1
        assert "evil.exe" in positives[0]
        assert len(negatives) == 2
        assert any("program files" in a for a in negatives)
        assert any("safedeploy" in a for a in negatives)
        assert not any("program files" in a or "safedeploy" in a for a in positives)

    def test_package_extraction_parity_with_db_snapshot_rule_2002(self):
        """Live package extraction of the repro rule equals its stored DB
        atoms (11 positive / 15 negative) -- the extractor-agreement proof
        that live-parse and precomputed scoring use one extractor."""
        pytest.importorskip("sigma_similarity")
        from src.services.sigma_atom_precompute import precompute_atom_fields

        sem = precompute_atom_fields({"logsource": self.RULE_2002_LOGSOURCE, "detection": self.RULE_2002_DETECTION})

        assert sem is not None
        assert sem["canonical_class"] == "windows.process_creation"
        assert sem["surface_score"] == 16
        assert sem["positive_atoms"] == self.RULE_2002_STORED_POS
        assert sem["negative_atoms"] == self.RULE_2002_STORED_NEG


class TestSingleExtractorTimingConsolidation:
    """Precomputed and live fallback timings must use the same package extractor."""

    @pytest.fixture
    def service(self):
        return SigmaNoveltyService()

    def test_legacy_extract_atomic_predicates_entrypoint_removed(self, service):
        assert not hasattr(service, "extract_atomic_predicates")

    def test_candidate_with_null_atoms_scores_same_as_precomputed_candidate(self, service):
        from src.services.sigma_atom_precompute import extract_atom_fields

        proposed = {
            "title": "Proposed Cmd",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"CommandLine|contains": "whoami", "Image|endswith": "\\cmd.exe"},
                "condition": "selection",
            },
        }
        candidate = {
            "title": "Candidate Cmd",
            "rule_id": "candidate-cmd",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"CommandLine|contains": "whoami", "Image|endswith": "\\cmd.exe"},
                "condition": "selection",
            },
            "exact_hash": "different",
            "exact_hash_match": False,
        }
        sem = extract_atom_fields(candidate, require_canonical_class=False)
        assert sem is not None

        service.retrieve_candidates = Mock(
            return_value=[
                {
                    **candidate,
                    "positive_atoms": sem["positive_atoms"],
                    "negative_atoms": sem["negative_atoms"],
                    "surface_score": sem["surface_score"],
                }
            ]
        )
        precomputed_result = service.assess_novelty(proposed, threshold=0.0)

        service.retrieve_candidates = Mock(return_value=[candidate])
        live_result = service.assess_novelty(proposed, threshold=0.0)

        precomputed_match = precomputed_result["top_matches"][0]
        live_match = live_result["top_matches"][0]
        assert live_match["similarity_engine"] == "deterministic"
        assert live_match["atom_jaccard"] == precomputed_match["atom_jaccard"]
        assert live_match["similarity"] == precomputed_match["similarity"]
        assert live_match["shared_atoms"] == precomputed_match["shared_atoms"]

    def test_unknown_canonical_class_still_scores_with_live_package_atoms(self, service):
        proposed = {
            "title": "Unknown Telemetry Proposed",
            "logsource": {"product": "custom", "category": "application"},
            "detection": {"keywords": ["suspicious-token"], "condition": "keywords"},
        }
        candidate = {
            "title": "Unknown Telemetry Candidate",
            "rule_id": "custom-candidate",
            "logsource": {"product": "custom", "category": "application"},
            "detection": {"keywords": ["suspicious-token"], "condition": "keywords"},
            "exact_hash": "different",
            "exact_hash_match": False,
        }

        service.retrieve_candidates = Mock(return_value=[candidate])
        result = service.assess_novelty(proposed, threshold=0.0)

        assert result["canonical_class"] is None
        assert result["engine_used"] == "deterministic"
        assert result["top_matches"][0]["atom_jaccard"] == 1.0
        assert result["top_matches"][0]["atom_details"]["canonical_class"] is None
