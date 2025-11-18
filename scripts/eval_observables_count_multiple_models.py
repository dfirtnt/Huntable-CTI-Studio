#!/usr/bin/env python3
"""
Evaluate ObservablesCountAgent with multiple LLM models.

Tests all LLM models (excluding BERT) against articles from OSDetection evaluation.
"""

import sys
import asyncio
import json
import argparse
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.utils.content_filter import ContentFilter
from src.services.llm_service import LLMService
import httpx

# Import the manual test data
from scripts.eval_os_detection_manual import MANUAL_TEST_DATA


# LLM models for ObservablesCountAgent (excluding BERT models)
LLM_MODELS = {
    'deepseek-r1-qwen3-8b': {
        'model_name': 'deepseek/deepseek-r1-0528-qwen3-8b',
        'description': 'DeepSeek R1 Qwen3 8B (reasoning model)'
    },
    'mistral-7b': {
        'model_name': 'mistralai/mistral-7b-instruct-v0.3',
        'description': 'Mistral 7B Instruct'
    },
    'qwen3-4b': {
        'model_name': 'qwen/qwen3-4b-2507',
        'description': 'Qwen3 4B 2507'
    },
    'qwen2-7b': {
        'model_name': 'qwen2-7b-instruct',
        'description': 'Qwen2 7B Instruct'
    },
    'llama-3.1-8b': {
        'model_name': 'meta-llama-3.1-8b-instruct',
        'description': 'Llama 3.1 8B Instruct'
    },
    'llama-3-8b': {
        'model_name': 'meta-llama-3-8b-instruct',
        'description': 'Llama 3 8B Instruct'
    },
    'llama-3-13b': {
        'model_name': 'meta-llama-3-13b-instruct',
        'description': 'Llama 3 13B Instruct'
    },
    'llama-3.3-70b': {
        'model_name': 'meta/llama-3.3-70b',
        'description': 'Llama 3.3 70B'
    },
    'phi-3-mini': {
        'model_name': 'phi-3-mini-3.8b-instructiontuned-alpaca',
        'description': 'Phi-3 Mini 3.8B'
    },
    'phi-4': {
        'model_name': 'microsoft/phi-4',
        'description': 'Phi-4'
    },
    'phi-2': {
        'model_name': 'phi-2',  # Try without microsoft/ prefix
        'description': 'Phi-2'
    },
    'codellama-7b': {
        'model_name': 'codellama-7b-instruct',
        'description': 'CodeLlama 7B Instruct'
    },
    'llama-3.2-1b': {
        'model_name': 'llama-3.2-1b-instruct',
        'description': 'Llama 3.2 1B'
    },
    'mixtral-8x7b': {
        'model_name': 'mixtral-8x7b-instruct-v0.1',
        'description': 'Mixtral 8x7B Instruct'
    },
    'granite-4-h-tiny': {
        'model_name': 'bm/granite-4-h-tiny',
        'description': 'Granite 4H Tiny'
    },
    'claude-sonnet-4-5': {
        'model_name': 'claude-sonnet-4-5',
        'description': 'Claude Sonnet 4.5 (Anthropic)',
        'provider': 'anthropic'
    },
    'claude-haiku-4-5': {
        'model_name': 'claude-haiku-4-5',
        'description': 'Claude Haiku 4.5 (Anthropic)',
        'provider': 'anthropic'
    },
    'gpt-5.1': {
        'model_name': 'gpt-5.1',
        'description': 'GPT-5.1 (OpenAI)',
        'provider': 'openai'
    },
    'gpt-5-mini': {
        'model_name': 'gpt-5-mini',
        'description': 'GPT-5 Mini (OpenAI)',
        'provider': 'openai'
    },
    'gpt-4o-mini': {
        'model_name': 'gpt-4o-mini',
        'description': 'GPT-4o Mini (OpenAI)',
        'provider': 'openai'
    },
    'o4-mini': {
        'model_name': 'o4-mini',
        'description': 'O4 Mini (OpenAI)',
        'provider': 'openai'
    },
    'o4-mini-deep-research': {
        'model_name': 'o4-mini-deep-research',
        'description': 'O4 Mini Deep Research (OpenAI)',
        'provider': 'openai'
    }
}


