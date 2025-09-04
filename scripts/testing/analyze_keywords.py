#!/usr/bin/env python3
"""
Analyze Windows malware keywords distribution across article classifications.
"""

import json
import re
import requests
from collections import defaultdict, Counter

# Windows malware/threat hunting keywords from improved_search_query.txt
WINDOWS_KEYWORDS = [
    'rundll32', 'comspec', 'msiexec', 'wmic', 'iex', 'findstr',
    'hkey', 'hklm', 'appdata', 'programdata', 'temp', 'powershell.exe',
    'wbem', '==', 'c:\\windows\\', 'Event ID', 'EventID',
    '.bat', '.ps1', '.lnk', 'D:\\', '.vhdx', '.iso',
    '<Command>', 'pipe', 'MZ', 'svchost', '::',
    '-accepteula', 'lsass.exe', 'WINDIR', '[.]', 'wintmp'
]

def analyze_keywords():
    """Analyze keyword distribution across classifications."""
    
    # Get all articles
    response = requests.get('http://localhost:8000/api/articles?limit=1000')
    articles = response.json()['articles']
    
    # Initialize counters
    keyword_stats = defaultdict(lambda: defaultdict(int))
    total_by_class = defaultdict(int)
    
    for article in articles:
        if not article.get('metadata') or not article['metadata'].get('training_category'):
            continue
            
        classification = article['metadata']['training_category']
        total_by_class[classification] += 1
        
        content = article.get('content', '').lower()
        
        # Check each keyword
        for keyword in WINDOWS_KEYWORDS:
            # Handle special characters in keywords
            if keyword in ['[.]', '::', '==', '-accepteula']:
                pattern = re.escape(keyword)
            elif keyword in ['c:\\windows\\', 'D:\\']:
                pattern = re.escape(keyword)
            elif keyword == '<Command>':
                pattern = r'<command>'
            elif keyword == 'Event ID':
                pattern = r'event\s+id'
            elif keyword == 'EventID':
                pattern = r'eventid'
            elif keyword == 'lsass.exe':
                pattern = r'lsass\.exe'
            elif keyword == 'powershell.exe':
                pattern = r'powershell\.exe'
            else:
                pattern = r'\b' + re.escape(keyword) + r'\b'
            
            if re.search(pattern, content, re.IGNORECASE):
                keyword_stats[keyword][classification] += 1
    
    # Analyze results
    print("Windows Malware Keywords Analysis")
    print("=" * 50)
    print(f"Total articles analyzed: {sum(total_by_class.values())}")
    print(f"Articles by classification:")
    for cls, count in total_by_class.items():
        print(f"  {cls}: {count}")
    print()
    
    # Find perfect discriminators
    perfect_discriminators = []
    good_discriminators = []
    
    for keyword in WINDOWS_KEYWORDS:
        stats = keyword_stats[keyword]
        chosen_count = stats.get('chosen', 0)
        rejected_count = stats.get('rejected', 0)
        unclassified_count = stats.get('unclassified', 0)
        
        total_matches = chosen_count + rejected_count + unclassified_count
        
        if total_matches == 0:
            continue
            
        print(f"Keyword: {keyword}")
        print(f"  Total matches: {total_matches}")
        print(f"  Chosen: {chosen_count}")
        print(f"  Rejected: {rejected_count}")
        print(f"  Unclassified: {unclassified_count}")
        
        # Check if it's a perfect discriminator
        if chosen_count > 0 and rejected_count == 0 and unclassified_count == 0:
            perfect_discriminators.append(keyword)
            print(f"  ✅ PERFECT DISCRIMINATOR - 100% Chosen, 0% others")
        elif chosen_count > 0 and (rejected_count == 0 or unclassified_count == 0):
            good_discriminators.append(keyword)
            print(f"  🟡 GOOD DISCRIMINATOR - High Chosen ratio")
        else:
            print(f"  ❌ Not a good discriminator")
        print()
    
    print("=" * 50)
    print("PERFECT DISCRIMINATORS (100% Chosen, 0% others):")
    if perfect_discriminators:
        for keyword in perfect_discriminators:
            print(f"  ✅ {keyword}")
    else:
        print("  None found")
    
    print("\nGOOD DISCRIMINATORS (High Chosen ratio):")
    if good_discriminators:
        for keyword in good_discriminators:
            print(f"  🟡 {keyword}")
    else:
        print("  None found")

if __name__ == "__main__":
    analyze_keywords()
