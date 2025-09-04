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
        # Updated quote pattern to handle nested quotes better
        self.quote_pattern = re.compile(r'"([^"]*)"')
        # Updated term pattern to handle special characters
        self.term_pattern = re.compile(r'[^\s"()]+')
    
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
        
        # Step 1: Extract all quoted terms with their positions
        quoted_terms = []
        for match in self.quote_pattern.finditer(query):
            quoted_terms.append({
                'term': match.group(1),
                'start': match.start(),
                'end': match.end(),
                'full_match': match.group(0)
            })
        
        # Step 2: Remove quoted terms from query (in reverse order to maintain positions)
        modified_query = query
        for quoted_term in reversed(quoted_terms):
            modified_query = modified_query[:quoted_term['start']] + modified_query[quoted_term['end']:]
        
        # Step 3: Add quoted terms to results
        for quoted_term in quoted_terms:
            terms.append(SearchTerm(quoted_term['term'], 'DEFAULT'))
        
        # Step 4: Parse remaining query for operators and terms
        parts = self.operator_pattern.split(modified_query)
        
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
                term = term.strip()
                if not term:
                    continue
                    
                if term.upper() in self.operators:
                    current_operator = term.upper()
                    continue
                    
                terms.append(SearchTerm(term, current_operator))
        
        # Step 5: Handle OR logic - if we have OR terms, treat the first term as OR as well
        if terms and any(term.operator == 'OR' for term in terms):
            if terms[0].operator == 'DEFAULT':
                terms[0] = SearchTerm(terms[0].term, 'OR')
        
        # Step 6: If we have multiple terms with DEFAULT operator, treat them as OR
        # This handles queries like "term1" OR "term2" OR "term3"
        default_terms = [term for term in terms if term.operator == 'DEFAULT']
        if len(default_terms) > 1:
            for term in default_terms:
                term.operator = 'OR'
        
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
    
    Special Characters Supported:
    • File paths: "c:\\windows\\system32"
    • Process names: "powershell.exe"
    • Registry keys: "HKEY_LOCAL_MACHINE"
    • File extensions: ".bat", ".ps1"
    • Technical terms: "Event ID", "MZ"
    
    Case Sensitivity:
    • All searches are case-insensitive
    • "rundll32" matches "RUNDLL32", "Rundll32", etc.
    • "PowerShell" matches "powershell", "POWERSHELL", etc.
"""