async def run_observables_count_with_model(
    article_id: int,
    model_name: str,
    temperature: float = 0.0,
    seed: int = 42,
    junk_filter_threshold: float = 0.8,
    db_session=None
) -> Dict[str, Any]:
    """Run ObservablesCountAgent with specified model."""
    # Use provided session or create new one
    if db_session is None:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        should_close = True
    else:
        should_close = False
    
    try:
        # Get article
        article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
        if not article:
            return {
                'article_id': article_id,
                'error': 'Article not found',
                'counts': None,
                'parse_success': False
            }
        
        content = article.content or ""
        
        # Apply junk filter
        content_filter = ContentFilter()
        hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0
        
        filter_result = content_filter.filter_content(
            content,
            min_confidence=junk_filter_threshold,
            hunt_score=hunt_score,
            article_id=article_id
        )
        filtered_content = filter_result.filtered_content or content
        
        # Load ObservablesCountAgent prompt
        prompt_path = project_root / "src/prompts/ObservablesCountAgent"
        if not prompt_path.exists():
            return {
                'article_id': article_id,
                'error': 'Prompt file not found',
                'counts': None,
                'parse_success': False
            }
        
        with open(prompt_path, 'r') as f:
            prompt_config = json.load(f)
        
        # Build system message from prompt config
        role = prompt_config.get("role", "")
        objective = prompt_config.get("objective", "")
        constraints = prompt_config.get("constraints", [])
        categories = prompt_config.get("categories", {})
        
        system_content = f"{role}\n\nObjective:\n{objective}\n\nConstraints:\n"
        for constraint in constraints:
            system_content += f"  • {constraint}\n"
        
        system_content += "\nCategories for Classification:\n"
        for key, cat_info in sorted(categories.items()):
            cat_num = key.split("_")[0]
            cat_name = " ".join(key.split("_")[1:]).title()
            description = cat_info.get("description", "")
            examples = cat_info.get("examples", [])
            
            system_content += f"\n{cat_num}. {cat_name}\n"
            system_content += f"   {description}\n"
            if examples:
                system_content += f"   e.g., {', '.join(examples)}\n"
        
        # Build user message with article content
        user_content = f"Article:\n\n{filtered_content}\n\n"
        user_content += "CRITICAL: Output ONLY valid JSON. Start with {{ and end with }}. No markdown, no explanations, no other text.\n\n"
        user_content += "Count observables in each category and output JSON matching this format:\n"
        user_content += json.dumps(prompt_config.get("output_format", {}), indent=2)
        user_content += "\n\nRemember: Output ONLY the JSON object, nothing else."
        
        # Check if this is an Anthropic or OpenAI model
        model_config = next((m for m in LLM_MODELS.values() if m['model_name'] == model_name), {})
        is_anthropic = model_config.get('provider') == 'anthropic' or model_name.startswith('claude-')
        is_openai = model_config.get('provider') == 'openai' or model_name.startswith('gpt-')
        
        # Initialize response variables for all paths
        response_text = ''
        reasoning_content = ''
        usage_info = {}
        finish_reason = 'unknown'
        
        if is_openai:
            # Call OpenAI API directly
            openai_api_key = os.getenv("OPENAI_API_KEY", "") or "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"
            if not openai_api_key or openai_api_key.strip() == "":
                return {
                    'article_id': article_id,
                    'error': 'OpenAI API key not configured',
                    'counts': None,
                    'parse_success': False
                }
            
            # GPT-5 and o4-mini models require max_completion_tokens instead of max_tokens
            # o4-mini-deep-research uses v1/responses endpoint
            is_gpt5 = model_name.startswith('gpt-5')
            is_o4_mini = model_name == 'o4-mini'
            is_o4_deep = model_name == 'o4-mini-deep-research'
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                if is_o4_deep:
                    # Use v1/responses endpoint for o4-mini-deep-research
                    payload = {
                        "model": model_name,
                        "input": [
                            {
                                "role": "system",
                                "content": [
                                    {"type": "input_text", "text": system_content}
                                ]
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": user_content}
                                ]
                            }
                        ],
                        "max_output_tokens": 2000,
                        "tools": [
                            {
                                "type": "web_search_preview"
                            }
                        ]
                    }
                    # Note: v1/responses endpoint for deep research models:
                    # - Doesn't support seed parameter
                    # - Doesn't support temperature parameter
                    # - Requires at least one tool (web_search_preview, mcp, or file_search)
                    
                    response = await client.post(
                        "https://api.openai.com/v1/responses",
                        headers={
                            "Authorization": f"Bearer {openai_api_key}",
                            "Content-Type": "application/json"
                        },
                        json=payload
                    )
                else:
                    # Use v1/chat/completions endpoint for other models
                    token_param = "max_completion_tokens" if (is_gpt5 or is_o4_mini) else "max_tokens"
                    payload = {
                        "model": model_name,
                        token_param: 2000,
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": user_content}
                        ]
                    }
                    # gpt-5-mini and o4-mini only support default temperature (1), not 0
                    if model_name not in ['gpt-5-mini', 'o4-mini']:
                        payload["temperature"] = temperature
                    if seed is not None:
                        payload["seed"] = seed
                    
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {openai_api_key}",
                            "Content-Type": "application/json"
                        },
                        json=payload
                    )
                
                if response.status_code != 200:
                    try:
                        error_json = response.json()
                        error_detail = error_json.get('error', {}).get('message', response.text)
                    except:
                        error_detail = response.text
                    return {
                        'article_id': article_id,
                        'url': article.canonical_url or '',
                        'title': article.title or 'Unknown',
                        'error': f"OpenAI API error ({response.status_code}): {error_detail}",
                        'counts': None,
                        'parse_success': False
                    }
                
                result = response.json()
                
                if is_o4_deep:
                    # Responses API format
                    # The response structure: output is an array of content items
                    output_items = result.get('output', [])
                    response_text = ''
                    
                    # Extract text from output items
                    for item in output_items:
                        content = item.get('content', [])
                        for content_item in content:
                            if content_item.get('type') == 'output_text':
                                response_text = content_item.get('text', '')
                                break
                        if response_text:
                            break
                    
                    # Fallback: try to get text directly
                    if not response_text:
                        response_text = result.get('text', '') or str(result.get('content', ''))
                    
                    usage_info = result.get('usage', {})
                    finish_reason = 'stop'  # Responses API may not have finish_reason
                else:
                    # Chat completions API format
                    response_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                    usage_info = result.get('usage', {})
                    finish_reason = result.get('choices', [{}])[0].get('finish_reason', 'stop')
                
                # OpenAI doesn't have separate reasoning content
                reasoning_content = ''
        elif is_anthropic:
            # Call Anthropic API directly
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "") or "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"
            if not anthropic_api_key or anthropic_api_key.strip() == "":
                return {
                    'article_id': article_id,
                    'error': 'Anthropic API key not configured',
                    'counts': None,
                    'parse_success': False
                }
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_api_key,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": model_name,
                        "max_tokens": 2000,
                        "temperature": temperature,
                        "system": system_content,
                        "messages": [
                            {"role": "user", "content": user_content}
                        ]
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    return {
                        'article_id': article_id,
                        'error': f"Anthropic API error ({response.status_code}): {error_detail}",
                        'counts': None,
                        'parse_success': False
                    }
                
                result = response.json()
                response_text = result.get('content', [{}])[0].get('text', '')
                # Anthropic doesn't have separate reasoning content
                reasoning_content = ''
                usage_info = result.get('usage', {})
                finish_reason = 'stop'  # Anthropic uses 'stop' for successful completions
        else:
            # Use LMStudio (original logic)
            original_extract = os.getenv("LMSTUDIO_MODEL_EXTRACT")
            original_rank = os.getenv("LMSTUDIO_MODEL_RANK")
            
            try:
                os.environ["LMSTUDIO_MODEL_EXTRACT"] = model_name
                if not os.getenv("LMSTUDIO_MODEL_RANK"):
                    os.environ["LMSTUDIO_MODEL_RANK"] = model_name
                
                llm_service = LLMService()
                
                # Override temperature and seed
                llm_service.temperature = temperature
                llm_service.seed = seed
                
                # Use extract model
                actual_model_name = llm_service.model_extract
                
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ]
                
                # Convert for models that don't support system role
                messages = llm_service._convert_messages_for_model(messages, actual_model_name)
                
                # Check if reasoning model
                is_reasoning_model = 'r1' in actual_model_name.lower() or 'reasoning' in actual_model_name.lower()
                max_tokens = 2000 if is_reasoning_model else 1500
                
                payload = {
                    "model": actual_model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "top_p": llm_service.top_p,
                }
                
                if seed is not None:
                    payload["seed"] = seed
                
                # Call LLM
                result = await llm_service._post_lmstudio_chat(
                    payload,
                    model_name=actual_model_name,
                    timeout=300.0,
                    failure_context="ObservablesCountAgent evaluation"
                )
                
                # Handle reasoning models
                choice = result.get('choices', [{}])[0]
                message = choice.get('message', {})
                reasoning_content = message.get('reasoning_content', '')
                response_text = message.get('content', '')
                usage_info = result.get('usage', {})
                finish_reason = choice.get('finish_reason', 'unknown')
            finally:
                # Restore original environment variables (only for LMStudio path)
                if original_extract:
                    os.environ["LMSTUDIO_MODEL_EXTRACT"] = original_extract
                elif "LMSTUDIO_MODEL_EXTRACT" in os.environ:
                    del os.environ["LMSTUDIO_MODEL_EXTRACT"]
                
                if original_rank:
                    os.environ["LMSTUDIO_MODEL_RANK"] = original_rank
                elif "LMSTUDIO_MODEL_RANK" in os.environ:
                    del os.environ["LMSTUDIO_MODEL_RANK"]
        
        # Extract JSON from reasoning if needed (common for all paths)
        if reasoning_content and not response_text:
                if '{' in reasoning_content:
                    last_brace = reasoning_content.rfind('}')
                    if last_brace > 0:
                        json_start = reasoning_content.rfind('{', 0, last_brace)
                        if json_start >= 0:
                            potential_json = reasoning_content[json_start:last_brace+1]
                            try:
                                test_parse = json.loads(potential_json)
                                if any(key in test_parse for key in ['CommandLinePatterns', 'ProcessLineagePatterns', 'Total']):
                                    response_text = potential_json
                            except:
                                pass
        
        # Parse JSON from response (common for all paths)
        parsed_result = None
        if response_text:
            try:
                # Handle case where response_text is already a dict (from responses API)
                if isinstance(response_text, dict):
                    parsed_result = response_text
                else:
                    # Extract JSON from markdown code blocks if present
                    json_text = response_text
                    if "```json" in response_text:
                        json_start = response_text.find("```json") + 7
                        json_end = response_text.find("```", json_start)
                        json_text = response_text[json_start:json_end].strip()
                    elif "```" in response_text:
                        json_start = response_text.find("```") + 3
                        json_end = response_text.find("```", json_start)
                        json_text = response_text[json_start:json_end].strip()
                    else:
                        # Try to extract JSON from text that may have prefix/suffix
                        # Find first { and last } to extract JSON object
                        first_brace = json_text.find('{')
                        last_brace = json_text.rfind('}')
                        if first_brace >= 0 and last_brace > first_brace:
                            json_text = json_text[first_brace:last_brace+1]
                    
                    # Handle double braces (some models return {{ ... }})
                    json_text = json_text.strip()
                    if json_text.startswith('{{') and json_text.endswith('}}'):
                        json_text = json_text[1:-1]  # Remove outer braces
                    elif json_text.startswith('{') and json_text.endswith('}'):
                        # Already single braces, keep as is
                        pass
                    
                    parsed_result = json.loads(json_text)
                
                # Convert string numbers to integers (some models return strings)
                if parsed_result:
                    for key, value in list(parsed_result.items()):
                        # Skip if value is a dict or list (not a number)
                        if isinstance(value, (dict, list)):
                            parsed_result[key] = 0  # Set to 0 if it's a complex type
                        elif isinstance(value, str):
                            # Try to convert string to int, but handle non-numeric strings
                            if value.isdigit():
                                parsed_result[key] = int(value)
                            elif value.replace('.', '', 1).isdigit():
                                # Handle decimal strings, but convert to int for counts
                                parsed_result[key] = int(float(value))
                            else:
                                # Non-numeric string (e.g., 'medium', 'high'), set to 0
                                parsed_result[key] = 0
                
                # Calculate total if not present or if it's a string
                if parsed_result:
                    if "Total" not in parsed_result or isinstance(parsed_result.get("Total"), str):
                        total = sum(v for k, v in parsed_result.items() if isinstance(v, (int, float)) and k != "Total")
                        parsed_result["Total"] = int(total)
                    
            except json.JSONDecodeError:
                parsed_result = None
            
        return {
            'article_id': article_id,
            'url': article.canonical_url or '',
            'title': article.title or 'Unknown',
            'counts': parsed_result,
            'parse_success': parsed_result is not None,
            'raw_response': response_text,
            'reasoning_content': reasoning_content if reasoning_content else None,
            'usage': usage_info if 'usage_info' in locals() else {},
            'finish_reason': finish_reason if 'finish_reason' in locals() else 'unknown',
            'error': None
        }
    
    except Exception as e:
        import traceback
        return {
            'article_id': article_id,
            'error': str(e),
            'counts': None,
            'parse_success': False,
            'traceback': traceback.format_exc()
        }
    finally:
        if should_close:
            db_session.close()


