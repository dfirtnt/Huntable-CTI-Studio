"""
Tests for the boolean search parser functionality.
"""

import pytest
from src.utils.search_parser import BooleanSearchParser, parse_boolean_search, SearchTerm


class TestBooleanSearchParser:
    """Test cases for BooleanSearchParser class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.parser = BooleanSearchParser()
        
        # Sample articles for testing
        self.sample_articles = [
            {
                'id': 1,
                'title': 'Ransomware Attack on Critical Infrastructure',
                'content': 'A sophisticated ransomware attack targeted critical infrastructure systems.'
            },
            {
                'id': 2,
                'title': 'Malware Analysis Report',
                'content': 'Analysis of new malware variants including trojans and viruses.'
            },
            {
                'id': 3,
                'title': 'APT Threat Intelligence',
                'content': 'Advanced Persistent Threat actors targeting government systems.'
            },
            {
                'id': 4,
                'title': 'Basic Security Guidelines',
                'content': 'Basic security practices for organizations.'
            }
        ]
    
    def test_parse_simple_query(self):
        """Test parsing simple search terms."""
        terms = self.parser.parse_query('malware')
        assert len(terms) == 1
        assert terms[0].term == 'malware'
        assert terms[0].operator == 'DEFAULT'
    
    def test_parse_and_query(self):
        """Test parsing AND queries."""
        terms = self.parser.parse_query('malware AND ransomware')
        assert len(terms) == 2
        assert terms[0].term == 'malware'
        assert terms[0].operator == 'DEFAULT'
        assert terms[1].term == 'ransomware'
        assert terms[1].operator == 'AND'
    
    def test_parse_or_query(self):
        """Test parsing OR queries."""
        terms = self.parser.parse_query('malware OR virus OR trojan')
        assert len(terms) == 3
        assert terms[0].term == 'malware'
        assert terms[0].operator == 'OR'  # Changed from 'DEFAULT' to 'OR'
        assert terms[1].term == 'virus'
        assert terms[1].operator == 'OR'
        assert terms[2].term == 'trojan'
        assert terms[2].operator == 'OR'
    
    def test_parse_not_query(self):
        """Test parsing NOT queries."""
        terms = self.parser.parse_query('malware NOT basic')
        assert len(terms) == 2
        assert terms[0].term == 'malware'
        assert terms[0].operator == 'DEFAULT'
        assert terms[1].term == 'basic'
        assert terms[1].operator == 'NOT'
    
    def test_parse_quoted_phrases(self):
        """Test parsing quoted phrases."""
        terms = self.parser.parse_query('"advanced persistent threat" AND malware')
        assert len(terms) == 2
        assert terms[0].term == 'advanced persistent threat'
        assert terms[0].operator == 'DEFAULT'
        assert terms[1].term == 'malware'
        assert terms[1].operator == 'AND'
    
    def test_evaluate_simple_match(self):
        """Test simple term matching."""
        terms = self.parser.parse_query('malware')
        result = self.parser.evaluate_article(self.sample_articles[1], terms)
        assert result is True
    
    def test_evaluate_and_match(self):
        """Test AND operator matching."""
        terms = self.parser.parse_query('ransomware AND infrastructure')
        result = self.parser.evaluate_article(self.sample_articles[0], terms)
        assert result is True
    
    def test_evaluate_and_no_match(self):
        """Test AND operator when not all terms match."""
        terms = self.parser.parse_query('ransomware AND virus')
        result = self.parser.evaluate_article(self.sample_articles[0], terms)
        assert result is False
    
    def test_evaluate_or_match(self):
        """Test OR operator matching."""
        terms = self.parser.parse_query('malware OR virus')
        result = self.parser.evaluate_article(self.sample_articles[1], terms)
        assert result is True
    
    def test_evaluate_not_match(self):
        """Test NOT operator matching."""
        terms = self.parser.parse_query('malware NOT basic')
        result = self.parser.evaluate_article(self.sample_articles[1], terms)
        assert result is True
    
    def test_evaluate_not_exclude(self):
        """Test NOT operator exclusion."""
        terms = self.parser.parse_query('security NOT basic')
        result = self.parser.evaluate_article(self.sample_articles[3], terms)
        assert result is False
    
    def test_evaluate_complex_query(self):
        """Test complex query with multiple operators."""
        # Simplified test without parentheses for now
        terms = self.parser.parse_query('"critical infrastructure" AND ransomware NOT basic')
        result = self.parser.evaluate_article(self.sample_articles[0], terms)
        assert result is True


class TestParseBooleanSearch:
    """Test cases for parse_boolean_search function."""
    
    def test_empty_query(self):
        """Test empty query returns all articles."""
        articles = [
            {'id': 1, 'title': 'Test', 'content': 'Content'},
            {'id': 2, 'title': 'Another', 'content': 'More content'}
        ]
        result = parse_boolean_search('', articles)
        assert len(result) == 2
    
    def test_simple_filter(self):
        """Test simple filtering."""
        articles = [
            {'id': 1, 'title': 'Malware Report', 'content': 'Content'},
            {'id': 2, 'title': 'Security Guide', 'content': 'More content'}
        ]
        result = parse_boolean_search('malware', articles)
        assert len(result) == 1
        assert result[0]['id'] == 1
    
    def test_and_filter(self):
        """Test AND filtering."""
        articles = [
            {'id': 1, 'title': 'Ransomware Infrastructure', 'content': 'Critical infrastructure attack'},
            {'id': 2, 'title': 'Malware Report', 'content': 'Basic malware analysis'}
        ]
        result = parse_boolean_search('ransomware AND infrastructure', articles)
        assert len(result) == 1
        assert result[0]['id'] == 1
    
    def test_or_filter(self):
        """Test OR filtering."""
        articles = [
            {'id': 1, 'title': 'Malware Report', 'content': 'Content'},
            {'id': 2, 'title': 'Virus Analysis', 'content': 'More content'},
            {'id': 3, 'title': 'Security Guide', 'content': 'Guide content'}
        ]
        result = parse_boolean_search('malware OR virus', articles)
        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[1]['id'] == 2


if __name__ == '__main__':
    pytest.main([__file__])
