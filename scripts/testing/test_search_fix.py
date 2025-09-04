# Test script for the fixed search parser
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.search_parser import BooleanSearchParser, parse_boolean_search

def test_search_parser():
    """Test the fixed search parser with complex queries."""
    
    # Test query similar to yours
    test_query = '"rundll32" OR "comspec" OR "msiexec" OR "wmic" OR "iex" OR "findstr" OR "hkey" OR "hklm" OR "appdata" OR "programdata" OR "\\temp\\" OR "powershell.exe" OR "wbem" OR "==" OR "c:\\windows\\" OR "Event ID" OR "EventID" OR ".bat" OR ".ps1" OR ".lnk" OR "D:\\" OR ".vhdx" OR ".iso" OR "<Command>" OR "\\pipe\\" OR "MZ" OR "svchost" OR "::" OR "-accepteula" OR "lsass.exe" OR "%WINDIR%" OR "[.]" OR "%wintmp%"'
    
    # Test articles
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
            'title': 'Unrelated Article',
            'content': 'This article has nothing to do with malware or Windows processes.'
        }
    ]
    
    print("Testing Fixed Search Parser")
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
    
    # Test filtering
    filtered_articles = parse_boolean_search(test_query, test_articles)
    
    print("Filtered Articles:")
    for article in filtered_articles:
        print(f"  - {article['title']}")
    
    print(f"\nTotal articles: {len(test_articles)}")
    print(f"Filtered articles: {len(filtered_articles)}")
    
    return len(filtered_articles) > 0

if __name__ == "__main__":
    success = test_search_parser()
    if success:
        print("\n✅ Search parser is working correctly!")
    else:
        print("\n❌ Search parser has issues!")
