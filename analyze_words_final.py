#!/usr/bin/env python3
"""
Analyze non-English dictionary words in top 25 threat hunting articles
"""

import re
import json
from collections import defaultdict, Counter
import nltk
from nltk.corpus import words

# Download English word list if not present
try:
    english_words = set(words.words())
except LookupError:
    nltk.download('words')
    english_words = set(words.words())

def extract_words(text):
    """Extract words from text, filtering out non-English dictionary words"""
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Common English words that NLTK might miss
    common_english = {
        'using', 'observed', 'files', 'has', 'hosts', 'hours', 'servers', 
        'commands', 'activities', 'named', 'addresses', 'explored', 'motivated',
        'researchers', 'config', 'credentials', 'accessed', 'analysts', 'tracking',
        'features', 'cases', 'compromised', 'including', 'tools', 'windows',
        'conducting', 'downloaded', 'scripts', 'configured', 'types', 'details',
        'shared', 'websites', 'visitors', 'identified', 'deploying', 'uses',
        'variants', 'updated', 'takeaways', 'targeting', 'accounts', 'nirsoft',
        'lsass', 'smb', 'intel', 'att', 'cobaltstrike', 'captcha', 'javascript',
        'payload', 'malware', 'ransomware', 'powershell', 'exe', 'dll', 'http',
        'microsoft', 'adfind', 'php', 'csv', 'ipsplugin'
    }
    
    # Filter out English dictionary words and common English words
    non_english_words = [word for word in words if word not in english_words and word not in common_english]
    
    return non_english_words

def analyze_articles():
    """Analyze non-English dictionary words from extracted article data"""
    
    # Read the extracted data
    with open('/tmp/top_articles_clean.txt', 'r') as f:
        lines = f.readlines()
    
    articles = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Split by pipe delimiter
        parts = line.split('|')
        if len(parts) >= 5:
            article_id = parts[0].strip()
            title = parts[1].strip()
            source = parts[2].strip()
            threat_score = parts[3].strip()
            content = parts[4].strip()
            
            articles.append({
                'id': article_id,
                'title': title,
                'source': source,
                'threat_score': threat_score,
                'content': content
            })
    
    print(f"Found {len(articles)} articles to analyze")
    
    word_stats = defaultdict(lambda: {'count': 0, 'articles': set()})
    
    for article in articles:
        article_id = article['id']
        content = article['content']
        title = article['title']
        
        print(f"Processing article {article_id}: {title[:50]}...")
        
        words = extract_words(content)
        word_counts = Counter(words)
        
        # Update statistics
        for word, count in word_counts.items():
            word_stats[word]['count'] += count
            word_stats[word]['articles'].add(article_id)
    
    # Convert sets to counts for final analysis
    for word in word_stats:
        word_stats[word]['article_count'] = len(word_stats[word]['articles'])
        del word_stats[word]['articles']  # Remove set to make JSON serializable
    
    return word_stats, articles

def main():
    """Main analysis function"""
    print("Starting non-English dictionary word analysis...")
    
    word_stats, articles = analyze_articles()
    
    # Sort by average occurrences (total count / number of articles)
    sorted_by_avg = sorted(
        word_stats.items(),
        key=lambda x: x[1]['count'] / x[1]['article_count'] if x[1]['article_count'] > 0 else 0,
        reverse=True
    )
    
    # Sort by number of articles where they appear
    sorted_by_articles = sorted(
        word_stats.items(),
        key=lambda x: x[1]['article_count'],
        reverse=True
    )
    
    print("\n" + "="*80)
    print("TOP 50 NON-ENGLISH DICTIONARY WORDS BY AVERAGE OCCURRENCES")
    print("="*80)
    print(f"{'Word':<20} {'Total Count':<12} {'Articles':<10} {'Avg Count':<10}")
    print("-"*80)
    
    for i, (word, stats) in enumerate(sorted_by_avg[:50], 1):
        avg_count = stats['count'] / stats['article_count'] if stats['article_count'] > 0 else 0
        print(f"{word:<20} {stats['count']:<12} {stats['article_count']:<10} {avg_count:<10.2f}")
    
    print("\n" + "="*80)
    print("TOP 50 NON-ENGLISH DICTIONARY WORDS BY NUMBER OF ARTICLES")
    print("="*80)
    print(f"{'Word':<20} {'Total Count':<12} {'Articles':<10} {'Avg Count':<10}")
    print("-"*80)
    
    for i, (word, stats) in enumerate(sorted_by_articles[:50], 1):
        avg_count = stats['count'] / stats['article_count'] if stats['article_count'] > 0 else 0
        print(f"{word:<20} {stats['count']:<12} {stats['article_count']:<10} {avg_count:<10.2f}")
    
    # Save detailed results to JSON
    results = {
        'by_average_occurrences': sorted_by_avg[:50],
        'by_article_count': sorted_by_articles[:50],
        'total_unique_words': len(word_stats),
        'total_articles_analyzed': len(articles)
    }
    
    with open('/tmp/non_english_words_analysis.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to /tmp/non_english_words_analysis.json")
    print(f"Total unique non-English words found: {len(word_stats)}")
    print(f"Articles analyzed: {len(articles)}")

if __name__ == "__main__":
    main()

