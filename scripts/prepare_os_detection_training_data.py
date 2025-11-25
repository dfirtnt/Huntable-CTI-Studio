#!/usr/bin/env python3
"""
Prepare training data for OS detection classifier.

This script:
1. Queries articles from database (high hunt_score articles)
2. Uses LLM (GPT-4o) to label articles with OS labels
3. Exports training data in JSON format for classifier training
"""

import sys
import os
import subprocess
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import asyncio
from openai import OpenAI

# Load OSDetectionAgent prompt for reference
OS_DETECTION_PROMPT_PATH = Path(__file__).parent.parent / "src" / "prompts" / "OSDetectionAgent"
if not OS_DETECTION_PROMPT_PATH.exists():
    print(f"Error: OSDetectionAgent prompt not found at {OS_DETECTION_PROMPT_PATH}")
    sys.exit(1)

with open(OS_DETECTION_PROMPT_PATH, 'r') as f:
    prompt_config_dict = json.load(f)

VALID_OS_LABELS = ["Windows", "Linux", "MacOS", "multiple"]


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


async def label_article_with_llm(
    article: Dict[str, Any],
    client: OpenAI,
    model: str = "gpt-4o"
) -> Optional[str]:
    """Use LLM to label article with OS."""
    
    instructions = prompt_config_dict.get("instructions", "")
    
    # Prepare content sample (first 3000 chars for context)
    content_sample = article['content'][:3000]
    
    prompt = f"""{instructions}

Article Title: {article['title']}
Article URL: {article.get('url', 'N/A')}

Content:
{content_sample}

Based on the content above, determine which operating system(s) this threat intelligence article focuses on. 
Respond with ONLY a valid JSON object in this exact format:
{{
    "operating_system": "Windows" | "Linux" | "MacOS" | "multiple"
}}

Do not include any other text, markdown, or explanation. Only the JSON object."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at analyzing cybersecurity threat intelligence articles to identify target operating systems."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=50
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        result = json.loads(content)
        os_label = result.get("operating_system", "multiple")
        
        if os_label not in VALID_OS_LABELS:
            print(f"  ⚠️  Invalid label '{os_label}', defaulting to 'multiple'")
            os_label = "multiple"
        
        return os_label
        
    except Exception as e:
        print(f"  ✗ LLM labeling failed: {e}")
        return None


async def prepare_training_data(
    articles: List[Dict[str, Any]],
    use_llm_labeling: bool = True,
    llm_model: str = "gpt-4o",
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Prepare training data from articles."""
    
    training_data = []
    client = None
    
    if use_llm_labeling:
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Error: OPENAI_API_KEY not set. Cannot use LLM labeling.")
            return []
        client = OpenAI(api_key=api_key)
    
    for i, article in enumerate(articles, 1):
        article_id = article['id']
        hunt_score = article.get('hunt_score', 0.0)
        
        print(f"[{i}/{len(articles)}] Article {article_id} (hunt_score={hunt_score:.1f})...", end=" ")
        
        if use_llm_labeling and client:
            os_label = await label_article_with_llm(article, client, llm_model)
            if os_label:
                print(f"✓ Labeled as: {os_label}")
            else:
                print("✗ Failed to label")
                continue
        else:
            # Manual labeling - skip for now
            print("⚠️  Skipping (manual labeling not implemented)")
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
            "labeling_method": "llm" if use_llm_labeling else "manual"
        })
    
    return training_data


def main():
    parser = argparse.ArgumentParser(description="Prepare OS detection training data")
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
        '--no-llm',
        action='store_true',
        help='Skip LLM labeling (for manual labeling workflow)'
    )
    parser.add_argument(
        '--llm-model',
        type=str,
        default='gpt-4o',
        help='LLM model to use for labeling (default: gpt-4o)'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='OpenAI API key (defaults to OPENAI_API_KEY env var)'
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("OS DETECTION TRAINING DATA PREPARATION")
    print("="*80)
    
    # Load articles
    print(f"\nLoading articles with hunt_score >= {args.min_hunt_score}...")
    articles = load_articles(min_hunt_score=args.min_hunt_score, limit=args.limit)
    print(f"Loaded {len(articles)} articles")
    
    if not articles:
        print("No articles found. Exiting.")
        return
    
    # Prepare training data
    print(f"\nPreparing training data (LLM labeling: {not args.no_llm})...")
    training_data = asyncio.run(
        prepare_training_data(
            articles,
            use_llm_labeling=not args.no_llm,
            llm_model=args.llm_model,
            api_key=args.api_key
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
    print(f"\nNext step: Train classifier with:")
    print(f"  python scripts/train_os_detection_classifier.py --data {args.output}")


if __name__ == "__main__":
    main()

