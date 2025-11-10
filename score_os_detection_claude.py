#!/usr/bin/env python3
"""Score OS detection performance using Claude Sonnet with JSON output evaluation."""

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

# Load OSDetectionAgent prompt
OS_DETECTION_PROMPT_PATH = "src/prompts/OSDetectionAgent"
if not os.path.exists(OS_DETECTION_PROMPT_PATH):
    print(f"Error: OSDetectionAgent prompt not found at {OS_DETECTION_PROMPT_PATH}")
    sys.exit(1)

with open(OS_DETECTION_PROMPT_PATH, 'r') as f:
    prompt_config_dict = json.load(f)

instructions_template = prompt_config_dict.get("instructions", "")

RESULTS_FILE = "claude_os_detection_scores.json"

VALID_OS_LABELS = ["Windows", "Linux", "MacOS", "multiple"]

def parse_os_detection_result(response_text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON OS detection result from LLM response."""
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
                if 'operating_system' in candidate_data:
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

def evaluate_detection(result: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate OS detection quality and return metrics."""
    metrics = {
        'json_valid': False,
        'has_operating_system': False,
        'operating_system': None,
        'is_valid_label': False,
        'error': None
    }
    
    if not result:
        metrics['error'] = 'No result to evaluate'
        return metrics
    
    metrics['json_valid'] = True
    
    if 'operating_system' in result:
        metrics['has_operating_system'] = True
        os_label = result['operating_system']
        if isinstance(os_label, str):
            metrics['operating_system'] = os_label
            metrics['is_valid_label'] = os_label in VALID_OS_LABELS
            if not metrics['is_valid_label']:
                metrics['error'] = f'Invalid OS label: {os_label}. Must be one of {VALID_OS_LABELS}'
        else:
            metrics['error'] = f'operating_system is not a string: {type(os_label)}'
    else:
        metrics['error'] = 'Missing operating_system field'
    
    return metrics

async def detect_os(article_id: int, title: str, source: str, url: str, content: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """Detect OS from a single article using Claude Sonnet."""
    user_prompt = f"""Title: {title}

URL: {url}

Content:

{content}

Determine which operating system the described behaviors target.

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
                        "max_tokens": 200,
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
                
                detected = parse_os_detection_result(response_text)
                if not detected:
                    print(f"Article {article_id}: Could not parse JSON (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                detected['raw_response'] = response_text[:500]
                detected['input_tokens'] = usage.get('input_tokens', 0)
                detected['output_tokens'] = usage.get('output_tokens', 0)
                detected['article_id'] = article_id
                
                return detected
                
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
    """Main function to detect OS from all articles."""
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
    
    print(f"Detecting OS from {len(articles)} articles with Claude Sonnet 4.5...\n")
    
    # Detect OS from all articles concurrently
    tasks = [detect_os(
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
            metrics = evaluate_detection(result)
            os_label = metrics['operating_system']
            
            article_id = result['article_id']
            if str(article_id) not in all_results:
                all_results[str(article_id)] = []
            
            all_results[str(article_id)].append({
                'operating_system': os_label,
                'is_valid_label': metrics['is_valid_label'],
                'json_valid': metrics['json_valid'],
                'metrics': metrics,
                'raw_response': result.get('raw_response', '')[:500]
            })
            
            # Anthropic pricing: $3/1M input, $15/1M output
            cost = (result['input_tokens'] / 1_000_000 * 3.00) + (result['output_tokens'] / 1_000_000 * 15.00)
            total_cost += cost
            
            print(f"Article {article_id}:")
            print(f"  OS: {os_label}")
            print(f"  Valid label: {metrics['is_valid_label']}")
            print(f"  JSON valid: {metrics['json_valid']}")
            print(f"  Tokens: {result['input_tokens'] + result['output_tokens']} (in: {result['input_tokens']}, out: {result['output_tokens']})")
            print(f"  Cost: ${cost:.6f}")
            if metrics['error']:
                print(f"  Error: {metrics['error']}")
            print()
    
    save_results(all_results)
    
    print("-" * 80)
    print(f"Total cost: ${total_cost:.6f} (${total_cost * 100:.2f} cents)")
    print(f"Average cost per article: ${total_cost / len([r for r in results if r]):.6f}")

if __name__ == "__main__":
    asyncio.run(main())

