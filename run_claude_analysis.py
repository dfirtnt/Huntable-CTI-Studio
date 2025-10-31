#!/usr/bin/env python3
"""Run Claude 3.5 Sonnet analysis 5 times for all articles and calculate medians."""

import httpx
import asyncio
import subprocess
import json
import os
from collections import defaultdict
from email.utils import parsedate_to_datetime
from datetime import datetime

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    print("Error: ANTHROPIC_API_KEY environment variable not set")
    sys.exit(1)
RESULTS_FILE = "claude_scores.json"

# Read the prompt template
with open("src/prompts/gpt4o_sigma_ranking.txt", "r") as f:
    prompt_template = f.read()

# Modify prompt: add instruction before URL
instruction = "\nDo not explain, justify, or include any text besides the score.\n\nOutput format:\n\n[integer only]\n\n"
prompt_template = prompt_template.replace("**URL:** {url}", instruction + "**URL:** {url}")

async def score_article(article_id, title, source, url, content, max_retries=3):
    """Score a single article using Claude 3.5 Sonnet."""
    full_prompt = prompt_template.format(
        title=title,
        source=source,
        url=url,
        content=content
    )
    
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": API_KEY,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 2000,
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ]
                },
                timeout=120.0
            )
            
            if response.status_code == 429:
                # Rate limited - parse retry-after header and use exponential backoff
                retry_after_header = response.headers.get("retry-after")
                
                # Parse retry-after (seconds or HTTP date)
                retry_after = 30.0  # default
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header.strip())
                    except ValueError:
                        try:
                            retry_date = parsedate_to_datetime(retry_after_header)
                            now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                            delta = retry_date - now
                            retry_after = max(0.0, delta.total_seconds())
                        except (ValueError, TypeError):
                            retry_after = 30.0
                
                # Exponential backoff: max(retry_after, base_delay * 2^attempt)
                base_delay = 1.0
                max_delay = 60.0
                delay = max(retry_after, base_delay * (2 ** attempt))
                delay = min(delay, max_delay)
                
                if attempt < max_retries - 1:
                    print(f"Article {article_id}: Rate limited (429). Waiting {delay:.1f}s (retry-after: {retry_after:.1f}s) before retry {attempt+1}/{max_retries}...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"Article {article_id}: Rate limit exceeded after {max_retries} attempts")
                    return None
            
            if response.status_code != 200:
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                print(f"Article {article_id}: Error {response.status_code}")
                return None
        
        result = response.json()
        usage = result.get('usage', {})
        score_text = result['content'][0]['text'].strip()
        
        # Extract integer score
        try:
            score = int(score_text)
        except:
            score = score_text  # Keep raw if not integer
        
        return {
            'article_id': article_id,
            'score': score,
            'raw_response': score_text,
            'input_tokens': usage.get('input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0)
        }
    return None

def load_results():
    """Load previous results from file."""
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    return defaultdict(list)

def save_results(results):
    """Save results to file."""
    with open(RESULTS_FILE, 'w') as f:
        json.dump(dict(results), f, indent=2)

async def run_batch(run_number):
    """Run one batch of scoring for all articles."""
    article_ids = [1909, 1866, 1860, 1937, 1794]
    
    # Fetch article data from database
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-F", "|", "-c", 
         f"SELECT a.id, a.title, a.canonical_url, s.name, a.content FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.id IN ({','.join(map(str, article_ids))}) ORDER BY id;"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Database query failed: {result.stderr}")
        return None
    
    articles = []
    for line in result.stdout.strip().split('\n'):
        if not line or '|' not in line:
            continue
        parts = line.split('|', 4)
        if len(parts) >= 5:
            articles.append({
                'id': int(parts[0]),
                'title': parts[1],
                'url': parts[2],
                'source': parts[3],
                'content': parts[4]
            })
    
    print(f"\n{'='*60}")
    print(f"Run {run_number}/5 - Scoring {len(articles)} articles with Claude 3.5 Sonnet")
    print(f"{'='*60}\n")
    
    # Score all articles concurrently
    tasks = [score_article(
        article_id=article['id'],
        title=article['title'],
        source=article['source'],
        url=article['url'],
        content=article['content']
    ) for article in articles]
    results = await asyncio.gather(*tasks)
    
    # Print and save results
    batch_results = {}
    total_cost = 0
    
    print("Results:")
    print("-" * 60)
    for result in results:
        if result:
            cost = (result['input_tokens'] / 1_000_000 * 3.00) + (result['output_tokens'] / 1_000_000 * 15.00)
            total_cost += cost
            score = result['score']
            batch_results[result['article_id']] = score
            print(f"Article {result['article_id']}: Score = {score}")
            print(f"  Tokens: {result['input_tokens'] + result['output_tokens']} (in: {result['input_tokens']}, out: {result['output_tokens']})")
            print(f"  Cost: ${cost:.6f}")
            print()
    
    print(f"Total cost for this run: ${total_cost:.6f} (${total_cost * 100:.2f} cents)")
    print()
    
    return batch_results

async def main():
    """Run 5 batches and calculate medians."""
    all_results = load_results()
    
    for run in range(1, 6):
        batch = await run_batch(run)
        if batch:
            for article_id, score in batch.items():
                all_results[str(article_id)].append(score)
            save_results(all_results)
        
        # Wait between runs to avoid rate limits
        if run < 5:
            print("Waiting 10 seconds before next run...\n")
            await asyncio.sleep(10)
    
    # Calculate and display medians
    print("\n" + "=" * 80)
    print("FINAL RESULTS - Median Scores (Claude 3.5 Sonnet)")
    print("=" * 80)
    
    import statistics
    
    print(f"{'Article ID':<12} {'Scores':<25} {'Median':<8} {'Mean':<8} {'Variance':<10}")
    print("-" * 80)
    
    for article_id in sorted([int(k) for k in all_results.keys()]):
        scores = all_results[str(article_id)]
        if scores:
            median = statistics.median(scores)
            mean = statistics.mean(scores)
            variance = statistics.variance(scores) if len(set(scores)) > 1 else 0.0
            scores_str = ', '.join(map(str, sorted(scores)))
            print(f"{article_id:<12} {scores_str:<25} {median:<8} {mean:<8.2f} {variance:<10.2f}")
    
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())

