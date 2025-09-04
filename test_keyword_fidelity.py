#!/usr/bin/env python3
"""
Test the fidelity of missing keywords against actual article classifications.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import requests
import re
from collections import defaultdict

def test_keyword_fidelity():
    """Test keyword fidelity against actual article classifications."""
    
    # Missing keywords to test
    missing_keywords = [
        'hkey', '\\temp\\', '.vhdx', '\\pipe\\', '%WINDIR%', '%wintmp%'
    ]
    
    # Get all articles
    print("Fetching articles from database...")
    response = requests.get('http://localhost:8000/api/articles?limit=1000')
    articles = response.json()['articles']
    
    print(f"Analyzing {len(articles)} articles...")
    
    # Initialize counters
    keyword_stats = defaultdict(lambda: defaultdict(int))
    total_by_class = defaultdict(int)
    
    for article in articles:
        if not article.get('metadata') or not article['metadata'].get('training_category'):
            continue
            
        classification = article['metadata']['training_category']
        total_by_class[classification] += 1
        
        content = article.get('content', '').lower()
        title = article.get('title', '').lower()
        full_text = f"{title} {content}"
        
        # Check each missing keyword
        for keyword in missing_keywords:
            # Handle special characters in keywords
            if keyword in ['\\temp\\', '\\pipe\\']:
                pattern = re.escape(keyword)
            elif keyword in ['%WINDIR%', '%wintmp%']:
                pattern = re.escape(keyword)
            elif keyword == '.vhdx':
                pattern = r'\b' + re.escape(keyword) + r'\b'
            else:
                pattern = r'\b' + re.escape(keyword) + r'\b'
            
            if re.search(pattern, full_text, re.IGNORECASE):
                keyword_stats[keyword][classification] += 1
    
    # Analyze results
    print("\nKeyword Fidelity Analysis")
    print("=" * 50)
    print(f"Total articles analyzed: {sum(total_by_class.values())}")
    print(f"Articles by classification:")
    for cls, count in total_by_class.items():
        print(f"  {cls}: {count}")
    print()
    
    # Find high-fidelity keywords
    high_fidelity_keywords = []
    medium_fidelity_keywords = []
    low_fidelity_keywords = []
    
    for keyword in missing_keywords:
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
        
        # Calculate fidelity metrics
        if total_matches > 0:
            chosen_ratio = chosen_count / total_matches
            print(f"  Chosen ratio: {chosen_ratio:.1%}")
            
            # Classify fidelity
            if chosen_count > 0 and rejected_count == 0 and unclassified_count == 0:
                high_fidelity_keywords.append(keyword)
                print(f"  ✅ PERFECT FIDELITY - 100% Chosen, 0% others")
            elif chosen_ratio >= 0.8:
                high_fidelity_keywords.append(keyword)
                print(f"  🟢 HIGH FIDELITY - {chosen_ratio:.1%} Chosen ratio")
            elif chosen_ratio >= 0.6:
                medium_fidelity_keywords.append(keyword)
                print(f"  🟡 MEDIUM FIDELITY - {chosen_ratio:.1%} Chosen ratio")
            else:
                low_fidelity_keywords.append(keyword)
                print(f"  🔴 LOW FIDELITY - {chosen_ratio:.1%} Chosen ratio")
        print()
    
    print("=" * 50)
    print("RECOMMENDATIONS:")
    print()
    
    if high_fidelity_keywords:
        print("🟢 HIGH FIDELITY KEYWORDS (Recommended to add):")
        for keyword in high_fidelity_keywords:
            print(f"  ✅ {keyword}")
        print()
    
    if medium_fidelity_keywords:
        print("🟡 MEDIUM FIDELITY KEYWORDS (Consider adding):")
        for keyword in medium_fidelity_keywords:
            print(f"  🟡 {keyword}")
        print()
    
    if low_fidelity_keywords:
        print("🔴 LOW FIDELITY KEYWORDS (Not recommended):")
        for keyword in low_fidelity_keywords:
            print(f"  🔴 {keyword}")
        print()
    
    if not high_fidelity_keywords and not medium_fidelity_keywords:
        print("❌ No keywords with sufficient fidelity found.")
        print("Recommendation: Do not add any of these keywords.")

if __name__ == "__main__":
    test_keyword_fidelity()
