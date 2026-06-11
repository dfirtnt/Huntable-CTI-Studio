"""Tests for SIGMA matching service functionality."""

from unittest.mock import Mock, patch

import pytest

from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_novelty_service import NoveltyLabel

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaMatchingService:
    """Test SigmaMatchingService functionality."""

    def test_init_does_not_create_embedding_clients(self, mock_db_session):
        """SigmaMatchingService should not instantiate embedding clients until needed."""
        with patch("src.services.sigma_matching_service.EmbeddingService") as mock_embedding_cls:
            service = SigmaMatchingService(mock_db_session)

        assert service._embedding_service is None
        assert service._sigma_embedding_client is None
        mock_embedding_cls.assert_not_called()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        session.connection = Mock()
        return session

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = Mock()
        service.generate_embedding = Mock(return_value=[0.1] * 768)
        service.generate_embeddings_batch = Mock(return_value=[[0.1] * 768] * 4)
        return service

    @pytest.fixture
    def mock_sigma_embedding_client(self):
        """Create mock SIGMA embedding client."""
        client = Mock()
        client.generate_embedding = Mock(return_value=[0.2] * 768)
        client.generate_embeddings_batch = Mock(return_value=[[0.2] * 768] * 4)
        return client

    @pytest.fixture
    def service(self, mock_db_session, mock_embedding_service, mock_sigma_embedding_client):
        """Create SigmaMatchingService instance with mocked dependencies."""
        with patch(
            "src.services.sigma_matching_service.EmbeddingService",
            side_effect=[mock_embedding_service, mock_sigma_embedding_client],
        ):
            service = SigmaMatchingService(mock_db_session)
            service.db = mock_db_session
            return service

    @pytest.fixture
    def sample_article(self):
        """Create sample article with embedding."""
        article = Mock()
        article.id = 1
        article.title = "APT29 PowerShell Persistence"
        article.content = "Advanced threat actors using PowerShell for persistence"
        article.embedding = [0.1] * 768
        return article

    @pytest.fixture
    def sample_sigma_rule(self):
        """Create sample SIGMA rule data."""
        return {
            "id": 1,
            "rule_id": "test-rule-123",
            "title": "PowerShell Scheduled Task Creation",
            "description": "Detects PowerShell scheduled task creation",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": {"CommandLine|contains": "schtasks"}, "condition": "selection"},
            "tags": ["attack.persistence"],
            "level": "medium",
            "status": "stable",
            "file_path": "/rules/windows/process_creation/test.yml",
            "signature_sim": 0.85,
        }

    def test_match_article_to_rules_success(self, service, mock_db_session, sample_article, sample_sigma_rule):
        """Test successful article to rules matching."""
        # Mock article query
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = sample_article
        mock_db_session.query.return_value = mock_query

        # Mock database connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            (
                sample_sigma_rule["id"],
                sample_sigma_rule["rule_id"],
                sample_sigma_rule["title"],
                sample_sigma_rule["description"],
                sample_sigma_rule["logsource"],
                sample_sigma_rule["detection"],
                sample_sigma_rule["tags"],
                sample_sigma_rule["level"],
                sample_sigma_rule["status"],
                sample_sigma_rule["file_path"],
                sample_sigma_rule["signature_sim"],
            )
        ]
        mock_cursor.close = Mock()
        mock_connection.connection.cursor.return_value = mock_cursor
        mock_db_session.connection.return_value = mock_connection

        matches = service.match_article_to_rules(article_id=1, threshold=0.0, limit=10)

        assert len(matches) == 1
        assert matches[0]["sigma_rule_id"] == sample_sigma_rule["id"]
        assert matches[0]["similarity_score"] > 0

    def test_match_article_to_rules_no_article(self, service, mock_db_session):
        """Test matching when article doesn't exist."""
        # Mock article query returning None
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        matches = service.match_article_to_rules(article_id=999)

        assert len(matches) == 0

    def test_match_article_to_rules_no_embedding(self, service, mock_db_session):
        """Test matching when article has no embedding."""
        article = Mock()
        article.id = 1
        article.embedding = None

        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = article
        mock_db_session.query.return_value = mock_query

        matches = service.match_article_to_rules(article_id=1)

        assert len(matches) == 0

    def test_match_article_to_rules_threshold_filtering(
        self, service, mock_db_session, sample_article, sample_sigma_rule
    ):
        """Test similarity threshold filtering."""
        # Mock article query
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = sample_article
        mock_db_session.query.return_value = mock_query

        # Mock database connection
        mock_connection = Mock()
        mock_cursor = Mock()
        # Return rule with low similarity
        mock_cursor.fetchall.return_value = [
            (
                sample_sigma_rule["id"],
                sample_sigma_rule["rule_id"],
                sample_sigma_rule["title"],
                sample_sigma_rule["description"],
                sample_sigma_rule["logsource"],
                sample_sigma_rule["detection"],
                sample_sigma_rule["tags"],
                sample_sigma_rule["level"],
                sample_sigma_rule["status"],
                sample_sigma_rule["file_path"],
                0.1,  # Low similarity
            )
        ]
        mock_cursor.close = Mock()
        mock_connection.connection.cursor.return_value = mock_cursor
        mock_db_session.connection.return_value = mock_connection

        # Test with high threshold
        matches = service.match_article_to_rules(article_id=1, threshold=0.5, limit=10)

        # Should filter out low similarity matches
        assert len(matches) == 0

    def test_match_chunks_to_rules_success(self, service, mock_db_session, sample_sigma_rule):
        """Test successful chunk to SIGMA rules matching."""
        from src.database.models import ChunkAnalysisResultTable

        # Create mock chunks
        chunk1 = Mock(spec=ChunkAnalysisResultTable)
        chunk1.id = 1
        chunk1.article_id = 1
        chunk1.chunk_text = "PowerShell command execution"
        chunk1.hunt_score = 85.0
        chunk1.perfect_discriminators_found = []
        chunk1.lolbas_matches_found = []

        chunk2 = Mock(spec=ChunkAnalysisResultTable)
        chunk2.id = 2
        chunk2.article_id = 1
        chunk2.chunk_text = "Scheduled task creation"
        chunk2.hunt_score = 80.0
        chunk2.perfect_discriminators_found = []
        chunk2.lolbas_matches_found = []

        # Mock chunk query chain: query(Model).filter_by(...).all()
        mock_filter_by_result = Mock()
        mock_filter_by_result.all.return_value = [chunk1, chunk2]
        mock_chunk_query = Mock()
        mock_chunk_query.filter_by.return_value = mock_filter_by_result
        mock_db_session.query.return_value = mock_chunk_query

        # Mock embedding generation - synchronous method (not async)
        with patch.object(service.embedding_service, "generate_embedding", new=Mock(return_value=[0.2] * 768)):
            # Mock database execute - result should be iterable
            # The execute method returns a result object that can be iterated
            mock_row = tuple(
                [
                    sample_sigma_rule["id"],
                    sample_sigma_rule["rule_id"],
                    sample_sigma_rule["title"],
                    sample_sigma_rule["description"],
                    sample_sigma_rule["logsource"],
                    sample_sigma_rule["detection"],
                    sample_sigma_rule["tags"],
                    sample_sigma_rule["level"],
                    sample_sigma_rule["status"],
                    sample_sigma_rule["file_path"],
                    0.90,  # signature_sim - high enough to pass threshold * weight (0.0 * 0.874 = 0.0)
                ]
            )
            # Create a result object that is iterable - use a list that can be iterated
            mock_result_rows = [mock_row]

            # Mock execute to return the result - ensure service.db.execute works
            def mock_execute(query, params=None):
                # Return an object that can be iterated
                class MockResult:
                    def __iter__(self):
                        return iter(mock_result_rows)

                return MockResult()

            # Set execute on the db session that service uses
            mock_db_session.execute = Mock(side_effect=mock_execute)
            # Also ensure service.db points to mock_db_session
            service.db = mock_db_session

            # Use threshold=0.0 to ensure all matches pass
            matches = service.match_chunks_to_rules(article_id=1, threshold=0.0, limit_per_chunk=5)

            assert len(matches) > 0
            assert "chunk_id" in matches[0]
            assert "similarity" in matches[0]

    def test_match_chunks_to_rules_no_chunks(self, service, mock_db_session):
        """Test matching when article has no chunks."""

        mock_chunk_query = Mock()
        mock_chunk_query.filter_by.return_value.all.return_value = []
        mock_db_session.query.return_value = mock_chunk_query

        matches = service.match_chunks_to_rules(article_id=1)

        assert len(matches) == 0

    def test_match_chunks_to_rules_embedding_generation_failure(self, service, mock_db_session):
        """Test handling of embedding generation failure."""
        from src.database.models import ChunkAnalysisResultTable

        chunk = Mock(spec=ChunkAnalysisResultTable)
        chunk.id = 1
        chunk.article_id = 1
        chunk.chunk_text = "Test chunk"
        chunk.hunt_score = 75.0
        chunk.perfect_discriminators_found = []
        chunk.lolbas_matches_found = []

        mock_chunk_query = Mock()
        mock_chunk_query.filter_by.return_value.all.return_value = [chunk]
        mock_db_session.query.return_value = mock_chunk_query

        with patch.object(service.embedding_service, "generate_embedding", side_effect=Exception("Embedding error")):
            matches = service.match_chunks_to_rules(article_id=1)

            # Should handle error gracefully
            assert isinstance(matches, list)

    def test_similarity_weights_application(self, service):
        """Test that similarity weights are applied correctly."""
        from src.services.sigma_matching_service import SIMILARITY_WEIGHTS

        # Verify weights sum to 1.0
        total_weight = sum(SIMILARITY_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.01

        # Verify signature has highest weight
        assert SIMILARITY_WEIGHTS["signature"] > SIMILARITY_WEIGHTS["title"]
        assert SIMILARITY_WEIGHTS["signature"] > SIMILARITY_WEIGHTS["description"]

    def test_match_article_to_rules_limit(self, service, mock_db_session, sample_article, sample_sigma_rule):
        """Test limit parameter in article matching."""
        # Mock article query
        mock_query = Mock()
        mock_query.filter_by.return_value.first.return_value = sample_article
        mock_db_session.query.return_value = mock_query

        # Mock database connection with multiple results
        mock_connection = Mock()
        mock_cursor = Mock()
        # Return 5 rules
        mock_cursor.fetchall.return_value = [
            (
                sample_sigma_rule["id"] + i,
                f"{sample_sigma_rule['rule_id']}-{i}",
                f"{sample_sigma_rule['title']} {i}",
                sample_sigma_rule["description"],
                sample_sigma_rule["logsource"],
                sample_sigma_rule["detection"],
                sample_sigma_rule["tags"],
                sample_sigma_rule["level"],
                sample_sigma_rule["status"],
                sample_sigma_rule["file_path"],
                0.85 - i * 0.1,
            )
            for i in range(5)
        ]
        mock_cursor.close = Mock()
        mock_connection.connection.cursor.return_value = mock_cursor
        mock_db_session.connection.return_value = mock_connection

        matches = service.match_article_to_rules(article_id=1, threshold=0.0, limit=3)

        assert len(matches) <= 3

    def test_assess_rule_novelty_includes_filter_metadata(self, service):
        """Novelty layer passes canonical_class and logsource_key through for UI empty-state copy."""
        proposed = {
            "title": "T",
            "description": "",
            "tags": [],
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": {"CommandLine": "x"}, "condition": "selection"},
        }
        novelty_payload = {
            "novelty_label": NoveltyLabel.NOVEL,
            "novelty_score": 1.0,
            "logsource_key": "windows|process_creation",
            "canonical_class": "windows.process_creation",
            "exact_hash": "abc",
            "top_matches": [],
            "canonical_rule": {},
            "total_candidates_evaluated": 1165,
            "behavioral_matches_found": 0,
            "engine_used": "deterministic",
        }
        with patch("src.services.sigma_novelty_service.SigmaNoveltyService") as ns_cls:
            ns_cls.return_value.assess_novelty.return_value = novelty_payload
            out = service.assess_rule_novelty(proposed, threshold=0.0)

        assert out["canonical_class"] == "windows.process_creation"
        assert out["logsource_key"] == "windows|process_creation"
        assert out["total_candidates_evaluated"] == 1165
        assert out["matches"] == []

    def test_assess_rule_novelty_passes_through_no_atoms_extracted(self, service):
        """Bridge-layer guard for the fail-open-not-silent chain: assess_rule_novelty must
        propagate the `no_atoms_extracted` flag from assess_novelty so summarize_rule_novelty
        can route the unassessable rule to needs_review. Without this passthrough the flag is
        lost between the two ends that ARE unit-tested, and the routing silently regresses.
        """
        proposed = {
            "title": "T",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {}, "condition": "selection"},
        }
        atomless_payload = {
            "novelty_label": NoveltyLabel.NOVEL,
            "novelty_score": 1.0,
            "logsource_key": "windows|process_creation",
            "canonical_class": None,
            "exact_hash": None,
            "top_matches": [],
            "canonical_rule": {},
            "total_candidates_evaluated": 0,
            "behavioral_matches_found": 0,
            "engine_used": "legacy",
            "no_atoms_extracted": True,
        }
        with patch("src.services.sigma_novelty_service.SigmaNoveltyService") as ns_cls:
            ns_cls.return_value.assess_novelty.return_value = atomless_payload
            out = service.assess_rule_novelty(proposed, threshold=0.0)

        assert out.get("no_atoms_extracted") is True, "assess_rule_novelty dropped the no_atoms_extracted flag"

    def test_assess_rule_novelty_no_atoms_extracted_defaults_false(self, service):
        """When the novelty layer does not flag atom-less, the passthrough defaults to False
        (not missing), so summarize_rule_novelty's bool() read is well-defined."""
        proposed = {
            "title": "T",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {"CommandLine": "x"}, "condition": "selection"},
        }
        normal_payload = {
            "novelty_label": NoveltyLabel.NOVEL,
            "novelty_score": 1.0,
            "logsource_key": "windows|process_creation",
            "canonical_class": "windows.process_creation",
            "exact_hash": "abc",
            "top_matches": [],
            "canonical_rule": {},
            "total_candidates_evaluated": 10,
            "behavioral_matches_found": 0,
            "engine_used": "deterministic",
        }
        with patch("src.services.sigma_novelty_service.SigmaNoveltyService") as ns_cls:
            ns_cls.return_value.assess_novelty.return_value = normal_payload
            out = service.assess_rule_novelty(proposed, threshold=0.0)

        assert out.get("no_atoms_extracted") is False

    def test_assess_rule_novelty_on_failure_returns_empty_filter_metadata(self, service):
        """On failure, matching service returns null/empty filter metadata (contract for API)."""
        proposed = {
            "title": "T",
            "description": "",
            "tags": [],
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": {"CommandLine": "x"}, "condition": "selection"},
        }
        with patch("src.services.sigma_novelty_service.SigmaNoveltyService", side_effect=RuntimeError("init fail")):
            out = service.assess_rule_novelty(proposed, threshold=0.0)

        assert out["matches"] == []
        assert out.get("canonical_class") is None
        assert out.get("logsource_key") == ""


