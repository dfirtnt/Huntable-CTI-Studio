#!/usr/bin/env python3
"""
Analyze non-English dictionary words in top 25 threat hunting articles
"""

import re
import json
import psycopg2
from collections import defaultdict, Counter
import nltk
from nltk.corpus import words

# Download English word list if not present
try:
    english_words = set(words.words())
except LookupError:
    nltk.download('words')
    english_words = set(words.words())

def connect_db():
    """Connect to PostgreSQL database via Docker"""
    return psycopg2.connect(
        host="localhost",
        port="5432", 
        database="cti_scraper",
        user="cti_user",
        password=os.getenv("POSTGRES_PASSWORD", "cti_password")
    )

def get_top_articles():
    """Get top 25 articles by threat hunting score"""
    conn = connect_db()
    cur = conn.cursor()
    
    query = """
    SELECT 
        a.id,
        a.title,
        s.name as source,
        (a.article_metadata->>'threat_hunting_score')::float as threat_score,
        a.content
    FROM articles a 
    JOIN sources s ON a.source_id = s.id 
    WHERE a.article_metadata->>'threat_hunting_score' IS NOT NULL 
    ORDER BY (a.article_metadata->>'threat_hunting_score')::float DESC 
    LIMIT 25;
    """
    
    cur.execute(query)
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def extract_words(text):
    """Extract words from text, filtering out non-English dictionary words"""
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter out English dictionary words
    non_english_words = [word for word in words if word not in english_words]
    
    return non_english_words

def analyze_words():
    """Analyze non-English dictionary words across top articles"""
    articles = get_top_articles()
    
    word_stats = defaultdict(lambda: {'count': 0, 'articles': set()})
    article_word_counts = defaultdict(int)
    
    print(f"Analyzing {len(articles)} articles...")
    
    for article_id, title, source, threat_score, content in articles:
        print(f"Processing article {article_id}: {title[:50]}...")
        
        words = extract_words(content)
        word_counts = Counter(words)
        
        # Update statistics
        for word, count in word_counts.items():
            word_stats[word]['count'] += count
            word_stats[word]['articles'].add(article_id)
        
        # Count unique words per article
        article_word_counts[article_id] = len(set(words))
    
    # Convert sets to counts for final analysis
    for word in word_stats:
        word_stats[word]['article_count'] = len(word_stats[word]['articles'])
        del word_stats[word]['articles']  # Remove set to make JSON serializable
    
    return word_stats, article_word_counts

def main():
    """Main analysis function"""
    print("Starting non-English dictionary word analysis...")
    
    word_stats, article_counts = analyze_words()
    
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
        'total_articles_analyzed': len(article_counts)
    }
    
    with open('/tmp/non_english_words_analysis.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nDetailed results saved to /tmp/non_english_words_analysis.json")
    print(f"Total unique non-English words found: {len(word_stats)}")
    print(f"Articles analyzed: {len(article_counts)}")

if __name__ == "__main__":
    main()
