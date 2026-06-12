"""Tests for SigmaSyncService.index_embeddings() — embedding phase only.

These lock the contract of the chunked, per-chunk-commit rewrite. The original
implementation loaded every rule up front and committed once at the very end, so
an OOM/interrupt mid-run rolled back ALL completed work — 0 rows persisted on a
3.7k-rule corpus despite visible progress. The rewrite:

  * fetches PKs first, then loads/encodes/commits ONE chunk at a time
    (so completed chunks survive an interrupt),
  * skips rules that already have embeddings unless force_reindex,
  * honors SIGMA_EMBED_RULES_PER_CHUNK to bound peak memory,
  * counts encoder failures as errors without losing prior chunks or raising.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.database.models import SigmaRuleTable
from src.services.sigma_sync_service import SigmaSyncService

pytestmark = pytest.mark.unit


def _make_rule(pk: int, *, has_embedding: bool = False):
    """A rule double with real attribute values so the production text-builders run."""
    rule = MagicMock()
    rule.id = pk
    rule.rule_id = f"rule-{pk:04d}"
    rule.title = f"Test Rule {pk}"
    rule.description = "Detects something suspicious"
    rule.tags = ["attack.execution"]
    rule.logsource = {"category": "process_creation", "product": "windows"}
    rule.detection = {"selection": {"CommandLine|contains": "test"}, "condition": "selection"}
    rule.embedding = [0.0] * 768 if has_embedding else None
    rule.logsource_embedding = None
    rule.embedding_model = None
    rule.embedded_at = None
    return rule


class _PkQuery:
    """query(SigmaRuleTable.id) — the up-front PK pre-scan. Honors a chained
    `.filter(embedding.is_(None))` (added when not force-reindexing) by tracking a
    NULL-only flag, then returns [(pk,)] tuples like SQLAlchemy does for a column query."""

    def __init__(self, rules):
        self._rules = rules
        self._only_null = False

    def filter(self, *args, **kwargs):
        # The first filter on the PK query (when present) is embedding.is_(None).
        self._only_null = True
        return self

    def all(self):
        rows = [r for r in self._rules if r.embedding is None] if self._only_null else self._rules
        return [(r.id,) for r in rows]


class _ChunkQuery:
    """query(SigmaRuleTable).filter(id.in_(pks)) — returns rule objects by PK.

    The session hands us a dict id->rule so we don't have to parse the SQLAlchemy
    in_() clause (its column attribute is read-only and can't be monkeypatched).
    We capture the PKs from the filter argument's compiled value instead.
    """

    def __init__(self, by_id, capture_pks):
        self._by_id = by_id
        self._capture_pks = capture_pks
        self._pks = None

    def filter(self, clause, *rest):
        # Extract the literal PK list from the `id.in_([...])` clause.
        pks = _extract_in_values(clause)
        self._pks = pks if pks is not None else list(self._by_id.keys())
        self._capture_pks(self._pks)
        return self

    def all(self):
        pks = self._pks if self._pks is not None else list(self._by_id.keys())
        return [self._by_id[p] for p in pks if p in self._by_id]


def _extract_in_values(clause):
    """Pull the literal values out of a SQLAlchemy `col.in_([...])` BinaryExpression.
    Returns a list of PKs, or None if it can't be read (test falls back to all)."""
    try:
        val = clause.right.value  # expanding BindParameter holding the value list
        if val is not None:
            return list(val)
    except Exception:
        pass
    return None


class _FakeSession:
    """Routes query() to the right fake query and records commit() calls.

    query(SigmaRuleTable.id) -> _PkQuery (entity is an InstrumentedAttribute);
    query(SigmaRuleTable)    -> _ChunkQuery (entity is the mapped class).
    """

    def __init__(self, rules):
        self._rules = rules
        self._by_id = {r.id: r for r in rules}
        self.commit_count = 0
        self.expunge_all_count = 0
        self.requested_chunk_pks = []
        # Snapshot of how many rules carried an embedding at each commit, in order.
        # Lets a test prove earlier chunks were persisted BEFORE a later chunk failed.
        self.embedded_at_commit = []

    def query(self, entity, *rest):
        if entity is SigmaRuleTable:
            return _ChunkQuery(self._by_id, self.requested_chunk_pks.append)
        return _PkQuery(self._rules)

    def commit(self):
        self.commit_count += 1
        self.embedded_at_commit.append(sum(1 for r in self._rules if r.embedding is not None))

    def expunge_all(self):
        self.expunge_all_count += 1


@pytest.fixture
def sync_service(tmp_path):
    return SigmaSyncService(repo_path=str(tmp_path))


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.no_autoflush = MagicMock()
    session.no_autoflush.__enter__ = MagicMock(return_value=None)
    session.no_autoflush.__exit__ = MagicMock(return_value=False)
    return session


def _emb_returning(n_rules):
    """A batch-embedder mock that returns 2 vectors per rule (whole-rule + signature)."""
    inst = MagicMock()

    def _batch(texts, batch_size=32):
        return [[0.1] * 768 for _ in range(len(texts))]

    inst.generate_embeddings_batch.side_effect = _batch
    return inst


class TestIndexEmbeddings:
    @patch("src.services.embedding_service.EmbeddingService")
    def test_generates_embeddings_for_rules_without_them(self, mock_emb_cls, sync_service, mock_db_session):
        """Should generate embeddings for rules where embedding IS NULL."""
        mock_rule = MagicMock()
        mock_rule.rule_id = "test-rule-1"
        mock_rule.embedding = None
        mock_rule.title = "Test Rule"
        mock_rule.description = "Test description"
        mock_rule.tags = ["attack.execution"]
        mock_rule.logsource = {"category": "process_creation", "product": "windows"}
        mock_rule.detection = {"selection": {"CommandLine|contains": "test"}, "condition": "selection"}

        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_rule]

        mock_emb_instance = MagicMock()
        # Batched path: 2 texts per rule (whole-rule + combined signature). The former
        # per-section vectors (title/description/tags + duplicate detection_*) were dropped
        # 2026-06-01; only `embedding` and `logsource_embedding` are scored downstream.
        mock_emb_instance.generate_embeddings_batch.return_value = [[0.1] * 768] * 2
        mock_emb_cls.return_value = mock_emb_instance

        result = sync_service.index_embeddings(mock_db_session)

        assert result["embeddings_indexed"] >= 1
        assert mock_emb_instance.generate_embeddings_batch.called
        # Contract: exactly 2 texts encoded per rule (1 rule here).
        flat_texts = mock_emb_instance.generate_embeddings_batch.call_args.args[0]
        assert len(flat_texts) == 2, f"expected 2 texts/rule, got {len(flat_texts)}"
        # Only the two live vectors are assigned; dropped columns are not set.
        assert mock_rule.embedding is not None
        assert mock_rule.logsource_embedding is not None

    @patch("src.services.embedding_service.EmbeddingService")
    def test_result_has_expected_keys(self, mock_emb_cls, sync_service, mock_db_session):
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        mock_emb_cls.return_value = MagicMock()

        result = sync_service.index_embeddings(mock_db_session)

        assert "embeddings_indexed" in result
        assert "skipped" in result
        assert "errors" in result

    @patch("src.services.embedding_service.EmbeddingService")
    def test_skips_rules_with_existing_embeddings(self, mock_emb_cls, sync_service, mock_db_session):
        """When force_reindex=False, rules with embeddings should be skipped."""
        mock_db_session.query.return_value.filter.return_value.all.return_value = []
        mock_emb_cls.return_value = MagicMock()

        result = sync_service.index_embeddings(mock_db_session, force_reindex=False)
        assert result["embeddings_indexed"] == 0

    def test_handles_embedding_service_failure_gracefully(self, sync_service, mock_db_session):
        """If EmbeddingService cannot load (when we need it), return error result instead of raising."""
        mock_rule = MagicMock()
        mock_rule.rule_id = "test-rule-1"
        mock_rule.title = "Test"
        mock_rule.description = "Desc"
        mock_rule.tags = []
        mock_rule.logsource = {}
        mock_rule.detection = {}
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_rule]

        with patch(
            "src.services.embedding_service.EmbeddingService",
            side_effect=RuntimeError("Model not available"),
        ):
            result = sync_service.index_embeddings(mock_db_session)

        assert result["embeddings_indexed"] == 0
        assert result["errors"] > 0 or "error" in result


