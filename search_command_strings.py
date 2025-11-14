#!/usr/bin/env python3
"""
Search for command-related strings in article content with sentence-level context.
Returns the matching sentence plus 2-3 sentences before and after.
"""

import re
import sys
import os
from typing import List, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection - reads from environment or uses defaults
# Also supports parsing DATABASE_URL if available
def get_db_config():
    db_url = os.getenv('DATABASE_URL', '')
    if db_url and 'postgresql' in db_url:
        # Parse DATABASE_URL: postgresql+asyncpg://user:password@host:port/dbname
        import re
        match = re.match(r'postgresql\+?\w*://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
        if match:
            user, password, host, port, database = match.groups()
            return {
                'host': host,
                'port': int(port),
                'database': database,
                'user': user,
                'password': password
            }
    
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': os.getenv('POSTGRES_DB', 'cti_scraper'),
        'user': os.getenv('POSTGRES_USER', 'cti_user'),
        'password': os.getenv('POSTGRES_PASSWORD', 'cti_password')
    }

DB_CONFIG = get_db_config()

# Search patterns (case-insensitive)
# PostgreSQL uses POSIX regex, Python uses Perl regex
# SQL patterns for database query
SQL_PATTERNS = [
    r'[[:<:]]command[[:>:]]',  # Word boundary for PostgreSQL
    r'[[:<:]]cmd[[:>:]]',
    r'powershel',  # Partial match for powershell
    r'[[:<:]]invoke[[:>:]]',
    r'\.exe[[:>:]]'  # .exe at word end
]

# Python patterns for sentence matching (use \b for word boundaries)
PYTHON_PATTERNS = [
    r'\bcommand\b',
    r'\bcmd\b',
    r'powershel',  # Partial match for powershell
    r'\binvoke\b',
    r'\.exe\b'
]

def split_sentences(text: str) -> List[Tuple[int, str]]:
    """Split text into sentences with their positions.
    Returns list of (sentence_num, sentence_text) tuples.
    """
    # Split on sentence boundaries: . ! ? followed by space and capital letter
    # or end of string. Also handle cases like "Dr." or "U.S." 
    sentence_pattern = r'([.!?]+)\s+(?=[A-Z])|([.!?]+)$'
    
    sentences = []
    sentence_num = 1
    last_end = 0
    
    for match in re.finditer(sentence_pattern, text):
        end_pos = match.end()
        sentence_text = text[last_end:end_pos].strip()
        if sentence_text and len(sentence_text) > 3:  # Filter very short fragments
            sentences.append((sentence_num, sentence_text))
            sentence_num += 1
        last_end = end_pos
    
    # Handle remaining text
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining and len(remaining) > 3:
            sentences.append((sentence_num, remaining))
    
    return sentences

def find_matches_in_sentences(sentences: List[Tuple[int, str]], patterns: List[str]) -> List[int]:
    """Find sentence numbers that match any pattern."""
    matching_sentence_nums = []
    for sentence_num, sentence_text in sentences:
        for pattern in patterns:
            if re.search(pattern, sentence_text, re.IGNORECASE):
                matching_sentence_nums.append(sentence_num)
                break
    return matching_sentence_nums

def get_context(sentences: List[Tuple[int, str]], match_sentence_num: int, context_before: int = 3, context_after: int = 3) -> str:
    """Get context around a matching sentence."""
    start_idx = max(0, match_sentence_num - context_before - 1)
    end_idx = min(len(sentences), match_sentence_num + context_after)
    
    context_sentences = [sentences[i][1] for i in range(start_idx, end_idx)]
    return ' '.join(context_sentences)

def main():
    try:
        # Debug: print connection info (without password)
        print(f"Connecting to: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']} as {DB_CONFIG['user']}", file=sys.stderr)
        
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get articles with matches
        # Build SQL regex pattern (PostgreSQL uses ~* for case-insensitive match)
        # Escape single quotes and join with | for OR
        pattern_sql = '|'.join(SQL_PATTERNS).replace("'", "''")
        query = """
            SELECT id, title, content
            FROM articles
            WHERE content ~* %s
            ORDER BY id
            LIMIT 50
        """
        
        print(f"Searching for pattern: {pattern_sql}", file=sys.stderr)
        cursor.execute(query, (pattern_sql,))
        articles = cursor.fetchall()
        
        print(f"Found {len(articles)} articles with matches\n")
        print("=" * 80)
        
        for article in articles:
            article_id = article['id']
            title = article['title']
            content = article['content']
            
            # Split into sentences
            sentences = split_sentences(content)
            
            # Find matching sentences (use Python patterns)
            matching_nums = find_matches_in_sentences(sentences, PYTHON_PATTERNS)
            
            if matching_nums:
                print(f"\nArticle ID: {article_id}")
                print(f"Title: {title}")
                print(f"Matches found: {len(matching_nums)}")
                print("-" * 80)
                
                # Get context for each match
                for match_num in matching_nums:
                    context = get_context(sentences, match_num, context_before=2, context_after=2)
                    print(f"\n[Match in sentence {match_num}]")
                    print(context)
                    print("-" * 80)
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

