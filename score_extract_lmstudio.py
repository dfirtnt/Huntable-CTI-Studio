#!/usr/bin/env python3
"""Score extract agent performance using LMStudio models with JSON output evaluation."""

import httpx
import asyncio
import sys
import os
import subprocess
import json
import re
from collections import defaultdict
from typing import Dict, Any, Optional
from datetime import datetime

LMSTUDIO_URL = os.getenv("LMSTUDIO_API_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL_EXTRACT", os.getenv("LMSTUDIO_MODEL", "meta-llama-3.1-8b-instruct"))
MODEL_NAME_FOR_FILE = LMSTUDIO_MODEL.replace("/", "-").replace("_", "-")
RESULTS_FILE = f"lmstudio_extract_{MODEL_NAME_FOR_FILE}.json"

# LMStudio recommended settings
TEMPERATURE = 0
TOP_P = 1
# For reasoning models (deepseek-r1), need much higher token limit
# Reasoning models output reasoning first, then JSON, so need ~4000-6000 tokens
MAX_TOKENS = 6000  # Increased for reasoning models like deepseek-r1
SEED = 42

# Load ExtractAgent prompt from database (same as workflow uses)
def load_prompt_from_database():
    """Load ExtractAgent prompt from database config."""
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-c", 
         "SELECT agent_prompts->'ExtractAgent' FROM agentic_workflow_config WHERE is_active = true ORDER BY version DESC LIMIT 1;"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0 or not result.stdout.strip():
        # Fallback to file system
        EXTRACT_PROMPT_PATH = "src/prompts/ExtractAgent"
        if not os.path.exists(EXTRACT_PROMPT_PATH):
            raise FileNotFoundError(f"ExtractAgent prompt not found in database or at {EXTRACT_PROMPT_PATH}")
        with open(EXTRACT_PROMPT_PATH, 'r') as f:
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
prompt_config_dict, instructions_template = load_prompt_from_database()