async def evaluate_model(
    model_key: str,
    model_config: Dict[str, Any],
    url_to_id: Dict[str, int],
    temperature: float = 0.0,
    seed: int = 42,
    junk_filter_threshold: float = 0.8,
    article_ids: Optional[List[int]] = None,
    output_path: Optional[Path] = None,
    existing_data: Optional[Dict[str, Any]] = None,
    num_runs: int = 1
) -> Dict[str, Any]:
    """Evaluate a single model configuration."""
    print(f"\n{'='*80}")
    print(f"Evaluating: {model_config['description']}")
    print(f"{'='*80}")
    print(f"Model: {model_config['model_name']}")
    print(f"Temperature: {temperature}, Seed: {seed}")
    print()
    
    # Create a single database session for this model evaluation
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    results = []
    category_totals = defaultdict(int)
    successful_parses = 0
    failed_parses = 0
    
    try:
        # Filter to Windows articles only (based on human OS classification)
        windows_test_data = [item for item in MANUAL_TEST_DATA if item.get('human', '').strip() == 'Windows']
        test_data_to_use = windows_test_data if windows_test_data else MANUAL_TEST_DATA
        
        for test_item in test_data_to_use:
            url = test_item['url']
            if url not in url_to_id:
                continue
            
            article_id = url_to_id[url]
            
            # Skip if article_ids filter is specified and this article is not in the list
            if article_ids is not None and article_id not in article_ids:
                continue
            
            try:
                # Run multiple times if num_runs > 1
                all_runs = []
                for run_num in range(num_runs):
                    result = await run_observables_count_with_model(
                        article_id,
                        model_config['model_name'],
                        temperature=temperature,
                        seed=seed if num_runs == 1 else None,  # Only use seed for single runs
                        junk_filter_threshold=junk_filter_threshold,
                        db_session=db_session
                    )
                    all_runs.append(result)
                
                # Calculate median and variance across runs
                import statistics
                
                # Collect all successful parse counts
                successful_runs = [r for r in all_runs if r.get('parse_success') and r.get('counts')]
                
                if successful_runs:
                    # Calculate median for each category
                    median_counts = {}
                    variance_counts = {}
                    
                    # Get all category keys from successful runs
                    all_keys = set()
                    for r in successful_runs:
                        if r.get('counts'):
                            all_keys.update(r['counts'].keys())
                    
                    for key in all_keys:
                        values = [r['counts'].get(key, 0) for r in successful_runs if r.get('counts')]
                        if values:
                            median_counts[key] = int(statistics.median(values))
                            if len(values) > 1:
                                variance_counts[key] = statistics.variance(values) if len(values) > 1 else 0.0
                            else:
                                variance_counts[key] = 0.0
                    
                    # Create result with median values
                    result = {
                        'article_id': article_id,
                        'url': all_runs[0].get('url', ''),
                        'title': all_runs[0].get('title', 'Unknown'),
                        'counts': median_counts,
                        'parse_success': len(successful_runs) > 0,
                        'num_runs': num_runs,
                        'successful_runs': len(successful_runs),
                        'variance': variance_counts,
                        'all_runs': all_runs if num_runs > 1 else None  # Store all runs if multiple
                    }
                    
                    successful_parses += 1
                    counts = median_counts
                    
                    # Sum category counts (using median values)
                    for key, value in counts.items():
                        if key != 'Total' and isinstance(value, int):
                            category_totals[key] += value
                else:
                    # All runs failed
                    result = {
                        'article_id': article_id,
                        'url': all_runs[0].get('url', '') if all_runs else '',
                        'title': all_runs[0].get('title', 'Unknown') if all_runs else 'Unknown',
                        'counts': None,
                        'parse_success': False,
                        'num_runs': num_runs,
                        'successful_runs': 0,
                        'variance': {},
                        'all_runs': all_runs if num_runs > 1 else None
                    }
                    failed_parses += 1
                
                results.append(result)
                
                status = "✓" if result.get('parse_success', False) else "✗"
                total = result.get('counts', {}).get('Total', 0) if result.get('counts') else 0
                title = result.get('title', 'Unknown')
                variance_total = result.get('variance', {}).get('Total', 0) if result.get('variance') else 0
                variance_str = f", var={variance_total:.2f}" if num_runs > 1 and variance_total > 0 else ""
                runs_str = f" ({result.get('successful_runs', 0)}/{num_runs} runs)" if num_runs > 1 else ""
                print(f"  {status} Article {article_id}: Total={total}{variance_str}{runs_str} ({title[:50]}...)")
                
                # Save incrementally after each article if output_path is provided
                if output_path and existing_data is not None:
                    try:
                        # Update the current model's results in memory
                        if model_key not in existing_data.get('models', {}):
                            existing_data['models'][model_key] = {
                                'model_key': model_key,
                                'model_name': model_config['model_name'],
                                'description': model_config['description'],
                                'results': [],
                                'total_articles': 0,
                                'successful_parses': 0,
                                'failed_parses': 0,
                                'parse_success_rate': 0.0,
                                'avg_total_observables': 0.0,
                                'category_totals': {},
                                'category_averages': {}
                            }
                        
                        model_data = existing_data['models'][model_key]
                        # Merge results: keep existing non-Windows results, update/add Windows results
                        existing_results_map = {r.get('article_id'): r for r in model_data.get('results', [])}
                        new_results_map = {r.get('article_id'): r for r in results}
                        
                        # Update with new results (Windows articles)
                        for article_id, result in new_results_map.items():
                            existing_results_map[article_id] = result
                        
                        # Rebuild results list with merged data
                        merged_results = list(existing_results_map.values())
                        model_data['results'] = merged_results
                        model_data['total_articles'] = len(merged_results)
                        
                        # Recalculate metrics from merged results
                        successful_parses_merged = sum(1 for r in merged_results if r.get('parse_success'))
                        model_data['successful_parses'] = successful_parses_merged
                        model_data['failed_parses'] = len(merged_results) - successful_parses_merged
                        model_data['parse_success_rate'] = successful_parses_merged / len(merged_results) if merged_results else 0.0
                        
                        # Recalculate averages from merged results
                        if successful_parses_merged > 0:
                            totals = [r['counts'].get('Total', 0) for r in merged_results if r.get('counts')]
                            if totals:
                                model_data['avg_total_observables'] = sum(totals) / len(totals)
                            
                            # Recalculate category averages from merged results
                            cat_totals = defaultdict(int)
                            for r in merged_results:
                                if r.get('parse_success') and r.get('counts'):
                                    for key, value in r['counts'].items():
                                        if key != 'Total' and isinstance(value, int):
                                            cat_totals[key] += value
                            model_data['category_totals'] = dict(cat_totals)
                            model_data['category_averages'] = {k: v / successful_parses_merged for k, v in cat_totals.items()}
                        
                        # Save to file
                        with open(output_path, 'w') as f:
                            json.dump(existing_data, f, indent=2)
                    except Exception as e:
                        # Don't fail the evaluation if incremental save fails
                        print(f"  ⚠️  Warning: Failed to save incrementally: {e}")
                
            except Exception as e:
                failed_parses += 1
                error_result = {
                    'article_id': article_id,
                    'url': url,
                    'title': test_item.get('title', 'Unknown'),
                    'error': str(e),
                    'counts': None,
                    'parse_success': False
                }
                results.append(error_result)
                print(f"  ✗ Article {article_id}: Error - {e}")
                
                # Save incrementally after error as well
                if output_path and existing_data is not None:
                    try:
                        if model_key not in existing_data.get('models', {}):
                            existing_data['models'][model_key] = {
                                'model_key': model_key,
                                'model_name': model_config['model_name'],
                                'description': model_config['description'],
                                'results': [],
                                'total_articles': 0,
                                'successful_parses': 0,
                                'failed_parses': 0,
                                'parse_success_rate': 0.0,
                                'avg_total_observables': 0.0,
                                'category_totals': {},
                                'category_averages': {}
                            }
                        
                        model_data = existing_data['models'][model_key]
                        # Merge results: keep existing non-Windows results, update/add Windows results
                        existing_results_map = {r.get('article_id'): r for r in model_data.get('results', [])}
                        new_results_map = {r.get('article_id'): r for r in results}
                        
                        # Update with new results (Windows articles)
                        for article_id, result in new_results_map.items():
                            existing_results_map[article_id] = result
                        
                        # Rebuild results list with merged data
                        merged_results = list(existing_results_map.values())
                        model_data['results'] = merged_results
                        model_data['total_articles'] = len(merged_results)
                        
                        # Recalculate metrics from merged results
                        successful_parses_merged = sum(1 for r in merged_results if r.get('parse_success'))
                        model_data['successful_parses'] = successful_parses_merged
                        model_data['failed_parses'] = len(merged_results) - successful_parses_merged
                        model_data['parse_success_rate'] = successful_parses_merged / len(merged_results) if merged_results else 0.0
                        
                        if successful_parses_merged > 0:
                            totals = [r['counts'].get('Total', 0) for r in merged_results if r.get('counts')]
                            if totals:
                                model_data['avg_total_observables'] = sum(totals) / len(totals)
                            
                            cat_totals = defaultdict(int)
                            for r in merged_results:
                                if r.get('parse_success') and r.get('counts'):
                                    for key, value in r['counts'].items():
                                        if key != 'Total' and isinstance(value, int):
                                            cat_totals[key] += value
                            model_data['category_totals'] = dict(cat_totals)
                            model_data['category_averages'] = {k: v / successful_parses_merged for k, v in cat_totals.items()}
                        
                        with open(output_path, 'w') as f:
                            json.dump(existing_data, f, indent=2)
                    except Exception as save_error:
                        print(f"  ⚠️  Warning: Failed to save incrementally after error: {save_error}")
    
    finally:
        db_session.close()
    
    # Calculate metrics
    total_articles = len(results)
    parse_success_rate = successful_parses / total_articles if total_articles > 0 else 0.0
    
    # Calculate averages
    avg_total_observables = 0.0
    if successful_parses > 0:
        totals = [r['counts'].get('Total', 0) for r in results if r.get('counts')]
        if totals:
            avg_total_observables = sum(totals) / len(totals)
    
    category_averages = {}
    if successful_parses > 0:
        for category, total in category_totals.items():
            category_averages[category] = total / successful_parses
    
    return {
        'model_key': model_key,
        'model_name': model_config['model_name'],
        'description': model_config['description'],
        'total_articles': total_articles,
        'successful_parses': successful_parses,
        'failed_parses': failed_parses,
        'parse_success_rate': parse_success_rate,
        'avg_total_observables': avg_total_observables,
        'category_totals': dict(category_totals),
        'category_averages': category_averages,
        'results': results
    }


