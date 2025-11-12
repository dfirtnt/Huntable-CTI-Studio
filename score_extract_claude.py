#!/usr/bin/env python3
"""Score extract agent performance using Claude Sonnet 3.5 with JSON output evaluation."""

import httpx
import asyncio
import sys
import os
import subprocess
import json
import re
from collections import defaultdict
from typing import Dict, Any, Optional
from email.utils import parsedate_to_datetime
from datetime import datetime

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    print("Error: ANTHROPIC_API_KEY environment variable not set")
    sys.exit(1)

# Load ExtractAgent prompt
EXTRACT_PROMPT_PATH = "src/prompts/ExtractAgent"
if not os.path.exists(EXTRACT_PROMPT_PATH):
    print(f"Error: ExtractAgent prompt not found at {EXTRACT_PROMPT_PATH}")
    sys.exit(1)

with open(EXTRACT_PROMPT_PATH, 'r') as f:
    prompt_config_dict = json.load(f)

instructions_template = prompt_config_dict.get("instructions", "")

RESULTS_FILE = "claude_extract_scores.json"

def parse_extraction_result(response_text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON extraction result from LLM response."""
    if not response_text or len(response_text.strip()) == 0:
        return None
    
    # Try to extract JSON from markdown code fences
    code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
    if code_fence_match:
        json_text = code_fence_match.group(1).strip()
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass
    
    # Look for JSON object
    json_candidates = []
    search_pos = 0
    while True:
        open_pos = response_text.find('{', search_pos)
        if open_pos == -1:
            break
        
        brace_count = 0
        json_end = -1
        for i in range(open_pos, len(response_text)):
            if response_text[i] == '{':
                brace_count += 1
            elif response_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        
        if json_end != -1:
            candidate_json = response_text[open_pos:json_end]
            try:
                candidate_data = json.loads(candidate_json)
                expected_keys = ['behavioral_observables', 'observable_list', 'discrete_huntables_count']
                if any(key in candidate_data for key in expected_keys):
                    json_candidates.append((open_pos, json_end, candidate_data))
            except json.JSONDecodeError:
                pass
        
        search_pos = open_pos + 1
    
    if json_candidates:
        json_candidates.sort(key=lambda x: x[0], reverse=True)
        return json_candidates[0][2]
    
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        return None

def evaluate_extraction(result: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate extraction quality and return metrics."""
    metrics = {
        'json_valid': False,
        'has_discrete_count': False,
        'discrete_count': 0,
        'has_behavioral_observables': False,
        'behavioral_observables_count': 0,
        'has_observable_list': False,
        'observable_list_count': 0,
        'has_content': False,
        'content_length': 0,
        'has_url': False,
        'error': None
    }
    
    if not result:
        metrics['error'] = 'No result to evaluate'
        return metrics
    
    metrics['json_valid'] = True
    
    if 'discrete_huntables_count' in result:
        metrics['has_discrete_count'] = True
        count = result['discrete_huntables_count']
        if isinstance(count, (int, float)):
            metrics['discrete_count'] = int(count)
        else:
            metrics['error'] = f'discrete_huntables_count is not a number: {count}'
    
    if 'behavioral_observables' in result:
        metrics['has_behavioral_observables'] = True
        behav = result['behavioral_observables']
        if isinstance(behav, list):
            metrics['behavioral_observables_count'] = len(behav)
        else:
            metrics['error'] = f'behavioral_observables is not a list: {type(behav)}'
    
    if 'observable_list' in result:
        metrics['has_observable_list'] = True
        obs_list = result['observable_list']
        if isinstance(obs_list, list):
            metrics['observable_list_count'] = len(obs_list)
        else:
            metrics['error'] = f'observable_list is not a list: {type(obs_list)}'
    
    if 'content' in result:
        metrics['has_content'] = True
        content = result['content']
        if isinstance(content, str):
            metrics['content_length'] = len(content)
    
    if 'url' in result:
        metrics['has_url'] = True
    
    return metrics

async def extract_article(article_id: int, title: str, source: str, url: str, content: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """Extract observables from a single article using Claude Sonnet 3.5."""
    user_prompt = f"""Title: {title}

URL: {url}

Content:

{content}

Extract telemetry-relevant attacker behaviors and observables.

{json.dumps(prompt_config_dict, indent=2)}

{instructions_template}"""
    
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": API_KEY,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": "claude-sonnet-4-5",
                        "max_tokens": 1200,
                        "temperature": 0,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_prompt
                            }
                        ]
                    },
                    timeout=180.0
                )
                
                if response.status_code == 429:
                    retry_after_header = response.headers.get("retry-after")
                    retry_after = 30.0
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
                    
                    base_delay = 1.0
                    max_delay = 60.0
                    delay = max(retry_after, base_delay * (2 ** attempt))
                    delay = min(delay, max_delay)
                    
                    if attempt < max_retries - 1:
                        print(f"Article {article_id}: Rate limited. Waiting {delay:.1f}s...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        print(f"Article {article_id}: Rate limit exceeded")
                        return None
                
                if response.status_code != 200:
                    print(f"Article {article_id}: Error {response.status_code}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                    return None
                
                result = response.json()
                usage = result.get('usage', {})
                response_text = result['content'][0]['text'].strip()
                
                if not response_text:
                    print(f"Article {article_id}: Empty response (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                extracted = parse_extraction_result(response_text)
                if not extracted:
                    print(f"Article {article_id}: Could not parse JSON (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                extracted['raw_response'] = response_text[:500]
                extracted['input_tokens'] = usage.get('input_tokens', 0)
                extracted['output_tokens'] = usage.get('output_tokens', 0)
                extracted['article_id'] = article_id
                
                return extracted
                
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

async def main():
    """Main function to extract from all articles."""
    article_ids = [1974, 1909, 1866, 1860, 1937, 1794]
    
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
        return
    
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
    
    print(f"Extracting from {len(articles)} articles with Claude Sonnet 3.5...\n")
    
    # Extract from all articles concurrently
    tasks = [extract_article(
        article_id=article['id'],
        title=article['title'],
        source=article['source'],
        url=article['url'],
        content=article['content']
    ) for article in articles]
    results = await asyncio.gather(*tasks)
    
    # Evaluate and print results
    print("\nResults:")
    print("-" * 80)
    total_cost = 0
    all_results = load_results()
    
    for result in results:
        if result:
            metrics = evaluate_extraction(result)
            discrete_count = metrics['discrete_count']
            
            article_id = result['article_id']
            if str(article_id) not in all_results:
                all_results[str(article_id)] = []
            
            all_results[str(article_id)].append({
                'discrete_count': discrete_count,
                'behavioral_count': metrics['behavioral_observables_count'],
                'observable_list_count': metrics['observable_list_count'],
                'json_valid': metrics['json_valid'],
                'metrics': metrics,
                # Store full extraction details
                'observables': result.get('observables', []),
                'behavioral_observables': result.get('behavioral_observables', []),
                'observable_list': result.get('observable_list', []),
                'summary': result.get('summary', {}),
                'raw_response': result.get('raw_response', '')[:1000]  # First 1000 chars
            })
            
            # Anthropic pricing: $3/1M input, $15/1M output
            cost = (result['input_tokens'] / 1_000_000 * 3.00) + (result['output_tokens'] / 1_000_000 * 15.00)
            total_cost += cost
            
            print(f"Article {article_id}:")
            print(f"  Discrete count: {discrete_count}")
            print(f"  Behavioral observables: {metrics['behavioral_observables_count']}")
            print(f"  Observable list: {metrics['observable_list_count']}")
            print(f"  JSON valid: {metrics['json_valid']}")
            print(f"  Tokens: {result['input_tokens'] + result['output_tokens']} (in: {result['input_tokens']}, out: {result['output_tokens']})")
            print(f"  Cost: ${cost:.6f}")
            print()
    
    save_results(all_results)
    
    print("-" * 80)
    print(f"Total cost: ${total_cost:.6f} (${total_cost * 100:.2f} cents)")
    print(f"Average cost per article: ${total_cost / len([r for r in results if r]):.6f}")

if __name__ == "__main__":
    asyncio.run(main())

