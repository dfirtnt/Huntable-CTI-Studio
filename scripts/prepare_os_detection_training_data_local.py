#!/usr/bin/env python3
"""
Prepare training data for OS detection classifier using LOCAL OS detection.

This script:
1. Queries articles from database (high hunt_score articles)
2. Uses existing OSDetectionService (CTI-BERT + LMStudio) to label articles
3. Exports training data in JSON format for classifier training

No OpenAI required - uses your existing local infrastructure.
"""

import sys
import os
import subprocess
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.os_detection_service import OSDetectionService

VALID_OS_LABELS = ["Windows", "Linux", "MacOS", "multiple", "Unknown"]


def load_articles(min_hunt_score: float = 80.0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load articles from database."""
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    query = f"""
    SELECT json_agg(row_to_json(t)) FROM (
        SELECT 
            a.id, 
            a.title, 
            a.canonical_url as url, 
            s.name as source, 
            a.content, 
            (a.article_metadata->>'threat_hunting_score')::float as hunt_score
        FROM articles a 
        JOIN sources s ON a.source_id = s.id 
        WHERE (a.article_metadata->>'threat_hunting_score')::float >= {min_hunt_score} 
        AND a.archived = false 
        ORDER BY hunt_score DESC
        {limit_clause}
    ) t;
    """
    
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-c", query],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Database query failed: {result.stderr}")
        return []
    
    try:
        json_output = result.stdout.strip()
        if json_output:
            articles = json.loads(json_output)
            return articles if isinstance(articles, list) else []
        return []
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON output: {e}")
        print(f"Output preview: {json_output[:200]}")
        return []


async def label_article_with_local_service(
    article: Dict[str, Any],
    service: OSDetectionService,
    use_fallback: bool = True
) -> Optional[str]:
    """Use local OSDetectionService to label article with OS."""
    
    content = article.get('content', '')
    if not content:
        return None
    
    try:
        # Use existing OS detection service
        result = await service.detect_os(
            content=content[:3000],  # Use first 3000 chars
            use_classifier=True,
            use_fallback=use_fallback,
            force_fallback=False
        )
        
        os_label = result.get('operating_system', 'Unknown')
        
        # Normalize label
        if os_label not in VALID_OS_LABELS:
            if os_label.lower() in ['windows', 'win']:
                os_label = "Windows"
            elif os_label.lower() in ['linux', 'unix']:
                os_label = "Linux"
            elif os_label.lower() in ['macos', 'mac os', 'mac', 'darwin']:
                os_label = "MacOS"
            else:
                os_label = "multiple" if os_label.lower() in ['multi', 'cross-platform'] else "Unknown"
        
        return os_label
        
    except Exception as e:
        print(f"  ✗ Local labeling failed: {e}")
        return None


async def prepare_training_data(
    articles: List[Dict[str, Any]],
    use_fallback: bool = True,
    fallback_model: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Prepare training data from articles using local OS detection."""
    
    training_data = []
    
    # Initialize OS detection service
    print("Initializing OS detection service...")
    service = OSDetectionService()
    
    for i, article in enumerate(articles, 1):
        article_id = article['id']
        hunt_score = article.get('hunt_score', 0.0)
        
        print(f"[{i}/{len(articles)}] Article {article_id} (hunt_score={hunt_score:.1f})...", end=" ")
        
        os_label = await label_article_with_local_service(article, service, use_fallback=use_fallback)
        
        if os_label:
            print(f"✓ Labeled as: {os_label}")
        else:
            print("✗ Failed to label")
            continue
        
        training_data.append({
            "article_id": article_id,
            "title": article.get('title', ''),
            "url": article.get('url', ''),
            "content": article['content'],
            "os_label": os_label,
            "hunt_score": hunt_score,
            "source": article.get('source', ''),
            "labeled_at": datetime.now().isoformat(),
            "labeling_method": "local_os_detection_service"
        })
    
    return training_data


def main():
    parser = argparse.ArgumentParser(description="Prepare OS detection training data using LOCAL detection")
    parser.add_argument(
        '--min-hunt-score',
        type=float,
        default=80.0,
        help='Minimum hunt score for articles (default: 80.0)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of articles to process'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/os_detection_training_data.json'),
        help='Output path for training data JSON file'
    )
    parser.add_argument(
        '--no-fallback',
        action='store_true',
        help='Disable LLM fallback (use only classifier/similarity)'
    )
    parser.add_argument(
        '--fallback-model',
        type=str,
        default=None,
        help='LMStudio model for fallback (default: mistralai/mistral-7b-instruct-v0.3)'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("OS DETECTION TRAINING DATA PREPARATION (LOCAL)")
    print("="*80)
    print("\nUsing existing OSDetectionService (CTI-BERT + LMStudio)")
    print("No OpenAI required!")
    
    # Load articles
    print(f"\nLoading articles with hunt_score >= {args.min_hunt_score}...")
    articles = load_articles(min_hunt_score=args.min_hunt_score, limit=args.limit)
    print(f"Loaded {len(articles)} articles")
    
    if not articles:
        print("No articles found. Exiting.")
        return
    
    # Prepare training data
    print(f"\nPreparing training data using local OS detection...")
    print(f"  Fallback enabled: {not args.no_fallback}")
    if args.fallback_model:
        print(f"  Fallback model: {args.fallback_model}")
    
    training_data = asyncio.run(
        prepare_training_data(
            articles,
            use_fallback=not args.no_fallback,
            fallback_model=args.fallback_model
        )
    )
    
    if not training_data:
        print("No training data generated. Exiting.")
        return
    
    # Save training data
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(training_data, f, indent=2)
    
    # Print summary
    print("\n" + "="*80)
    print("TRAINING DATA SUMMARY")
    print("="*80)
    
    os_counts = {}
    for item in training_data:
        os_label = item['os_label']
        os_counts[os_label] = os_counts.get(os_label, 0) + 1
    
    print(f"\nTotal samples: {len(training_data)}")
    print("\nOS Label Distribution:")
    for os_label in VALID_OS_LABELS:
        count = os_counts.get(os_label, 0)
        if count > 0:
            print(f"  {os_label}: {count}")
    
    print(f"\n✅ Training data saved to: {args.output}")
    print(f"\nNext step: Fine-tune BERT with:")
    print(f"  python scripts/finetune_os_bert.py --data {args.output}")


if __name__ == "__main__":
    main()

