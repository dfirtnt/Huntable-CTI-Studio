"""
Tests for the rollup module.
"""

import pytest
from src.core.rollup import rollup_article, ArticleQualityRollup


class TestRollup:
    """Test cases for the ArticleQualityRollup class."""
    
    def test_rollup_single_excellent_chunk(self):
        """Test rollup with one excellent chunk."""
        chunks = [
            {
                'chunk_id': 1,
                'text': 'This chunk contains excellent threat hunting content.',
                'score': 0.8,
                'excellent_prob': 0.9
            }
        ]
        
        result = rollup_article(1, chunks)
        
        assert result['article_id'] == 1
        assert result['excellent'] == True
        assert result['excellent_prob'] == 0.9
        assert result['rollup_score'] > 0.0
    
    def test_rollup_no_excellent_chunks(self):
        """Test rollup with no excellent chunks."""
        chunks = [
            {
                'chunk_id': 1,
                'text': 'This chunk has low quality content.',
                'score': 0.2,
                'excellent_prob': 0.1
            },
            {
                'chunk_id': 2,
                'text': 'Another low quality chunk.',
                'score': 0.3,
                'excellent_prob': 0.2
            }
        ]
        
        result = rollup_article(1, chunks)
        
        assert result['article_id'] == 1
        assert result['excellent'] == False
        assert result['excellent_prob'] == 0.2  # Max probability
        assert result['rollup_score'] > 0.0
    
    def test_rollup_mixed_quality_chunks(self):
        """Test rollup with mixed quality chunks."""
        chunks = [
            {
                'chunk_id': 1,
                'text': 'Low quality chunk.',
                'score': 0.2,
                'excellent_prob': 0.1
            },
            {
                'chunk_id': 2,
                'text': 'Excellent chunk with technical details.',
                'score': 0.8,
                'excellent_prob': 0.9
            },
            {
                'chunk_id': 3,
                'text': 'Medium quality chunk.',
                'score': 0.5,
                'excellent_prob': 0.4
            }
        ]
        
        result = rollup_article(1, chunks)
        
        assert result['article_id'] == 1
        assert result['excellent'] == True  # Should be excellent due to chunk 2
        assert result['excellent_prob'] == 0.9  # Max probability
        assert result['rollup_score'] > 0.0
    
    def test_rollup_empty_chunks(self):
        """Test rollup with empty chunks list."""
        result = rollup_article(1, [])
        
        assert result['article_id'] == 1
        assert result['excellent'] == False
        assert result['excellent_prob'] == 0.0
        assert result['rollup_score'] == 0.0
        assert result['rollup']['total_chunks'] == 0
    
    def test_rollup_max_top3_method(self):
        """Test rollup using max_top3 method."""
        rollup_processor = ArticleQualityRollup(method="max_top3")
        
        chunks = [
            {'chunk_id': 1, 'text': 'Chunk 1', 'score': 0.3, 'excellent_prob': 0.2},
            {'chunk_id': 2, 'text': 'Chunk 2', 'score': 0.8, 'excellent_prob': 0.7},
            {'chunk_id': 3, 'text': 'Chunk 3', 'score': 0.6, 'excellent_prob': 0.5},
            {'chunk_id': 4, 'text': 'Chunk 4', 'score': 0.9, 'excellent_prob': 0.8},
            {'chunk_id': 5, 'text': 'Chunk 5', 'score': 0.4, 'excellent_prob': 0.3}
        ]
        
        result = rollup_processor.rollup_article(1, chunks)
        
        # Should use max of top 3 scores (0.9, 0.8, 0.6)
        assert result['rollup_score'] == 0.9
        assert result['rollup']['method'] == 'max_top3'
    
    def test_rollup_weighted_avg_method(self):
        """Test rollup using weighted_avg method."""
        rollup_processor = ArticleQualityRollup(method="weighted_avg")
        
        chunks = [
            {'chunk_id': 1, 'text': 'Chunk 1', 'score': 0.5, 'excellent_prob': 0.4},
            {'chunk_id': 2, 'text': 'Chunk 2', 'score': 0.7, 'excellent_prob': 0.6}
        ]
        
        result = rollup_processor.rollup_article(1, chunks)
        
        # Should calculate weighted average
        expected_score = (0.5 * 0.6 + 0.7 * 0.6 + 0.4 * 0.4 + 0.6 * 0.4) / 2.0
        assert abs(result['rollup_score'] - expected_score) < 0.1
        assert result['rollup']['method'] == 'weighted_avg'
    
    def test_rollup_any_excellent_method(self):
        """Test rollup using any_excellent method."""
        rollup_processor = ArticleQualityRollup(method="any_excellent")
        
        # Test with no excellent chunks
        chunks_no_excellent = [
            {'chunk_id': 1, 'text': 'Chunk 1', 'score': 0.3, 'excellent_prob': 0.2},
            {'chunk_id': 2, 'text': 'Chunk 2', 'score': 0.4, 'excellent_prob': 0.3}
        ]
        
        result = rollup_processor.rollup_article(1, chunks_no_excellent)
        assert result['rollup_score'] == 0.4  # Max prefilter score
        
        # Test with excellent chunk
        chunks_with_excellent = [
            {'chunk_id': 1, 'text': 'Chunk 1', 'score': 0.3, 'excellent_prob': 0.6},
            {'chunk_id': 2, 'text': 'Chunk 2', 'score': 0.4, 'excellent_prob': 0.3}
        ]
        
        result = rollup_processor.rollup_article(1, chunks_with_excellent)
        assert result['rollup_score'] == 1.0  # Should be 1.0 due to excellent chunk
        assert result['rollup']['method'] == 'any_excellent'
    
    def test_rollup_metadata(self):
        """Test that rollup metadata is correctly populated."""
        chunks = [
            {
                'chunk_id': 1,
                'text': 'Excellent chunk with technical content.',
                'score': 0.8,
                'excellent_prob': 0.9
            },
            {
                'chunk_id': 2,
                'text': 'Another good chunk.',
                'score': 0.6,
                'excellent_prob': 0.5
            }
        ]
        
        result = rollup_article(1, chunks)
        
        assert 'rollup' in result
        rollup_meta = result['rollup']
        
        assert rollup_meta['total_chunks'] == 2
        assert rollup_meta['excellent_chunks'] == 1
        assert len(rollup_meta['excellent_chunk_details']) == 1
        assert 'rollup_date' in rollup_meta
        assert 'prefilter_score_stats' in rollup_meta
        assert 'excellent_prob_stats' in rollup_meta
    
    def test_rollup_excellent_chunk_details(self):
        """Test that excellent chunk details are captured."""
        chunks = [
            {
                'chunk_id': 1,
                'text': 'This is an excellent chunk with detailed technical information about the attack.',
                'score': 0.8,
                'excellent_prob': 0.9
            }
        ]
        
        result = rollup_article(1, chunks)
        
        excellent_details = result['rollup']['excellent_chunk_details']
        assert len(excellent_details) == 1
        
        detail = excellent_details[0]
        assert detail['chunk_id'] == 1
        assert detail['score'] == 0.8
        assert detail['excellent_prob'] == 0.9
        assert 'text_preview' in detail
        assert len(detail['text_preview']) > 0
    
    def test_rollup_statistics(self):
        """Test that statistics are correctly calculated."""
        chunks = [
            {'chunk_id': 1, 'text': 'Chunk 1', 'score': 0.3, 'excellent_prob': 0.2},
            {'chunk_id': 2, 'text': 'Chunk 2', 'score': 0.7, 'excellent_prob': 0.6},
            {'chunk_id': 3, 'text': 'Chunk 3', 'score': 0.5, 'excellent_prob': 0.4}
        ]
        
        result = rollup_article(1, chunks)
        
        # Check prefilter score stats
        score_stats = result['rollup']['prefilter_score_stats']
        assert score_stats['count'] == 3
        assert score_stats['min'] == 0.3
        assert score_stats['max'] == 0.7
        assert score_stats['mean'] == pytest.approx(0.5, rel=0.1)
        
        # Check excellent probability stats
        prob_stats = result['rollup']['excellent_prob_stats']
        assert prob_stats['count'] == 3
        assert prob_stats['min'] == 0.2
        assert prob_stats['max'] == 0.6
        assert prob_stats['mean'] == pytest.approx(0.4, rel=0.1)
    
    def test_rollup_multiple_articles(self):
        """Test rolling up multiple articles."""
        rollup_processor = ArticleQualityRollup()
        
        articles_data = [
            {
                'article_id': 1,
                'chunks': [
                    {'chunk_id': 1, 'text': 'Chunk 1', 'score': 0.8, 'excellent_prob': 0.9}
                ]
            },
            {
                'article_id': 2,
                'chunks': [
                    {'chunk_id': 2, 'text': 'Chunk 2', 'score': 0.3, 'excellent_prob': 0.2}
                ]
            }
        ]
        
        results = rollup_processor.rollup_multiple_articles(articles_data)
        
        assert len(results) == 2
        assert results[0]['excellent'] == True
        assert results[1]['excellent'] == False
    
    def test_rollup_summary(self):
        """Test rollup summary statistics."""
        rollup_processor = ArticleQualityRollup()
        
        rollup_results = [
            {'article_id': 1, 'excellent': True, 'excellent_prob': 0.9, 'rollup_score': 0.8},
            {'article_id': 2, 'excellent': False, 'excellent_prob': 0.3, 'rollup_score': 0.4},
            {'article_id': 3, 'excellent': True, 'excellent_prob': 0.8, 'rollup_score': 0.7}
        ]
        
        summary = rollup_processor.get_rollup_summary(rollup_results)
        
        assert summary['total_articles'] == 3
        assert summary['excellent_articles'] == 2
        assert summary['excellent_percentage'] == pytest.approx(66.67, rel=0.1)
        assert summary['method_used'] == 'max_top3'
        assert 'rollup_score_stats' in summary
        assert 'excellent_prob_stats' in summary


if __name__ == "__main__":
    pytest.main([__file__])
