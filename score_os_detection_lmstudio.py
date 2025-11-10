#!/usr/bin/env python3
"""Score OS detection performance using LMStudio models with JSON output evaluation."""

import httpx
import asyncio
import sys
import os
import subprocess
import json
import re
from collections import defaultdict
from typing import Dict, Any, Optional

LMSTUDIO_URL = os.getenv("LMSTUDIO_API_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL_OS_DETECTION", os.getenv("LMSTUDIO_MODEL", "meta-llama-3.1-8b-instruct"))
MODEL_NAME_FOR_FILE = LMSTUDIO_MODEL.replace("/", "-").replace("_", "-")
RESULTS_FILE = f"lmstudio_os_detection_{MODEL_NAME_FOR_FILE}.json"

# LMStudio recommended settings
TEMPERATURE = 0
TOP_P = 1
MAX_TOKENS = 200  # OS detection is simple, doesn't need many tokens
SEED = 42

VALID_OS_LABELS = ["Windows", "Linux", "MacOS", "multiple"]

# Load OSDetectionAgent prompt from database (same as workflow uses)
def load_prompt_from_database():
    """Load OSDetectionAgent prompt from database config."""
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-c", 
         "SELECT agent_prompts->'OSDetectionAgent' FROM agentic_workflow_config WHERE is_active = true ORDER BY version DESC LIMIT 1;"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0 or not result.stdout.strip():
        # Fallback to file system
        OS_DETECTION_PROMPT_PATH = "src/prompts/OSDetectionAgent"
        if not os.path.exists(OS_DETECTION_PROMPT_PATH):
            raise FileNotFoundError(f"OSDetectionAgent prompt not found in database or at {OS_DETECTION_PROMPT_PATH}")
        with open(OS_DETECTION_PROMPT_PATH, 'r') as f:
            prompt_config_dict = json.load(f)
        instructions_template = prompt_config_dict.get("instructions", "")
        return prompt_config_dict, instructions_template
    
    agent_prompt_data = json.loads(result.stdout.strip())
    prompt_str = agent_prompt_data.get("prompt", "")
    if isinstance(prompt_str, str):
        prompt_config_dict = json.loads(prompt_str)
    else:
        prompt_config_dict = prompt_str
    instructions_template = agent_prompt_data.get("instructions", "")
    
    return prompt_config_dict, instructions_template

# Load prompt
try:
    prompt_config_dict, instructions_template = load_prompt_from_database()
except FileNotFoundError:
    # Fallback to file system
    OS_DETECTION_PROMPT_PATH = "src/prompts/OSDetectionAgent"
    with open(OS_DETECTION_PROMPT_PATH, 'r') as f:
        prompt_config_dict = json.load(f)
    instructions_template = prompt_config_dict.get("instructions", "")

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
    
    # Look for JSON object at the end of response (reasoning models)
    json_candidates = []
    search_pos = 0
    while True:
        open_pos = response_text.find('{', search_pos)
        if open_pos == -1:
            break
        
        # Find matching closing brace
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
        # Prefer the one closest to the end
        json_candidates.sort(key=lambda x: x[0], reverse=True)
        return json_candidates[0][2]
    
    # Last resort: try parsing entire response
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

def truncate_content_for_model(content: str, model_name: str) -> str:
    """Truncate content to fit within model's context window."""
    # Estimate tokens: ~4 chars per token
    # Reserve: 500 tokens for prompt template + 200 tokens for output + 200 safety margin = 900 tokens overhead
    
    # Determine context window based on model
    if '1b' in model_name.lower():
        max_content_tokens = 200
    elif '3b' in model_name.lower():
        max_content_tokens = 2000
    elif '8b' in model_name.lower() or '7b' in model_name.lower():
        if 'llama-3' in model_name.lower() or 'mixtral' in model_name.lower():
            max_content_tokens = 6000
        else:
            max_content_tokens = 2000
    elif '13b' in model_name.lower() or '14b' in model_name.lower():
        max_content_tokens = 6000
    elif '32b' in model_name.lower():
        max_content_tokens = 10000
    elif '80b' in model_name.lower() or 'qwen3-next' in model_name.lower():
        max_content_tokens = 50000
    else:
        max_content_tokens = 2000
    
    max_content_chars = max_content_tokens * 4
    
    if len(content) <= max_content_chars:
        return content
    
    # Truncate at sentence boundary
    truncated = content[:max_content_chars]
    last_period = truncated.rfind(".")
    last_newline = truncated.rfind("\n")
    last_boundary = max(last_period, last_newline)
    
    if last_boundary > max_content_chars * 0.8:
        truncated = truncated[:last_boundary + 1]
    
    return truncated + "\n\n[Content truncated to fit model context window]"

