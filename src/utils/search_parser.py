"""
Boolean Search Query Parser

This module provides functionality to parse search queries with boolean operators
(AND, OR, NOT) and apply them to article filtering.
"""

import re
from typing import List, Dict, Any, Callable
from dataclasses import dataclass


@dataclass
class SearchTerm:
    """Represents a search term with its operator."""
    term: str
    operator: str  # 'AND', 'OR', 'NOT', or 'DEFAULT'
    negated: bool = False


class BooleanSearchParser:
    """Parser for boolean search queries."""
    
    def __init__(self):
        # Define operators and their precedence
        self.operators = {
            'AND': 2,
            'OR': 1,
            'NOT': 3
        }
        
        # Compile regex patterns
        self.operator_pattern = re.compile(
            r'\b(AND|OR|NOT)\b', 
            re.IGNORECASE
        )
        self.quote_pattern = re.compile(r'"([^"]*)"')
        self.term_pattern = re.compile(r'\b\w+\b')
    
    def parse_query(self, query: str) -> List[SearchTerm]:
        """
        Parse a search query into a list of SearchTerm objects.
        
        Args:
            query: The search query string
            
        Returns:
            List of SearchTerm objects
        """
        if not query or not query.strip():
            return []
        
        query = query.strip()
        terms = []
        
        # Handle quoted phrases first
        quoted_terms = self.quote_pattern.findall(query)
        for quoted_term in quoted_terms:
            # Remove the quoted term from the original query
            query = query.replace(f'"{quoted_term}"', '')
            terms.append(SearchTerm(quoted_term, 'DEFAULT'))
        
        # Split by operators
        parts = self.operator_pattern.split(query)
        
        current_operator = 'DEFAULT'
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
                
            if part.upper() in self.operators:
                current_operator = part.upper()
                continue
            
            # Extract individual terms from this part
            individual_terms = self.term_pattern.findall(part)
            for term in individual_terms:
                if term.upper() in self.operators:
                    current_operator = term.upper()
                    continue
                    
                if term:
                    terms.append(SearchTerm(term, current_operator))
        
        # If we have OR terms, treat the first term as OR as well
        if terms and any(term.operator == 'OR' for term in terms):
            if terms[0].operator == 'DEFAULT':
                terms[0] = SearchTerm(terms[0].term, 'OR')
        
        return terms
    
    def evaluate_article(self, article: Dict[str, Any], terms: List[SearchTerm]) -> bool:
        """
        Evaluate whether an article matches the boolean search criteria.
        
        Args:
            article: Article dictionary with 'title' and 'content' fields
            terms: List of SearchTerm objects
            
        Returns:
            True if article matches, False otherwise
        """
        if not terms:
            return True
        
        # Group terms by operator
        and_terms = [term for term in terms if term.operator == 'AND']
        or_terms = [term for term in terms if term.operator == 'OR']
        not_terms = [term for term in terms if term.operator == 'NOT']
        default_terms = [term for term in terms if term.operator == 'DEFAULT']
        
        # Check NOT terms first (if any NOT term matches, article is excluded)
        for term in not_terms:
            if self._term_matches(article, term.term):
                return False
        
        # If we have both AND and OR terms, we need to handle them carefully
        # For now, treat default terms as AND terms
        all_and_terms = and_terms + default_terms
        
        # If we have OR terms but no AND terms, any OR term can match
        if or_terms and not all_and_terms:
            return any(self._term_matches(article, term.term) for term in or_terms)
        
        # If we have AND terms but no OR terms, all AND terms must match
        if all_and_terms and not or_terms:
            return all(self._term_matches(article, term.term) for term in all_and_terms)
        
        # If we have both AND and OR terms, all AND terms must match AND at least one OR term must match
        if all_and_terms and or_terms:
            and_matches = all(self._term_matches(article, term.term) for term in all_and_terms)
            or_matches = any(self._term_matches(article, term.term) for term in or_terms)
            return and_matches and or_matches
        
        return True
    
    def _term_matches(self, article: Dict[str, Any], term: str) -> bool:
        """
        Check if a term matches in the article's title or content.
        
        Args:
            article: Article dictionary
            term: Search term
            
        Returns:
            True if term is found, False otherwise
        """
        term_lower = term.lower()
        
        # Check title
        if article.get('title'):
            if term_lower in article['title'].lower():
                return True
        
        # Check content
        if article.get('content'):
            if term_lower in article['content'].lower():
                return True
        
        return False


def parse_boolean_search(query: str, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse a boolean search query and filter articles accordingly.
    
    Args:
        query: Search query string with boolean operators
        articles: List of article dictionaries
        
    Returns:
        Filtered list of articles
    """
    parser = BooleanSearchParser()
    terms = parser.parse_query(query)
    
    if not terms:
        return articles
    
    return [article for article in articles if parser.evaluate_article(article, terms)]


def get_search_help_text() -> str:
    """Get help text for boolean search syntax."""
    return """
    Boolean Search Syntax:
    
    • Simple terms: malware, ransomware
    • AND operator: malware AND ransomware
    • OR operator: malware OR ransomware  
    • NOT operator: malware NOT ransomware
    • Quoted phrases: "advanced persistent threat"
    • Mixed: "APT" AND (malware OR virus) NOT basic
    
    Examples:
    • "ransomware" AND "critical infrastructure"
    • malware OR virus OR trojan
    • "zero day" NOT basic
    • "threat actor" AND (APT OR "advanced persistent threat")
    """
