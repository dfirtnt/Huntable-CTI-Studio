#!/usr/bin/env python3
"""Score multiple articles using LMStudio gpt-oss-20b with integer-only output."""

import httpx
import asyncio
import sys
import os
import subprocess
import json
import re
from collections import defaultdict

LMSTUDIO_URL = os.getenv("LMSTUDIO_API_URL", "http://localhost:1234/v1")
# Using fastest 7B model for testing - change this to your preferred fast model
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "qwen/qwen2.5-coder-32b")  # 32B model - ensure context length is set high
# Results file name based on model
MODEL_NAME_FOR_FILE = LMSTUDIO_MODEL.replace("/", "-").replace("_", "-")
RESULTS_FILE = f"lmstudio_scores_{MODEL_NAME_FOR_FILE}.json"

# LMStudio recommended settings
TEMPERATURE = 0.2
TOP_P = 0.9
SEED = 42

# Read the prompt template (original, no modifications)
with open("src/prompts/gpt4o_sigma_ranking.txt", "r") as f:
    prompt_template = f.read()

def extract_score(text):
    """Extract integer score from response."""
    text = text.strip()
    
    # Try to extract just the integer (pure integer response)
    match = re.search(r'^\s*(\d+)\s*$', text)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 10:
            return score
    
    # Try: SIGMA HUNTABILITY SCORE: 7 (with various formatting)
    match = re.search(r'SIGMA\s+HUNTABILITY\s+SCORE[:\s]+(\d+)', text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 10:
            return score
    
    # Try: Score: 7 or **Score:** 7 or ### Score: 7
    match = re.search(r'(?:Score|score|SCORE)[:\s#*]*\s*(\d+)', text, re.IGNORECASE)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 10:
            return score
    
    # Try: Any number 1-10 in the response (most permissive)
    match = re.search(r'\b([1-9]|10)\b', text)
    if match:
        score = int(match.group(1))
        return score
    
    return None

async def score_article(article_id, title, source, url, content, max_retries=3):
    """Score a single article using LMStudio gpt-oss-20b."""
    full_prompt = prompt_template.format(
        title=title,
        source=source,
        url=url,
        content=content
    )
    
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{LMSTUDIO_URL}/chat/completions",
                    headers={
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": LMSTUDIO_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": full_prompt
                            }
                        ],
                        "max_tokens": 2000,  # Match chat UI default
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P
                        # Removed seed - may cause deterministic newline behavior
                        # Chat UI doesn't use seed, matches working behavior
                    },
                    timeout=300.0  # Longer timeout for local models
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    print(f"Article {article_id}: Error {response.status_code}: {error_detail[:200]}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return None
                
                result = response.json()
                usage = result.get('usage', {})
                
                # Get content - handle cases where content might be empty or missing
                if 'choices' not in result or len(result['choices']) == 0:
                    print(f"Article {article_id}: No choices in response")
                    print(f"  Full response: {result}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                choice = result['choices'][0]
                message = choice.get('message', {})
                raw_content = message.get('content', '')
                score_text = raw_content.strip()
                
                # Check if response is empty or only newlines
                if not score_text:
                    print(f"Article {article_id}: Empty or newline-only response (attempt {attempt + 1})")
                    print(f"  Finish reason: {choice.get('finish_reason', 'unknown')}")
                    print(f"  Usage: {usage}")
                    print(f"  Raw content (first 100 chars): {repr(raw_content[:100])}")
                    
                    # Try extracting score from raw content even if it's mostly newlines
                    score_from_raw = extract_score(raw_content)
                    if score_from_raw:
                        print(f"  ✓ Found score {score_from_raw} despite newlines")
                        score_text = str(score_from_raw)  # Use found score
                    else:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        return None
                else:
                    score_from_raw = None
                
                # Extract score from cleaned text
                score = extract_score(score_text) if score_from_raw is None else score_from_raw
                if score is None:
                    print(f"Article {article_id}: Could not extract score from response:")
                    print(f"  Full response: {repr(score_text[:500])}")
                    print(f"  Response length: {len(score_text)} chars")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                return {
                    'article_id': article_id,
                    'score': score,
                    'raw_response': score_text[:100] if len(score_text) > 100 else score_text,
                    'input_tokens': usage.get('prompt_tokens', 0),
                    'output_tokens': usage.get('completion_tokens', 0)
                }
                
            except httpx.TimeoutException:
                print(f"Article {article_id}: Timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(10)
                    continue
                return None
            except Exception as e:
                print(f"Article {article_id}: Error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return None
    
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
    article_ids = [1974, 1909, 1866, 1860, 1937, 1794]
    
    # Load existing results to skip completed articles
    existing_results = load_results()
    
    # Filter out articles that already have 5 runs
    articles_needing_runs = []
    for aid in article_ids:
        existing_scores = existing_results.get(str(aid), [])
        if len(existing_scores) < 5:
            needed = 5 - len(existing_scores)
            articles_needing_runs.append((aid, needed))
        else:
            print(f"Skipping article {aid} - already has 5 runs (scores: {existing_scores})")
    
    if not articles_needing_runs:
        print(f"\nAll articles already have 5 runs! Nothing to do.")
        return {}
    
    # Fetch article data from database only for articles needing runs
    article_ids_to_fetch = [aid for aid, _ in articles_needing_runs]
    
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-F", "|", "-c", 
         f"SELECT a.id, a.title, a.canonical_url, s.name, a.content FROM articles a JOIN sources s ON a.source_id = s.id WHERE a.id IN ({','.join(map(str, article_ids_to_fetch))}) ORDER BY id;"],
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
            article_id = int(parts[0])
            existing_scores = existing_results.get(str(article_id), [])
            needed = 5 - len(existing_scores)
            articles.append({
                'id': article_id,
                'title': parts[1],
                'url': parts[2],
                'source': parts[3],
                'content': parts[4],
                'runs_needed': needed
            })
    
    print(f"\n{'='*60}")
    print(f"Run {run_number}/5 - Scoring {len(articles)} articles with LMStudio gpt-oss-20b")
    articles_info = [f"{a['id']} ({a['runs_needed']} needed)" for a in articles]
    print(f"Articles needing runs: {articles_info}")
    print(f"{'='*60}\n")
    
    # Score all articles sequentially (local model may not handle concurrent well)
    batch_results = {}
    
    for article in articles:
        article_id = article['id']
        runs_needed = article['runs_needed']
        
        # Reload results before processing this article (in case it was updated)
        current_results = load_results()
        current_count = len(current_results.get(str(article_id), []))
        
        # Recalculate needed runs (may have changed if script restarted)
        actually_needed = max(0, 5 - current_count)
        
        if actually_needed == 0:
            print(f"Skipping article {article_id} - already has 5 runs (loaded fresh)")
            continue
        
        if actually_needed != runs_needed:
            print(f"Article {article_id}: Adjusting runs needed from {runs_needed} to {actually_needed} (current: {current_count}/5)")
            runs_needed = actually_needed
        
        # Run only the number of scores needed for this article
        for run_idx in range(runs_needed):
            print(f"Scoring article {article_id} (run {current_count + run_idx + 1}/5)...")
            result = await score_article(
                article_id=article_id,
                title=article['title'],
                source=article['source'],
                url=article['url'],
                content=article['content']
            )
            
            if result:
                score = result['score']
                batch_results[result['article_id']] = batch_results.get(result['article_id'], [])
                batch_results[result['article_id']].append(score)
                tokens = result['input_tokens'] + result['output_tokens']
                print(f"  ✓ Article {result['article_id']}: Score = {score} (Tokens: {tokens})")
                
                # Save results immediately and show current progress
                all_results_temp = load_results()
                all_results_temp[str(result['article_id'])] = all_results_temp.get(str(result['article_id']), []) + [score]
                save_results(all_results_temp)
                
                # Show current progress for this article
                current_scores = all_results_temp[str(result['article_id'])]
                print(f"    Progress: {len(current_scores)}/5 runs - Current scores: {current_scores}")
                if len(current_scores) >= 2:
                    import statistics
                    median = statistics.median(current_scores)
                    print(f"    Current median: {median}")
            else:
                print(f"  ✗ Article {article_id}: Failed")
            
            # Small delay between runs
            await asyncio.sleep(2)
    
    print()
    return batch_results

async def main():
    """Run 5 batches and calculate medians."""
    all_results = load_results()
    
    print(f"LMStudio Configuration:")
    print(f"  URL: {LMSTUDIO_URL}")
    print(f"  Model: {LMSTUDIO_MODEL}")
    print(f"  Temperature: {TEMPERATURE}, Top-p: {TOP_P}, Seed: {SEED}")
    print()
    
    for run in range(1, 6):
        batch = await run_batch(run)
        if batch:
            for article_id, scores in batch.items():
                if isinstance(scores, list):
                    all_results[str(article_id)].extend(scores)
                else:
                    all_results[str(article_id)].append(scores)
            save_results(all_results)
        
        # Wait between runs
        if run < 5:
            print("Waiting 5 seconds before next run...\n")
            await asyncio.sleep(5)
    
    # Calculate and display medians
    print("\n" + "=" * 80)
    print("FINAL RESULTS - Median Scores (LMStudio gpt-oss-20b)")
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