async def main():
    """Main evaluation function."""
    parser = argparse.ArgumentParser(description='Evaluate ObservablesCountAgent with multiple LLM models')
    parser.add_argument(
        '--models',
        type=str,
        nargs='+',
        default=[k for k in LLM_MODELS.keys() if k != 'llama-3-13b'],  # Exclude llama-3-13b (generates repetitive tokens)
        help='Models to test (default: all LLM models)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='outputs/evaluations/observables_count_multi_model_eval.json',
        help='Output path for evaluation results'
    )
    parser.add_argument(
        '--temperature',
        type=float,
        default=0.0,
        help='Temperature setting (default: 0.0 for deterministic)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed (default: 42)'
    )
    parser.add_argument(
        '--junk-filter-threshold',
        type=float,
        default=0.8,
        help='Junk filter threshold (default: 0.8)'
    )
    parser.add_argument(
        '--article-ids',
        type=int,
        nargs='+',
        default=None,
        help='Specific article IDs to test (default: all articles from MANUAL_TEST_DATA)'
    )
    parser.add_argument(
        '--num-runs',
        type=int,
        default=1,
        help='Number of runs per article (default: 1, use median for >1)'
    )
    parser.add_argument(
        '--list-models',
        action='store_true',
        help='List available models and exit'
    )
    
    args = parser.parse_args()
    
    if args.list_models:
        print("Available models:")
        print("=" * 80)
        for key, config in LLM_MODELS.items():
            print(f"\n{key}:")
            print(f"  Description: {config['description']}")
            print(f"  Model: {config['model_name']}")
        return
    
    print("=" * 80)
    print("ObservablesCountAgent Multi-Model Evaluation")
    print("=" * 80)
    print()
    
    # Map URLs to article IDs
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    url_to_id = {}
    try:
        for test_item in MANUAL_TEST_DATA:
            article = db_session.query(ArticleTable).filter(
                ArticleTable.canonical_url == test_item['url']
            ).first()
            if article:
                url_to_id[test_item['url']] = article.id
    finally:
        db_session.close()
    
    print(f"Found {len(url_to_id)} articles in database")
    print(f"Testing models: {', '.join(args.models)}")
    print(f"Temperature: {args.temperature}, Seed: {args.seed}")
    print(f"Junk filter threshold: {args.junk_filter_threshold}")
    print()
    
    # Validate models
    invalid_models = [m for m in args.models if m not in LLM_MODELS]
    if invalid_models:
        print(f"❌ Invalid models: {', '.join(invalid_models)}")
        print(f"Available models: {', '.join(LLM_MODELS.keys())}")
        return
    
    # Load existing results if file exists (for incremental saving)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    existing_data = {}
    if output_path.exists():
        try:
            with open(output_path, 'r') as f:
                existing_data = json.load(f)
        except:
            pass
    
    # Evaluate each model
    all_results = {}
    for model_key in args.models:
        model_config = LLM_MODELS[model_key]
        try:
            result = await evaluate_model(
                model_key,
                model_config,
                url_to_id,
                temperature=args.temperature,
                seed=args.seed,
                junk_filter_threshold=args.junk_filter_threshold,
                article_ids=args.article_ids,
                output_path=output_path,
                existing_data=existing_data,
                num_runs=args.num_runs
            )
            all_results[model_key] = result
        except Exception as e:
            print(f"❌ Error evaluating {model_key}: {e}")
            import traceback
            traceback.print_exc()
            all_results[model_key] = {
                'model_key': model_key,
                'error': str(e)
            }
    
    # Print comparison summary
    print("\n" + "=" * 80)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 80)
    print()
    
    print(f"{'Model':<30} {'Parse Rate':<15} {'Avg Total':<15} {'Description'}")
    print("-" * 80)
    
    sorted_results = sorted(
        [(k, v) for k, v in all_results.items() if 'parse_success_rate' in v],
        key=lambda x: x[1]['parse_success_rate'],
        reverse=True
    )
    
    for model_key, result in sorted_results:
        if 'parse_success_rate' in result:
            model_name = result['description']
            parse_rate = result['parse_success_rate']
            avg_total = result.get('avg_total_observables', 0.0)
            print(f"{model_name:<30} {parse_rate:>6.1%}        {avg_total:>6.1f}        {model_name}")
    
    # Final save (results already saved incrementally, but update with final metrics)
    # existing_data already loaded above
    
    # If article_ids were specified, merge results into latest run instead of creating new run
    if args.article_ids and existing_data.get('models'):
        # Find the run with the most articles for this model (the full evaluation run)
        target_run = None
        max_articles = 0
        if 'runs' in existing_data and existing_data['runs']:
            for run in existing_data['runs']:
                if args.models[0] in run.get('models', {}):
                    model_data = run['models'][args.models[0]]
                    num_articles = len(model_data.get('results', []))
                    if num_articles > max_articles:
                        max_articles = num_articles
                        target_run = run
        
        # Fallback to top-level models if no run found
        if not target_run:
            target_run = {'models': existing_data.get('models', {})}
        
        # Update existing results for specified models
        for model_key in args.models:
            if model_key in target_run.get('models', {}):
                existing_model = target_run['models'][model_key]
                new_model = all_results.get(model_key, {})
                
                # Create a map of article_id -> result for easy lookup
                existing_results_map = {r.get('article_id'): r for r in existing_model.get('results', [])}
                new_results_map = {r.get('article_id'): r for r in new_model.get('results', [])}
                
                # Update existing results with new ones for specified article IDs only
                updated_count = 0
                for article_id in args.article_ids:
                    if article_id in new_results_map:
                        old_ps = existing_results_map.get(article_id, {}).get('parse_success', 'N/A')
                        existing_results_map[article_id] = new_results_map[article_id]
                        new_ps = existing_results_map[article_id].get('parse_success', 'N/A')
                        updated_count += 1
                        print(f"  Updated article {article_id}: parse_success {old_ps} -> {new_ps}")
                
                # Recalculate metrics using ALL results (not just the updated ones)
                updated_results = list(existing_results_map.values())
                successful = [r for r in updated_results if r.get('parse_success')]
                existing_model['results'] = updated_results
                existing_model['total_articles'] = len(updated_results)
                existing_model['successful_parses'] = len(successful)
                existing_model['failed_parses'] = len(updated_results) - len(successful)
                existing_model['parse_success_rate'] = len(successful) / len(updated_results) if updated_results else 0.0
                
                # Recalculate averages
                if successful:
                    totals = [r.get('counts', {}).get('Total', 0) for r in successful if r.get('counts')]
                    existing_model['avg_total_observables'] = sum(totals) / len(totals) if totals else 0.0
                    
                    # Recalculate category totals and averages
                    from collections import defaultdict
                    category_totals = defaultdict(int)
                    for r in successful:
                        counts = r.get('counts', {})
                        if counts:
                            for key, value in counts.items():
                                if key != 'Total' and isinstance(value, int):
                                    category_totals[key] += value
                    existing_model['category_totals'] = dict(category_totals)
                    existing_model['category_averages'] = {k: v / len(successful) for k, v in category_totals.items()}
                
                # Update both the run and top-level
                all_results[model_key] = existing_model
                if 'runs' in existing_data and target_run in existing_data['runs']:
                    target_run['models'][model_key] = existing_model
                existing_data['models'][model_key] = existing_model
        
        print(f"\n✅ Merged results for {updated_count} articles into existing {args.models[0]} results (total: {len(updated_results)} articles)")
        
        # Save the merged data and exit (don't create a new run)
        with open(output_path, 'w') as f:
            json.dump(existing_data, f, indent=2)
        print(f"✅ Results saved to: {output_path}")
        return
    
    # Create new run entry (only if not merging)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_run = {
        'run_id': run_id,
        'evaluation_date': datetime.now().isoformat(),
        'total_articles': len(url_to_id) if not args.article_ids else len(args.article_ids),
        'temperature': args.temperature,
        'seed': args.seed,
        'junk_filter_threshold': args.junk_filter_threshold,
        'models_tested': args.models,
        'models': all_results
    }
    
    # Merge with existing data - preserve previous runs
    if 'runs' in existing_data:
        existing_data['runs'].append(new_run)
    else:
        # Convert old format to new format with runs array
        if 'models' in existing_data:
            # This is an old format file, convert it
            old_run = {
                'run_id': existing_data.get('evaluation_date', 'legacy').replace(':', '').replace('-', '')[:15],
                'evaluation_date': existing_data.get('evaluation_date', datetime.now().isoformat()),
                'total_articles': existing_data.get('total_articles', 0),
                'temperature': existing_data.get('temperature', 0.0),
                'seed': existing_data.get('seed', 42),
                'junk_filter_threshold': existing_data.get('junk_filter_threshold', 0.8),
                'models_tested': existing_data.get('models_tested', []),
                'models': existing_data.get('models', {})
            }
            existing_data = {'runs': [old_run, new_run]}
        else:
            existing_data = {'runs': [new_run]}
    
    # Also keep latest run at top level for backward compatibility
    existing_data['evaluation_date'] = new_run['evaluation_date']
    existing_data['total_articles'] = new_run['total_articles']
    existing_data['temperature'] = new_run['temperature']
    existing_data['seed'] = new_run['seed']
    existing_data['junk_filter_threshold'] = new_run['junk_filter_threshold']
    existing_data['models_tested'] = new_run['models_tested']
    
    # Merge all models from all runs into top-level models dict
    # This ensures the API endpoint can access all models, not just the latest run
    all_models_merged = {}
    if 'runs' in existing_data:
        for run in existing_data['runs']:
            run_models = run.get('models', {})
            for model_key, model_data in run_models.items():
                # Keep the most recent result for each model (later runs overwrite earlier ones)
                if model_key not in all_models_merged:
                    all_models_merged[model_key] = model_data
                else:
                    # Compare run dates to keep the most recent
                    current_run_date = run.get('evaluation_date', '')
                    existing_run_date = None
                    # Find the run that has this model in all_models_merged
                    for existing_run in existing_data['runs']:
                        if model_key in existing_run.get('models', {}):
                            existing_run_date = existing_run.get('evaluation_date', '')
                            break
                    if current_run_date > existing_run_date:
                        all_models_merged[model_key] = model_data
    
    existing_data['models'] = all_models_merged
    
    with open(output_path, 'w') as f:
        json.dump(existing_data, f, indent=2)
    
    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"\n✅ Results saved to: {output_path}")
    
    if sorted_results:
        best_model = sorted_results[0]
        print(f"\n📊 Best model: {best_model[1]['description']} ({best_model[1]['parse_success_rate']:.1%} parse success)")


if __name__ == "__main__":
    asyncio.run(main())

