# Debug script for the simple search query
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.search_parser import BooleanSearchParser, parse_boolean_search

def debug_simple_search():
    """Debug the simple search query that's not working."""
    
    # Simple test query
    test_query = '"rundll32" OR "comspec"'
    
    # Test articles that should match
    test_articles = [
        {
            'id': 1,
            'title': 'Malware Analysis Report',
            'content': 'The malware uses rundll32.exe to execute malicious code and creates files in c:\\windows\\temp directory.'
        },
        {
            'id': 2,
            'title': 'PowerShell Attack Detection',
            'content': 'Attackers used powershell.exe to download and execute payloads from appdata folder.'
        },
        {
            'id': 3,
            'title': 'Registry Analysis',
            'content': 'Suspicious registry keys found in HKEY_LOCAL_MACHINE and HKEY_CURRENT_USER.'
        },
        {
            'id': 4,
            'title': 'Command Line Analysis',
            'content': 'The attacker used comspec to execute commands and rundll32 for DLL injection.'
        },
        {
            'id': 5,
            'title': 'Unrelated Article',
            'content': 'This article has nothing to do with malware or Windows processes.'
        }
    ]
    
    print("Debugging Simple Search Query")
    print("=" * 50)
    print(f"Query: {test_query}")
    print()
    
    # Test parsing
    parser = BooleanSearchParser()
    terms = parser.parse_query(test_query)
    
    print("Parsed Terms:")
    for i, term in enumerate(terms):
        print(f"  {i+1}. '{term.term}' (operator: {term.operator})")
    print()
    
    # Test individual term matching
    print("Testing Individual Term Matching:")
    for term in terms:
        matches = []
        for article in test_articles:
            if parser._term_matches(article, term.term):
                matches.append(article['title'])
        print(f"  '{term.term}' matches: {matches}")
    print()
    
    # Test filtering
    filtered_articles = parse_boolean_search(test_query, test_articles)
    
    print("Filtered Articles:")
    for article in filtered_articles:
        print(f"  - {article['title']}")
    
    print(f"\nTotal articles: {len(test_articles)}")
    print(f"Filtered articles: {len(filtered_articles)}")
    
    # Debug the evaluation logic
    print("\nDebugging Evaluation Logic:")
    for article in test_articles:
        result = parser.evaluate_article(article, terms)
        print(f"  '{article['title']}': {result}")
    
    return len(filtered_articles) > 0

if __name__ == "__main__":
    success = debug_simple_search()
    if success:
        print("\n✅ Search parser is working correctly!")
    else:
        print("\n❌ Search parser has issues!")