class TestHardGateScopedToFallback:
    """Spec Item 6 (P2-C) Option B (chosen per 4c measurement: canonical_class is
    de facto 1:1 with logsource_key, so the gate is dead code on the canonical_class
    path — scope it to the fallback path only).

    The gate at sigma_matching_service.py:551 drops candidates whose logsource_key
    differs from the proposed rule's. After Item 6 it must fire ONLY when Phase 1
    retrieved the candidate via the logsource_key fallback (where the gate is a
    no-op safety net) — never on the canonical_class or exact_hash paths.

    Each test mocks SigmaNoveltyService.assess_novelty to return a fixed top_matches
    list with a chosen phase1_path. We assert which matches survive the
    assess_rule_novelty gate.
    """

    @pytest.fixture
    def mock_db_session(self):
        session = Mock()
        session.query = Mock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        with patch("src.services.sigma_matching_service.EmbeddingService"):
            s = SigmaMatchingService(mock_db_session)
            s.db = mock_db_session
            return s

    @pytest.fixture
    def proposed(self):
        return {
            "title": "Proposed",
            "description": "",
            "tags": [],
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": {"CommandLine": "x"}, "condition": "selection"},
        }

    @pytest.fixture
    def proposed_logsource_key(self):
        return "windows|process_creation"

    def _make_novelty_payload(self, top_matches, proposed_logsource_key):
        return {
            "novelty_label": NoveltyLabel.NOVEL,
            "novelty_score": 1.0,
            "logsource_key": proposed_logsource_key,
            "canonical_class": "windows.process_creation",
            "exact_hash": "abc",
            "top_matches": top_matches,
            "canonical_rule": {},
            "total_candidates_evaluated": 1,
            "behavioral_matches_found": 1,
            "engine_used": "deterministic",
        }

    def _make_match(self, rule_id, phase1_path, similarity=0.5):
        """Minimal top_matches entry shape that assess_rule_novelty reads."""
        return {
            "rule_id": rule_id,
            "atom_jaccard": 0.5,
            "logic_shape_similarity": 0.65,
            "similarity": similarity,
            "service_penalty": 0.0,
            "filter_penalty": 0.0,
            "weighted_before_penalties": similarity,
            "similarity_engine": "deterministic",
            "atom_details": None,
            "shared_atoms": [],
            "added_atoms": [],
            "removed_atoms": [],
            "filter_differences": [],
            "phase1_path": phase1_path,
        }

    def _make_db_rule(self, rule_id, logsource_key):
        """Mock SigmaRuleTable row returned by the matching service's per-match lookup."""
        rule = Mock()
        rule.id = 1
        rule.rule_id = rule_id
        rule.title = "t"
        rule.description = "d"
        rule.logsource = {"category": "process_creation", "product": "windows"}
        rule.detection = {"selection": {}, "condition": "selection"}
        rule.tags = []
        rule.level = "low"
        rule.status = "stable"
        rule.file_path = "rules/x.yml"
        rule.logsource_key = logsource_key
        return rule

    def _run_compare(self, mock_db_session, service_fixture, proposed, top_matches, proposed_lsk, rule_lsk):
        """Helper: wire up the mocks, set the candidate rule's logsource_key, run compare.

        Spec Item 10b: the matching loop now batches per-match rule lookups into a single
        .filter(rule_id.in_(...)).all() instead of per-match .first(). The mock stubs both
        forms so the test works whether the implementation is the batched or the legacy form.
        """
        rule = self._make_db_rule("r1", rule_lsk)
        query_mock = mock_db_session.query.return_value
        filter_mock = query_mock.filter.return_value
        filter_mock.first.return_value = rule  # legacy form (defensive)
        filter_mock.all.return_value = [rule]  # batched form (Spec Item 10b)

        novelty_payload = self._make_novelty_payload(top_matches, proposed_lsk)
        with patch("src.services.sigma_novelty_service.SigmaNoveltyService") as ns_cls:
            ns_cls.return_value.assess_novelty.return_value = novelty_payload
            return service_fixture.assess_rule_novelty(proposed, threshold=0.0)

    def test_canonical_class_path_survives_logsource_mismatch(
        self, service, mock_db_session, proposed, proposed_logsource_key
    ):
        """phase1_path='canonical_class' + mismatching logsource_key → match SURVIVES (the gate skips this path)."""
        match = self._make_match("r1", phase1_path="canonical_class")
        out = self._run_compare(
            mock_db_session,
            service,
            proposed,
            [match],
            proposed_lsk=proposed_logsource_key,
            rule_lsk="linux|process_creation",  # MISMATCH
        )
        assert len(out["matches"]) == 1, (
            "canonical_class candidates must NOT be dropped by the gate; "
            "canonical_class filter is authoritative on that path."
        )
        assert out["matches"][0]["rule_id"] == "r1"

    def test_logsource_fallback_path_drops_mismatch(self, service, mock_db_session, proposed, proposed_logsource_key):
        """phase1_path='logsource_fallback' + mismatching logsource_key → match DROPPED (gate fires)."""
        match = self._make_match("r1", phase1_path="logsource_fallback")
        out = self._run_compare(
            mock_db_session,
            service,
            proposed,
            [match],
            proposed_lsk=proposed_logsource_key,
            rule_lsk="linux|process_creation",  # MISMATCH
        )
        assert out["matches"] == [], (
            "On the fallback path the gate must still drop logsource_key mismatches "
            "as a defensive safety net (Phase 1's SQL was supposed to enforce match, "
            "but if a mismatch survives we don't trust the candidate)."
        )

    def test_logsource_fallback_path_keeps_matching_logsource(
        self, service, mock_db_session, proposed, proposed_logsource_key
    ):
        """phase1_path='logsource_fallback' + matching logsource_key → match SURVIVES."""
        match = self._make_match("r1", phase1_path="logsource_fallback")
        out = self._run_compare(
            mock_db_session,
            service,
            proposed,
            [match],
            proposed_lsk=proposed_logsource_key,
            rule_lsk=proposed_logsource_key,  # MATCH
        )
        assert len(out["matches"]) == 1
        assert out["matches"][0]["rule_id"] == "r1"

    def test_exact_hash_path_survives_logsource_mismatch(
        self, service, mock_db_session, proposed, proposed_logsource_key
    ):
        """phase1_path='exact_hash' (rule hash already proved identity) → match SURVIVES regardless of logsource."""
        match = self._make_match("r1", phase1_path="exact_hash")
        out = self._run_compare(
            mock_db_session,
            service,
            proposed,
            [match],
            proposed_lsk=proposed_logsource_key,
            rule_lsk="linux|process_creation",  # MISMATCH (shouldn't even be possible in practice)
        )
        assert len(out["matches"]) == 1, (
            "exact_hash matches must not be gated — hash-based identity supersedes logsource_key surface check."
        )

    def test_missing_phase1_path_falls_back_to_legacy_gate_behavior(
        self, service, mock_db_session, proposed, proposed_logsource_key
    ):
        """Backward compat: match without phase1_path field (older cached data) → gate fires conservatively."""
        match = self._make_match("r1", phase1_path="canonical_class")
        del match["phase1_path"]  # simulate older payload that pre-dates Item 6
        out = self._run_compare(
            mock_db_session,
            service,
            proposed,
            [match],
            proposed_lsk=proposed_logsource_key,
            rule_lsk="linux|process_creation",  # MISMATCH
        )
        assert out["matches"] == [], (
            "When phase1_path is missing, the gate must default to the legacy "
            "(always-enforce) behavior so older novelty payloads stay safe."
        )

    def test_batched_rule_lookup_no_n_plus_1(self, service, mock_db_session, proposed, proposed_logsource_key):
        """Spec Item 10b: per-match rule lookup must use ONE batched .all() query
        (.filter(rule_id.in_(...)).all()), not N per-match .first() queries.
        """
        # 10 matches → naive impl would do 10 .first() calls + 0 .all().
        # Batched impl should do 0 .first() + exactly 1 .all().
        matches_in = [self._make_match(f"r{i}", phase1_path="canonical_class") for i in range(10)]

        rules = [self._make_db_rule(f"r{i}", proposed_logsource_key) for i in range(10)]
        query_mock = mock_db_session.query.return_value
        filter_mock = query_mock.filter.return_value
        filter_mock.first.return_value = rules[0]  # legacy fallback
        filter_mock.all.return_value = rules  # batched form

        novelty_payload = self._make_novelty_payload(matches_in, proposed_logsource_key)
        with patch("src.services.sigma_novelty_service.SigmaNoveltyService") as ns_cls:
            ns_cls.return_value.assess_novelty.return_value = novelty_payload
            out = service.assess_rule_novelty(proposed, threshold=0.0)

        assert len(out["matches"]) == 10, "All 10 matches should be returned"
        # The batched call: .all() invoked exactly once on the per-match-lookup chain.
        # .first() should NOT be called for per-match lookup in the batched path.
        assert filter_mock.all.call_count == 1, (
            f"Expected exactly one batched .all() call; got {filter_mock.all.call_count}. N+1 query was reintroduced."
        )