class TestChunkedCommitContract:
    """Risk-based tests for the per-chunk-commit rewrite (the OOM-durability fix)."""

    @patch("src.services.embedding_service.EmbeddingService")
    def test_commits_once_per_chunk_not_once_total(self, mock_emb_cls, sync_service, monkeypatch):
        """Regression: the original code committed once at the end, so an interrupt
        lost everything. The fix must commit after EACH chunk. With 5 rules and a
        chunk size of 2, that's 3 chunks → at least 3 commits (not 1)."""
        monkeypatch.setenv("SIGMA_EMBED_RULES_PER_CHUNK", "2")
        mock_emb_cls.return_value = _emb_returning(5)

        rules = [_make_rule(i) for i in range(5)]
        session = _FakeSession(rules)

        result = sync_service.index_embeddings(session, force_reindex=True)

        assert result["embeddings_indexed"] == 5
        assert result["errors"] == 0
        # 5 rules / chunk size 2 => 3 chunks => 3 commits.
        assert session.commit_count == 3, f"expected 3 per-chunk commits, got {session.commit_count}"
        # Every rule got its two live vectors assigned.
        assert all(r.embedding is not None for r in rules)
        assert all(r.logsource_embedding is not None for r in rules)

    @patch("src.services.embedding_service.EmbeddingService")
    def test_midrun_encoder_failure_preserves_prior_chunks(self, mock_emb_cls, sync_service, monkeypatch):
        """If the encoder fails on a later chunk, earlier chunks must already be
        committed and counted — no exception propagates, work isn't rolled back.
        This is the exact durability property the OOM exposed."""
        monkeypatch.setenv("SIGMA_EMBED_RULES_PER_CHUNK", "2")

        inst = MagicMock()
        calls = {"n": 0}

        def _batch(texts, batch_size=32):
            calls["n"] += 1
            if calls["n"] == 2:  # fail on the second chunk's encode
                raise RuntimeError("simulated OOM-ish encoder failure")
            return [[0.1] * 768 for _ in range(len(texts))]

        inst.generate_embeddings_batch.side_effect = _batch
        mock_emb_cls.return_value = inst

        rules = [_make_rule(i) for i in range(6)]  # 3 chunks of 2
        session = _FakeSession(rules)

        # Must NOT raise.
        result = sync_service.index_embeddings(session, force_reindex=True)

        # Chunk 1 (2 rules) + chunk 3 (2 rules) succeed; chunk 2 (2 rules) errors.
        assert result["embeddings_indexed"] == 4
        assert result["errors"] == 2
        # The failed chunk skips its commit (nothing to persist), but the surrounding
        # chunks each commit — so the 4 good rows are durable, not rolled back.
        assert session.commit_count == 2
        # The decisive regression guard: chunk 1's 2 rows were already committed at the
        # FIRST commit, i.e. before chunk 2's encoder blew up. Under the old "commit once
        # at the very end" code this list would be empty (everything lost on interrupt).
        assert session.embedded_at_commit[0] == 2
        assert session.embedded_at_commit[-1] == 4

    @patch("src.services.embedding_service.EmbeddingService")
    def test_chunk_size_env_override_controls_chunking(self, mock_emb_cls, sync_service, monkeypatch):
        """SIGMA_EMBED_RULES_PER_CHUNK changes the number of chunks (commits)."""
        monkeypatch.setenv("SIGMA_EMBED_RULES_PER_CHUNK", "4")
        mock_emb_cls.return_value = _emb_returning(8)

        rules = [_make_rule(i) for i in range(8)]
        session = _FakeSession(rules)

        result = sync_service.index_embeddings(session, force_reindex=True)

        assert result["embeddings_indexed"] == 8
        # 8 rules / chunk size 4 => 2 chunks => 2 commits.
        assert session.commit_count == 2

    @patch("src.services.embedding_service.EmbeddingService")
    def test_invalid_env_override_falls_back_to_default(self, mock_emb_cls, sync_service, monkeypatch):
        """A garbage SIGMA_EMBED_RULES_PER_CHUNK must not crash; falls back to the
        default chunk size (so a few rules complete in a single chunk)."""
        monkeypatch.setenv("SIGMA_EMBED_RULES_PER_CHUNK", "not-a-number")
        mock_emb_cls.return_value = _emb_returning(3)

        rules = [_make_rule(i) for i in range(3)]
        session = _FakeSession(rules)

        result = sync_service.index_embeddings(session, force_reindex=True)

        assert result["embeddings_indexed"] == 3
        # 3 rules well under the default chunk size => one chunk => one commit.
        assert session.commit_count == 1

    @patch("src.services.embedding_service.EmbeddingService")
    def test_resume_processes_only_unembedded_rules(self, mock_emb_cls, sync_service, monkeypatch):
        """force_reindex=False (the resume/setup path) must skip rules that already
        have an embedding and only process the NULL ones — this is what makes a
        re-run after an interrupt finish the remaining corpus."""
        mock_emb_cls.return_value = _emb_returning(4)

        # 2 already embedded, 2 pending.
        rules = [
            _make_rule(0, has_embedding=True),
            _make_rule(1, has_embedding=False),
            _make_rule(2, has_embedding=True),
            _make_rule(3, has_embedding=False),
        ]
        session = _FakeSession(rules)

        result = sync_service.index_embeddings(session, force_reindex=False)

        assert result["embeddings_indexed"] == 2, "should embed only the 2 NULL rules"
        # The pending ones got vectors; the pre-embedded ones are untouched here.
        assert rules[1].embedding is not None and rules[1].embedding != [0.0] * 768
        assert rules[3].embedding is not None and rules[3].embedding != [0.0] * 768
