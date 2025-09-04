# Test script that simulates the web application scenario
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.search_parser import parse_boolean_search

def test_web_app_scenario():
    """Test the search in the same way the web app does it."""
    
    # Simulate article objects (like from database)
    class MockArticle:
        def __init__(self, id, title, content, source_id=1):
            self.id = id
            self.title = title
            self.content = content
            self.source_id = source_id
            self.published_at = None
            self.canonical_url = None
            self.metadata = {}
    
    # Create test articles
    test_articles = [
        MockArticle(1, 'Malware Analysis Report', 'The malware uses rundll32.exe to execute malicious code and creates files in c:\\windows\\temp directory.'),
        MockArticle(2, 'PowerShell Attack Detection', 'Attackers used powershell.exe to download and execute payloads from appdata folder.'),
        MockArticle(3, 'Registry Analysis', 'Suspicious registry keys found in HKEY_LOCAL_MACHINE and HKEY_CURRENT_USER.'),
        MockArticle(4, 'Command Line Analysis', 'The attacker used comspec to execute commands and rundll32 for DLL injection.'),
        MockArticle(5, 'Unrelated Article', 'This article has nothing to do with malware or Windows processes.')
    ]
    
    # Test query
    search_query = '"rundll32" OR "comspec"'
    
    print("Testing Web Application Scenario")
    print("=" * 50)
    print(f"Query: {search_query}")
    print(f"Total articles: {len(test_articles)}")
    print()
    
    # Convert to dict format (exactly like the web app does)
    articles_dict = [
        {
            'id': article.id,
            'title': article.title,
            'content': article.content,
            'source_id': article.source_id,
            'published_at': article.published_at,
            'canonical_url': article.canonical_url,
            'metadata': article.metadata
        }
        for article in test_articles
    ]
    
    print("Articles converted to dict format:")
    for article_dict in articles_dict:
        print(f"  ID {article_dict['id']}: '{article_dict['title']}'")
        print(f"    Content: {article_dict['content'][:50]}...")
    print()
    
    # Apply boolean search filtering
    filtered_dicts = parse_boolean_search(search_query, articles_dict)
    
    print("Filtered Articles (dict format):")
    for article_dict in filtered_dicts:
        print(f"  - {article_dict['title']}")
    
    print(f"\nTotal articles: {len(test_articles)}")
    print(f"Filtered articles: {len(filtered_dicts)}")
    
    # Convert back to article objects (like the web app does)
    filtered_article_ids = {article['id'] for article in filtered_dicts}
    filtered_articles = [
        article for article in test_articles
        if article.id in filtered_article_ids
    ]
    
    print("\nFinal filtered articles (object format):")
    for article in filtered_articles:
        print(f"  - {article.title}")
    
    return len(filtered_articles) > 0

if __name__ == "__main__":
    success = test_web_app_scenario()
    if success:
        print("\n✅ Web app scenario works correctly!")
    else:
        print("\n❌ Web app scenario has issues!")