def parse_extraction_result(response_text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON extraction result from LLM response."""
    if not response_text or len(response_text.strip()) == 0:
        return None
    
    # Clean up common formatting issues
    # Remove double braces at start (some models output {{ instead of {)
    cleaned = response_text.strip()
    if cleaned.startswith('{{'):
        cleaned = cleaned[1:]  # Remove one extra {
    if cleaned.endswith('}}'):
        cleaned = cleaned[:-1]  # Remove one extra }
    
    # Try to extract JSON from markdown code fences
    code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', cleaned, re.DOTALL)
    if code_fence_match:
        json_text = code_fence_match.group(1).strip()
        # Clean double braces in code fence too
        if json_text.startswith('{{'):
            json_text = json_text[1:]
        if json_text.endswith('}}'):
            json_text = json_text[:-1]
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass
    
    # Look for JSON object at the end of response (reasoning models)
    # Note: cleaned already has double braces removed at start/end
    json_candidates = []
    search_pos = 0
    while True:
        open_pos = cleaned.find('{', search_pos)
        if open_pos == -1:
            break
        
        # Find matching closing brace
        brace_count = 0
        json_end = -1
        for i in range(open_pos, len(cleaned)):
            if cleaned[i] == '{':
                brace_count += 1
            elif cleaned[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        
        if json_end != -1:
            candidate_json = cleaned[open_pos:json_end]
            try:
                candidate_data = json.loads(candidate_json)
                # Check for expected keys (support both old and new formats)
                expected_keys = ['behavioral_observables', 'observable_list', 'discrete_huntables_count', 'observables', 'summary']
                if any(key in candidate_data for key in expected_keys):
                    json_candidates.append((open_pos, json_end, candidate_data))
            except json.JSONDecodeError:
                pass
        
        search_pos = open_pos + 1
    
    if json_candidates:
        # Prefer the one closest to the end
        json_candidates.sort(key=lambda x: x[0], reverse=True)
        return json_candidates[0][2]
    
    # Try to extract partial JSON if response is truncated
    # Look for incomplete JSON structure and try to complete it
    if cleaned.strip().startswith('{') or cleaned.strip().startswith('{{'):
        # Try to find the last complete observable entry
        last_complete_brace = cleaned.rfind('}')
        if last_complete_brace > 0:
            # Try to find a complete structure before the truncation
            # Look for closing of observables array and summary
            partial_json = cleaned[:last_complete_brace + 1]
            # Clean double braces
            if partial_json.startswith('{{'):
                partial_json = partial_json[1:]
            if partial_json.endswith('}}'):
                partial_json = partial_json[:-1]
            # Try to close incomplete structures
            if partial_json.count('[') > partial_json.count(']'):
                # Array not closed, try to close it
                partial_json += ']'
            if partial_json.count('{') > partial_json.count('}'):
                # Object not closed, try to close it
                partial_json += '}'
            try:
                parsed = json.loads(partial_json)
                # If we got something useful, return it
                if 'observables' in parsed or 'summary' in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass
    
    # Last resort: try parsing entire response (with double brace cleanup)
    try:
        final_json = cleaned
        if final_json.startswith('{{'):
            final_json = final_json[1:]
        if final_json.endswith('}}'):
            final_json = final_json[:-1]
        return json.loads(final_json)
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
    
    # Check discrete_huntables_count (old format) or summary.count (new format)
    if 'discrete_huntables_count' in result:
        metrics['has_discrete_count'] = True
        count = result['discrete_huntables_count']
        if isinstance(count, (int, float)):
            metrics['discrete_count'] = int(count)
        else:
            metrics['error'] = f'discrete_huntables_count is not a number: {count}'
    elif 'summary' in result and isinstance(result['summary'], dict):
        summary = result['summary']
        if 'count' in summary:
            metrics['has_discrete_count'] = True
            count = summary['count']
            if isinstance(count, (int, float)):
                metrics['discrete_count'] = int(count)
            else:
                metrics['error'] = f'summary.count is not a number: {count}'
    
    # Check behavioral_observables (old format) or observables (new format)
    if 'behavioral_observables' in result:
        metrics['has_behavioral_observables'] = True
        behav = result['behavioral_observables']
        if isinstance(behav, list):
            metrics['behavioral_observables_count'] = len(behav)
        else:
            metrics['error'] = f'behavioral_observables is not a list: {type(behav)}'
    elif 'observables' in result:
        metrics['has_behavioral_observables'] = True
        observables = result['observables']
        if isinstance(observables, list):
            metrics['behavioral_observables_count'] = len(observables)
        else:
            metrics['error'] = f'observables is not a list: {type(observables)}'
    
    # Check observable_list (old format)
    if 'observable_list' in result:
        metrics['has_observable_list'] = True
        obs_list = result['observable_list']
        if isinstance(obs_list, list):
            metrics['observable_list_count'] = len(obs_list)
        else:
            metrics['error'] = f'observable_list is not a list: {type(obs_list)}'
    
    # Check content
    if 'content' in result:
        metrics['has_content'] = True
        content = result['content']
        if isinstance(content, str):
            metrics['content_length'] = len(content)
    
    # Check url
    if 'url' in result:
        metrics['has_url'] = True
    
    return metrics

def truncate_content_for_model(content: str, model_name: str) -> str:
    """Truncate content to fit within model's context window."""
    # Estimate tokens: ~4 chars per token
    # Reserve: 500 tokens for prompt template + 1200 tokens for output + 200 safety margin = 1900 tokens overhead
    
    # Determine context window based on model
    if '1b' in model_name.lower():
        max_content_tokens = 200  # 2048 context - 1900 overhead = ~150 tokens (~600 chars)
    elif '3b' in model_name.lower():
        max_content_tokens = 2000  # 4096 context - 1900 overhead = ~2200 tokens (~8800 chars)
    elif '8b' in model_name.lower() or '7b' in model_name.lower():
        # Most 7B/8B models have 4096 context, some have 8192
        if 'llama-3' in model_name.lower() or 'mixtral' in model_name.lower():
            max_content_tokens = 6000  # 8192 context - 1900 overhead = ~6300 tokens (~25200 chars)
        else:
            max_content_tokens = 2000  # 4096 context - 1900 overhead = ~2200 tokens (~8800 chars)
    elif '13b' in model_name.lower() or '14b' in model_name.lower():
        # Qwen2.5-14b-coder has 8192 context, but be more conservative for longer articles
        max_content_tokens = 5000  # 8192 context - 1900 overhead - 1000 safety = ~5300 tokens (~21200 chars)
    elif '32b' in model_name.lower():
        max_content_tokens = 10000  # Larger context windows
    elif '80b' in model_name.lower() or 'qwen3-next' in model_name.lower():
        # Qwen3-Next-80B supports 262K context, but we'll be conservative
        max_content_tokens = 50000  # 262K context - 1900 overhead = ~260K tokens available
    else:
        max_content_tokens = 2000  # Conservative default (4096 context)
    
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

async def extract_article(article_id: int, title: str, source: str, url: str, content: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """Extract observables from a single article using LMStudio."""
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
                # Use system message if model supports it, otherwise combine
                use_system_message = any(x in LMSTUDIO_MODEL.lower() for x in ['llama-3', 'llama3', 'qwen', 'deepseek'])
                
                if use_system_message:
                    messages = [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_prompt}
                    ]
                else:
                    # For models that don't support system messages, combine into user message
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
                
                # For reasoning models (deepseek-r1), JSON is typically in reasoning_content
                # Check reasoning_content first for reasoning models, then content
                is_reasoning_model = 'deepseek-r1' in LMSTUDIO_MODEL.lower() or 'r1' in LMSTUDIO_MODEL.lower()
                
                if is_reasoning_model:
                    # Reasoning models: prefer reasoning_content (contains JSON), fallback to content
                    if reasoning_text and ('{' in reasoning_text or 'observables' in reasoning_text):
                        response_text = reasoning_text
                    elif content_text and ('{' in content_text or 'observables' in content_text):
                        response_text = content_text
                    else:
                        response_text = reasoning_text + '\n\n' + content_text if (reasoning_text and content_text) else (reasoning_text or content_text)
                else:
                    # Non-reasoning models: prefer content, then reasoning_content
                    if content_text and (content_text.strip().startswith('{') or 'behavioral_observables' in content_text):
                        response_text = content_text
                    elif reasoning_text and (reasoning_text.strip().startswith('{') or 'behavioral_observables' in reasoning_text):
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
                extracted = parse_extraction_result(response_text)
                if not extracted:
                    print(f"Article {article_id}: Could not parse JSON from response (attempt {attempt + 1})")
                    print(f"  Response length: {len(response_text)} chars")
                    print(f"  Finish reason: {finish_reason}")
                    print(f"  Response preview: {response_text[:300]}...")
                    print(f"  Response end: ...{response_text[-200:]}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                # Add metadata
                extracted['raw_response'] = response_text[:500]  # Store first 500 chars
                extracted['input_tokens'] = usage.get('prompt_tokens', 0)
                extracted['output_tokens'] = usage.get('completion_tokens', 0)
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

def get_timestamped_filename(base_filename: str) -> str:
    """Generate timestamped filename for preserving each run."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    base, ext = os.path.splitext(base_filename)
    return f"{base}_{timestamp}{ext}"

def save_results(results):
    """Save results to file."""
    with open(RESULTS_FILE, 'w') as f:
        json.dump(dict(results), f, indent=2)
    
    # Also save timestamped copy for this run
    timestamped_file = get_timestamped_filename(RESULTS_FILE)
    with open(timestamped_file, 'w') as f:
        json.dump(dict(results), f, indent=2)

async def run_batch(run_number: int):
    """Run one batch of extraction for all articles."""
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
    print(f"Extracting from {len(articles)} articles with {LMSTUDIO_MODEL}")
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
            print(f"Extracting from article {article_id}...")
            result = await extract_article(
                article_id=article_id,
                title=article['title'],
                source=article['source'],
                url=article['url'],
                content=article['content']
            )
            
            if result:
                # Evaluate extraction
                metrics = evaluate_extraction(result)
                discrete_count = metrics['discrete_count']
                
                batch_results[article_id] = batch_results.get(article_id, [])
                batch_results[article_id].append({
                    'discrete_count': discrete_count,
                    'behavioral_count': metrics['behavioral_observables_count'],
                    'observable_list_count': metrics['observable_list_count'],
                    'json_valid': metrics['json_valid'],
                    'metrics': metrics,
                    'result': result  # Store full result for analysis
                })
                
                tokens = result.get('input_tokens', 0) + result.get('output_tokens', 0)
                print(f"  ✓ Article {article_id}: Discrete count = {discrete_count}, Behavioral = {metrics['behavioral_observables_count']}, Tokens = {tokens}")
                
                # Save immediately
                all_results_temp = load_results()
                if str(article_id) not in all_results_temp:
                    all_results_temp[str(article_id)] = []
                all_results_temp[str(article_id)].append({
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
    """Run extraction and calculate statistics."""
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
            # Results already saved in run_batch
    
    # Calculate and display statistics
    print("\n" + "=" * 80)
    print(f"FINAL RESULTS - Extract Agent Performance ({LMSTUDIO_MODEL})")
    print("=" * 80)
    
    import statistics
    
    print(f"{'Article ID':<12} {'Discrete Counts':<30} {'Median':<8} {'Mean':<8} {'Variance':<10} {'JSON Valid':<12}")
    print("-" * 80)
    
    for article_id in sorted([int(k) for k in all_results.keys()]):
        runs = all_results[str(article_id)]
        if runs:
            discrete_counts = [r['discrete_count'] for r in runs]
            json_valid_count = sum(1 for r in runs if r.get('json_valid', False))
            
            median = statistics.median(discrete_counts) if discrete_counts else 0
            mean = statistics.mean(discrete_counts) if discrete_counts else 0
            variance = statistics.variance(discrete_counts) if len(set(discrete_counts)) > 1 else 0.0
            
            counts_str = ', '.join(map(str, sorted(discrete_counts)))
            print(f"{article_id:<12} {counts_str:<30} {median:<8} {mean:<8.2f} {variance:<10.2f} {json_valid_count}/5")
    
    print("=" * 80)
    print(f"\nResults saved to: {RESULTS_FILE}")
    print(f"Timestamped copy saved to: {get_timestamped_filename(RESULTS_FILE)}")

if __name__ == "__main__":
    asyncio.run(main())

