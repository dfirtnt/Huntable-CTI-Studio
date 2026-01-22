"""Tests for SIGMA matching service functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List

from src.services.sigma_matching_service import SigmaMatchingService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaMatchingService:
    """Test SigmaMatchingService functionality."""

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
        service.generate_embedding = AsyncMock(return_value=[0.1] * 768)
        service.generate_embeddings_batch = AsyncMock(return_value=[[0.1] * 768] * 4)
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
        with patch('src.services.sigma_matching_service.EmbeddingService', return_value=mock_embedding_service), \
             patch('src.services.sigma_matching_service.LMStudioEmbeddingClient', return_value=mock_sigma_embedding_client):
            service = SigmaMatchingService(mock_db_session)
            service.db = mock_db_session  # Ensure db is set correctly
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
            'id': 1,
            'rule_id': 'test-rule-123',
            'title': 'PowerShell Scheduled Task Creation',
            'description': 'Detects PowerShell scheduled task creation',
            'logsource': {'category': 'process_creation', 'product': 'windows'},
            'detection': {'selection': {'CommandLine|contains': 'schtasks'}, 'condition': 'selection'},
            'tags': ['attack.persistence'],
            'level': 'medium',
            'status': 'stable',
            'file_path': '/rules/windows/process_creation/test.yml',
            'signature_sim': 0.85
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
                sample_sigma_rule['id'],
                sample_sigma_rule['rule_id'],
                sample_sigma_rule['title'],
                sample_sigma_rule['description'],
                sample_sigma_rule['logsource'],
                sample_sigma_rule['detection'],
                sample_sigma_rule['tags'],
                sample_sigma_rule['level'],
                sample_sigma_rule['status'],
                sample_sigma_rule['file_path'],
                sample_sigma_rule['signature_sim']
            )
        ]
        mock_cursor.close = Mock()
        mock_connection.connection.cursor.return_value = mock_cursor
        mock_db_session.connection.return_value = mock_connection
        
        matches = service.match_article_to_rules(article_id=1, threshold=0.0, limit=10)
        
        assert len(matches) == 1
        assert matches[0]['sigma_rule_id'] == sample_sigma_rule['id']
        assert matches[0]['similarity_score'] > 0

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

    def test_match_article_to_rules_threshold_filtering(self, service, mock_db_session, sample_article, sample_sigma_rule):
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
                sample_sigma_rule['id'],
                sample_sigma_rule['rule_id'],
                sample_sigma_rule['title'],
                sample_sigma_rule['description'],
                sample_sigma_rule['logsource'],
                sample_sigma_rule['detection'],
                sample_sigma_rule['tags'],
                sample_sigma_rule['level'],
                sample_sigma_rule['status'],
                sample_sigma_rule['file_path'],
                0.1  # Low similarity
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
        chunk1.chunk_text = 'PowerShell command execution'
        chunk1.hunt_score = 85.0
        chunk1.perfect_discriminators_found = []
        chunk1.lolbas_matches_found = []
        
        chunk2 = Mock(spec=ChunkAnalysisResultTable)
        chunk2.id = 2
        chunk2.article_id = 1
        chunk2.chunk_text = 'Scheduled task creation'
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
        with patch.object(service.embedding_service, 'generate_embedding', new=Mock(return_value=[0.2] * 768)) as mock_embed:
            
            # Mock database execute - result should be iterable
            # The execute method returns a result object that can be iterated
            mock_row = tuple([
                sample_sigma_rule['id'],
                sample_sigma_rule['rule_id'],
                sample_sigma_rule['title'],
                sample_sigma_rule['description'],
                sample_sigma_rule['logsource'],
                sample_sigma_rule['detection'],
                sample_sigma_rule['tags'],
                sample_sigma_rule['level'],
                sample_sigma_rule['status'],
                sample_sigma_rule['file_path'],
                0.90  # signature_sim - high enough to pass threshold * weight (0.0 * 0.874 = 0.0)
            ])
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
            assert 'chunk_id' in matches[0]
            assert 'similarity' in matches[0]

    def test_match_chunks_to_rules_no_chunks(self, service, mock_db_session):
        """Test matching when article has no chunks."""
        from src.database.models import ChunkAnalysisResultTable
        
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
        chunk.chunk_text = 'Test chunk'
        chunk.hunt_score = 75.0
        chunk.perfect_discriminators_found = []
        chunk.lolbas_matches_found = []
        
        mock_chunk_query = Mock()
        mock_chunk_query.filter_by.return_value.all.return_value = [chunk]
        mock_db_session.query.return_value = mock_chunk_query
        
        with patch.object(service.embedding_service, 'generate_embedding', side_effect=Exception("Embedding error")):
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
        assert SIMILARITY_WEIGHTS['signature'] > SIMILARITY_WEIGHTS['title']
        assert SIMILARITY_WEIGHTS['signature'] > SIMILARITY_WEIGHTS['description']

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
                sample_sigma_rule['id'] + i,
                f"{sample_sigma_rule['rule_id']}-{i}",
                f"{sample_sigma_rule['title']} {i}",
                sample_sigma_rule['description'],
                sample_sigma_rule['logsource'],
                sample_sigma_rule['detection'],
                sample_sigma_rule['tags'],
                sample_sigma_rule['level'],
                sample_sigma_rule['status'],
                sample_sigma_rule['file_path'],
                0.85 - i * 0.1
            ) for i in range(5)
        ]
        mock_cursor.close = Mock()
        mock_connection.connection.cursor.return_value = mock_cursor
        mock_db_session.connection.return_value = mock_connection
        
        matches = service.match_article_to_rules(article_id=1, threshold=0.0, limit=3)
        
        assert len(matches) <= 3
