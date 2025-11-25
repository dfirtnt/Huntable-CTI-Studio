#!/usr/bin/env python3
"""
Bootstrap OS Detection Training Data

Creates training data from existing CTI-BERT detection results.
Uses similarity scores to infer labels when explicit detection is uncertain.

Usage:
    python scripts/prepare_os_detection_training_data_bootstrap.py \
        --results ctibert_os_detection_scores.json \
        --output data/os_detection_training_data.json
"""

import sys
import os
import subprocess
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

VALID_OS_LABELS = ["Windows", "Linux", "MacOS", "multiple"]


def load_articles(article_ids: List[int]) -> List[Dict[str, Any]]:
    """Load articles from database by IDs."""
    if not article_ids:
        return []
    
    ids_str = ','.join(map(str, article_ids))
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
        WHERE a.id IN ({ids_str})
        AND a.archived = false
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
        return []


def infer_label_from_similarities(similarities: Dict[str, float], detected_os: str) -> str:
    """Infer OS label from similarity scores."""
    if not similarities:
        return "multiple"
    
    # If explicitly detected as Windows/Linux/MacOS with medium+ confidence, use that
    if detected_os in ["Windows", "Linux", "MacOS"]:
        return detected_os
    
    # Find OS with highest similarity
    max_os = max(similarities, key=similarities.get)
    max_sim = similarities[max_os]
    
    # If highest similarity is significantly higher (>0.05), use that OS
    sorted_sims = sorted(similarities.values(), reverse=True)
    if len(sorted_sims) > 1:
        diff = sorted_sims[0] - sorted_sims[1]
        if diff > 0.05 and max_sim > 0.5:
            return max_os
    
    # Otherwise, multiple OS
    return "multiple"


def create_training_data_from_results(
    results_file: Path,
    min_confidence: str = "low"
) -> List[Dict[str, Any]]:
    """Create training data from CTI-BERT detection results."""
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    training_data = []
    article_ids = []
    
    # Collect article IDs and their detection results
    for article_id_str, detections in results.items():
        if not detections:
            continue
        
        article_ids.append(int(article_id_str))
    
    # Load articles from database
    print(f"Loading {len(article_ids)} articles from database...")
    articles = load_articles(article_ids)
    
    # Create article lookup
    article_lookup = {a['id']: a for a in articles}
    
    # Process each article
    for article_id_str, detections in results.items():
        article_id = int(article_id_str)
        
        if article_id not in article_lookup:
            print(f"  ⚠️  Article {article_id} not found in database, skipping")
            continue
        
        article = article_lookup[article_id]
        
        # Use first detection result
        detection = detections[0] if detections else {}
        
        detected_os = detection.get('operating_system', 'multiple')
        similarities = detection.get('similarities', {})
        confidence = detection.get('confidence', 'low')
        
        # Infer label from similarities
        inferred_label = infer_label_from_similarities(similarities, detected_os)
        
        # For Windows detection, prioritize it
        if detected_os == "Windows" and confidence in ["medium", "high"]:
            os_label = "Windows"
        elif inferred_label == "Windows" and similarities.get('Windows', 0) > 0.55:
            # Windows has highest similarity and reasonable score
            os_label = "Windows"
        else:
            os_label = inferred_label
        
        training_data.append({
            "article_id": article_id,
            "title": article.get('title', ''),
            "url": article.get('url', ''),
            "content": article['content'],
            "os_label": os_label,
            "hunt_score": article.get('hunt_score', 0.0),
            "source": article.get('source', ''),
            "detected_os": detected_os,
            "confidence": confidence,
            "similarities": similarities,
            "labeled_at": datetime.now().isoformat(),
            "labeling_method": "bootstrap_from_ctibert"
        })
        
        print(f"  Article {article_id}: {detected_os} → {os_label} (conf={confidence}, sim={similarities.get('Windows', 0):.3f})")
    
    return training_data


def main():
    parser = argparse.ArgumentParser(description="Bootstrap OS detection training data from CTI-BERT results")
    parser.add_argument(
        '--results',
        type=Path,
        default=Path('ctibert_os_detection_scores.json'),
        help='Path to CTI-BERT detection results JSON file'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/os_detection_training_data.json'),
        help='Output path for training data JSON file'
    )
    parser.add_argument(
        '--min-confidence',
        type=str,
        choices=['low', 'medium', 'high'],
        default='low',
        help='Minimum confidence level to include (default: low)'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("OS DETECTION TRAINING DATA BOOTSTRAP")
    print("="*80)
    
    if not args.results.exists():
        print(f"Error: Results file not found: {args.results}")
        return
    
    print(f"\nLoading detection results from {args.results}...")
    training_data = create_training_data_from_results(args.results, args.min_confidence)
    
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
    print(f"\nNext step: Train classifier with:")
    print(f"  python3 scripts/train_os_detection_classifier_enhanced.py --data {args.output}")


if __name__ == "__main__":
    main()