async def detect_os(article_id: int, title: str, source: str, url: str, content: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """Detect OS from a single article using LMStudio."""
    # Truncate content to fit model context window
    truncated_content = truncate_content_for_model(content, LMSTUDIO_MODEL)
    
    # Build prompt using the database format (same as workflow)
    prompt_config_json = json.dumps(prompt_config_dict, indent=2)
    user_prompt = instructions_template.format(
        title=title,
        url=url,
        content=truncated_content,
        prompt_config=prompt_config_json
    )
    
    # Determine system message
    if "task" in prompt_config_dict:
        system_content = prompt_config_dict["task"]
    elif "role" in prompt_config_dict:
        system_content = prompt_config_dict["role"]
    else:
        system_content = "You are a detection engineer LLM."
    
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            try:
                # Handle system/user message separation
                use_system_message = any(x in LMSTUDIO_MODEL.lower() for x in ['llama-3', 'llama3', 'qwen', 'deepseek'])
                
                if use_system_message:
                    messages = [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_prompt}
                    ]
                else:
                    combined_prompt = f"{system_content}\n\n{user_prompt}"
                    messages = [{"role": "user", "content": combined_prompt}]
                
                response = await client.post(
                    f"{LMSTUDIO_URL}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": LMSTUDIO_MODEL,
                        "messages": messages,
                        "temperature": TEMPERATURE,
                        "top_p": TOP_P,
                        "max_tokens": MAX_TOKENS,
                        "seed": SEED
                    },
                    timeout=300.0
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
                
                if 'choices' not in result or len(result['choices']) == 0:
                    print(f"Article {article_id}: No choices in response")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                choice = result['choices'][0]
                message = choice.get('message', {})
                content_text = message.get('content', '')
                reasoning_text = message.get('reasoning_content', '')
                
                # For reasoning models, check reasoning_content first
                is_reasoning_model = 'deepseek-r1' in LMSTUDIO_MODEL.lower() or 'r1' in LMSTUDIO_MODEL.lower()
                
                if is_reasoning_model:
                    if reasoning_text and ('{' in reasoning_text or 'operating_system' in reasoning_text):
                        response_text = reasoning_text
                    elif content_text and ('{' in content_text or 'operating_system' in content_text):
                        response_text = content_text
                    else:
                        response_text = reasoning_text + '\n\n' + content_text if (reasoning_text and content_text) else (reasoning_text or content_text)
                else:
                    if content_text and (content_text.strip().startswith('{') or 'operating_system' in content_text):
                        response_text = content_text
                    elif reasoning_text and (reasoning_text.strip().startswith('{') or 'operating_system' in reasoning_text):
                        response_text = reasoning_text
                    else:
                        response_text = content_text + '\n\n' + reasoning_text if (content_text and reasoning_text) else (content_text or reasoning_text)
                
                if not response_text or len(response_text.strip()) == 0:
                    print(f"Article {article_id}: Empty response (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                # Check for truncation
                finish_reason = choice.get('finish_reason', '')
                if finish_reason == 'length':
                    print(f"Article {article_id}: Response truncated (finish_reason=length, max_tokens={MAX_TOKENS})")
                
                # Parse JSON
                detected = parse_os_detection_result(response_text)
                if not detected:
                    print(f"Article {article_id}: Could not parse JSON from response (attempt {attempt + 1})")
                    print(f"  Response length: {len(response_text)} chars")
                    print(f"  Finish reason: {finish_reason}")
                    print(f"  Response preview: {response_text[:300]}...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                # Add metadata
                detected['raw_response'] = response_text[:500]
                detected['input_tokens'] = usage.get('prompt_tokens', 0)
                detected['output_tokens'] = usage.get('completion_tokens', 0)
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

async def run_batch(run_number: int):
    """Run one batch of OS detection for all articles."""
    article_ids = [1974, 1909, 1866, 1860, 1937, 1794]
    
    # Load existing results
    existing_results = load_results()
    
    # Filter out articles that already have 1 run
    articles_needing_runs = []
    for aid in article_ids:
        existing_runs = existing_results.get(str(aid), [])
        if len(existing_runs) < 1:
            needed = 1 - len(existing_runs)
            articles_needing_runs.append((aid, needed))
        else:
            print(f"Skipping article {aid} - already has 1 run")
    
    if not articles_needing_runs:
        print(f"\nAll articles already have 1 run! Nothing to do.")
        return {}
    
    # Fetch article data from database
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
            existing_runs = existing_results.get(str(article_id), [])
            needed = 1 - len(existing_runs)
            articles.append({
                'id': article_id,
                'title': parts[1],
                'url': parts[2],
                'source': parts[3],
                'content': parts[4],
                'runs_needed': needed
            })
    
    print(f"\n{'='*60}")
    print(f"Detecting OS from {len(articles)} articles with {LMSTUDIO_MODEL}")
    articles_info = [f"{a['id']} ({a['runs_needed']} needed)" for a in articles]
    print(f"Articles needing runs: {articles_info}")
    print(f"{'='*60}\n")
    
    batch_results = {}
    
    for article in articles:
        article_id = article['id']
        runs_needed = article['runs_needed']
        
        # Reload results before processing
        current_results = load_results()
        current_count = len(current_results.get(str(article_id), []))
        actually_needed = max(0, 1 - current_count)
        
        if actually_needed == 0:
            print(f"Skipping article {article_id} - already has 1 run")
            continue
        
        if actually_needed != runs_needed:
            runs_needed = actually_needed
        
        for run_idx in range(runs_needed):
            print(f"Detecting OS from article {article_id}...")
            result = await detect_os(
                article_id=article_id,
                title=article['title'],
                source=article['source'],
                url=article['url'],
                content=article['content']
            )
            
            if result:
                # Evaluate detection
                metrics = evaluate_detection(result)
                os_label = metrics['operating_system']
                
                batch_results[article_id] = batch_results.get(article_id, [])
                batch_results[article_id].append({
                    'operating_system': os_label,
                    'is_valid_label': metrics['is_valid_label'],
                    'json_valid': metrics['json_valid'],
                    'metrics': metrics,
                    'result': result
                })
                
                tokens = result.get('input_tokens', 0) + result.get('output_tokens', 0)
                print(f"  ✓ Article {article_id}: OS = {os_label}, Valid = {metrics['is_valid_label']}, Tokens = {tokens}")
                
                # Save immediately
                all_results_temp = load_results()
                if str(article_id) not in all_results_temp:
                    all_results_temp[str(article_id)] = []
                all_results_temp[str(article_id)].append({
                    'operating_system': os_label,
                    'is_valid_label': metrics['is_valid_label'],
                    'json_valid': metrics['json_valid'],
                    'metrics': metrics,
                    'raw_response': result.get('raw_response', '')[:500]
                })
                save_results(all_results_temp)
                
                # Show progress
                current_runs = all_results_temp[str(article_id)]
                print(f"    Completed: {len(current_runs)}/1 run")
            else:
                print(f"  ✗ Article {article_id}: Failed")
            
            await asyncio.sleep(2)
    
    print()
    return batch_results

async def main():
    """Run OS detection and calculate statistics."""
    all_results = load_results()
    
    print(f"LMStudio Configuration:")
    print(f"  URL: {LMSTUDIO_URL}")
    print(f"  Model: {LMSTUDIO_MODEL}")
    print(f"  Temperature: {TEMPERATURE}, Top-p: {TOP_P}, Max Tokens: {MAX_TOKENS}, Seed: {SEED}")
    print()
    
    batch = await run_batch(1)
    all_results = load_results()
    if batch:
        for article_id, runs in batch.items():
            if str(article_id) not in all_results:
                all_results[str(article_id)] = []
    
    # Calculate and display statistics
    print("\n" + "=" * 80)
    print(f"FINAL RESULTS - OS Detection Performance ({LMSTUDIO_MODEL})")
    print("=" * 80)
    
    print(f"{'Article ID':<12} {'OS Labels':<30} {'Valid Label':<15} {'JSON Valid':<12}")
    print("-" * 80)
    
    for article_id in sorted([int(k) for k in all_results.keys()]):
        runs = all_results[str(article_id)]
        if runs:
            os_labels = [r['operating_system'] for r in runs]
            valid_count = sum(1 for r in runs if r.get('is_valid_label', False))
            json_valid_count = sum(1 for r in runs if r.get('json_valid', False))
            
            labels_str = ', '.join(os_labels)
            print(f"{article_id:<12} {labels_str:<30} {valid_count}/1{'':<10} {json_valid_count}/1")
    
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())

