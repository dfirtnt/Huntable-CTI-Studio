#!/usr/bin/env python3
"""Direct SimHash backfill using psql commands."""

import subprocess
import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_psql_command(sql_command):
    """Run a SQL command using psql."""
    cmd = [
        "docker", "exec", "cti_postgres", 
        "psql", "-U", "cti_user", "-d", "cti_scraper", "-c", sql_command
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"SQL command failed: {e.stderr}")
        return None


def get_coverage_stats():
    """Get current SimHash coverage statistics."""
    sql = """
    SELECT 
        COUNT(*) as total_articles,
        COUNT(CASE WHEN simhash IS NOT NULL THEN 1 END) as simhash_articles,
        ROUND((COUNT(CASE WHEN simhash IS NOT NULL THEN 1 END)::numeric / COUNT(*)) * 100, 1) as coverage_percent
    FROM articles
    """
    
    result = run_psql_command(sql)
    if result:
        lines = result.split('\n')
        for line in lines:
            if '|' in line and not line.startswith('-') and not line.startswith(' ') and not 'total_articles' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3 and parts[0].isdigit():
                    total = int(parts[0])
                    with_simhash = int(parts[1])
                    coverage = float(parts[2])
                    
                    logger.info(f"Current SimHash Coverage:")
                    logger.info(f"  Total articles: {total}")
                    logger.info(f"  Articles with SimHash: {with_simhash}")
                    logger.info(f"  Coverage: {coverage}%")
                    
                    return coverage
    
    return 0


def backfill_simhash():
    """Backfill SimHash using a Python script that computes SimHash."""
    
    # First, get articles without SimHash
    sql = "SELECT id, title, content FROM articles WHERE simhash IS NULL ORDER BY created_at LIMIT 10;"
    result = run_psql_command(sql)
    
    if not result:
        logger.error("Failed to get articles without SimHash")
        return False
    
    logger.info("Found articles without SimHash. Creating Python backfill script...")
    
    # Create a simple Python script to compute SimHash
    python_script = '''
import hashlib
import re
from collections import Counter

def tokenize(text):
    """Tokenize text into features for SimHash."""
    if not text:
        return []
    
    text = text.lower()
    tokens = re.findall(r'\\b\\w+\\b', text)
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
        'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did',
        'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those'
    }
    return [token for token in tokens if len(token) > 2 and token not in stop_words]

def get_feature_hash(feature):
    """Get hash value for a feature."""
    hash_obj = hashlib.md5(feature.encode('utf-8'))
    return int(hash_obj.hexdigest(), 16) % (2 ** 64)

def get_weighted_vector(features):
    """Get weighted vector based on feature frequency."""
    feature_counts = Counter(features)
    vector = [0] * 64
    
    for feature, count in feature_counts.items():
        feature_hash = get_feature_hash(feature)
        for i in range(64):
            if feature_hash & (1 << i):
                vector[i] += count
            else:
                vector[i] -= count
    
    return vector

def compute_simhash(text, title=""):
    """Compute SimHash for given text."""
    full_text = f"{title} {text}"
    features = tokenize(full_text)
    
    if not features:
        return 0, 0
    
    vector = get_weighted_vector(features)
    simhash = 0
    for i, weight in enumerate(vector):
        if weight > 0:
            simhash |= (1 << i)
    
    bucket = simhash % 16
    return simhash, bucket

# Test the function
print("SimHash function ready")
'''
    
    # Write the script to a file
    with open('/tmp/simhash_func.py', 'w') as f:
        f.write(python_script)
    
    logger.info("Created SimHash computation function")
    
    # Now create the main backfill script
    backfill_script = '''
import sys
import os
sys.path.append('/app')

import psycopg2
import os
from simhash_func import compute_simhash

# Connect to database
# Use environment variable for password, fallback to default for development
postgres_password = os.getenv("POSTGRES_PASSWORD", "cti_password")
conn = psycopg2.connect(
    host="postgres",
    database="cti_scraper", 
    user="cti_user",
    password=postgres_password
)
cur = conn.cursor()

# Get articles without SimHash
cur.execute("SELECT id, title, content FROM articles WHERE simhash IS NULL ORDER BY created_at")
articles = cur.fetchall()

print(f"Found {len(articles)} articles without SimHash")

updated = 0
for article_id, title, content in articles:
    try:
        simhash, bucket = compute_simhash(content or "", title or "")
        
        cur.execute(
            "UPDATE articles SET simhash = %s, simhash_bucket = %s WHERE id = %s",
            (simhash, bucket, article_id)
        )
        
        updated += 1
        if updated % 50 == 0:
            print(f"Updated {updated}/{len(articles)} articles")
            
    except Exception as e:
        print(f"Error updating article {article_id}: {e}")
        continue

conn.commit()
print(f"Successfully updated {updated} articles")

cur.close()
conn.close()
'''
    
    with open('/tmp/backfill_main.py', 'w') as f:
        f.write(backfill_script)
    
    logger.info("Created main backfill script")
    
    # Copy files to container and run
    subprocess.run(["docker", "cp", "/tmp/simhash_func.py", "cti_worker:/tmp/simhash_func.py"])
    subprocess.run(["docker", "cp", "/tmp/backfill_main.py", "cti_worker:/tmp/backfill_main.py"])
    
    # Run the backfill
    cmd = ["docker", "exec", "cti_worker", "python", "/tmp/backfill_main.py"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        logger.info("Backfill completed successfully")
        logger.info(result.stdout)
        return True
    else:
        logger.error(f"Backfill failed: {result.stderr}")
        return False


def main():
    """Main function to backfill SimHash values."""
    logger.info("Starting SimHash backfill process")
    
    # Get current coverage
    current_coverage = get_coverage_stats()
    
    if current_coverage >= 99.0:
        logger.info("SimHash coverage is already excellent (≥99%), no backfill needed")
        return True
    
    # Run backfill
    logger.info("Running SimHash backfill...")
    success = backfill_simhash()
    
    if success:
        # Get updated coverage
        logger.info("Backfill completed, checking updated coverage...")
        updated_coverage = get_coverage_stats()
        
        improvement = updated_coverage - current_coverage
        logger.info(f"Coverage improved from {current_coverage}% to {updated_coverage}% (+{improvement}%)")
        
        if updated_coverage >= 99.0:
            logger.info("✅ SimHash coverage is now excellent!")
        else:
            logger.warning(f"⚠️ SimHash coverage is {updated_coverage}% - may need investigation")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
