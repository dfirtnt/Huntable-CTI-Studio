"""
AI-powered article analysis endpoints.
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Dict, Optional

import httpx

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.services.sigma_validator import validate_sigma_rule
from src.utils.gpt4o_optimizer import estimate_gpt4o_cost
from src.utils.prompt_loader import format_prompt
from src.utils.ioc_extractor import HybridIOCExtractor
from src.worker.celery_app import celery_app
from src.web.dependencies import logger

router = APIRouter(prefix="/api/articles", tags=["Articles", "AI"])

# Test API key endpoints (separate router for correct URL paths)
test_router = APIRouter(prefix="/api", tags=["AI", "Testing"])

@test_router.post("/test-openai-key")
async def api_test_openai_key(request: Request):
    """Test OpenAI API key validity."""
    try:
        body = await request.json()
        api_key = body.get('api_key')
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")
        
        # Test the API key with a simple request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                return {"valid": True, "message": "API key is valid"}
            elif response.status_code == 401:
                return {"valid": False, "message": "Invalid API key"}
            else:
                return {"valid": False, "message": f"API error: {response.status_code}"}
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
        logger.error(f"OpenAI API key test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@test_router.post("/test-ollama-connection")
async def api_test_ollama_connection(request: Request):
    """Test Ollama connection and model availability."""
    try:
        body = await request.json()
        model = body.get('model', 'tinyllama')  # Default to tinyllama
        
        ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
        
        # Test the Ollama connection with a simple request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": "Hello",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 5
                    }
                },
                timeout=15.0
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get('response', '')
                return {
                    "valid": True, 
                    "message": f"Ollama connection successful. Model '{model}' responded: '{response_text.strip()}'"
                }
            else:
                return {
                    "valid": False, 
                    "message": f"Ollama API error: {response.status_code} - {response.text}"
                }
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout - Ollama may be starting up")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Ollama service")
    except Exception as e:
        logger.error(f"Ollama connection test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@test_router.post("/test-anthropic-key")
async def api_test_anthropic_key(request: Request):
    """Test Anthropic API key validity."""
    try:
        body = await request.json()
        api_key = body.get('api_key')
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")
        
        # Test the API key with a simple request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hello"}]
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                return {"valid": True, "message": "API key is valid"}
            elif response.status_code == 401:
                return {"valid": False, "message": "Invalid API key"}
            else:
                return {"valid": False, "message": f"API error: {response.status_code}"}
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
        logger.error(f"Anthropic API key test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@test_router.get("/lmstudio-models")
async def api_get_lmstudio_models():
    """Get currently loaded models from LMStudio."""
    try:
        lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{lmstudio_url}/models", timeout=10.0)
            
            if response.status_code == 200:
                models_data = response.json()
                models = [model["id"] for model in models_data.get("data", [])]
                return {
                    "success": True,
                    "models": models,
                    "message": f"Found {len(models)} loaded model(s)"
                }
            else:
                return {
                    "success": False,
                    "models": [],
                    "message": f"LMStudio API error: {response.status_code}"
                }
                
    except httpx.TimeoutException:
        return {
            "success": False,
            "models": [],
            "message": "Request timeout - LMStudio may be starting up"
        }
    except httpx.ConnectError:
        return {
            "success": False,
            "models": [],
            "message": "Cannot connect to LMStudio service"
        }
    except Exception as e:
        logger.error(f"LMStudio models fetch error: {e}")
        return {
            "success": False,
            "models": [],
            "message": f"Error fetching models: {str(e)}"
        }


@test_router.post("/test-lmstudio-connection")
async def api_test_lmstudio_connection(request: Request):
    """Test LMStudio connection and model availability."""
    try:
        lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        lmstudio_model = os.getenv("LMSTUDIO_MODEL", "llama-3.2-1b-instruct")
        
        # Test the LMStudio connection with a simple request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{lmstudio_url}/chat/completions",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "model": lmstudio_model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5,
                    "temperature": 0.1
                },
                timeout=15.0
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                return {
                    "valid": True, 
                    "message": f"LMStudio connection successful. Model '{lmstudio_model}' responded: '{response_text.strip()}'"
                }
            else:
                return {
                    "valid": False, 
                    "message": f"LMStudio API error: {response.status_code} - {response.text}"
                }
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout - LMStudio may be starting up")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to LMStudio service")
    except Exception as e:
        logger.error(f"LMStudio connection test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/rank-with-gpt4o")
async def api_rank_with_gpt4o(article_id: int, request: Request):
    """API endpoint for GPT4o SIGMA huntability ranking (frontend-compatible endpoint)."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        article_url = body.get('url')
        api_key = body.get('api_key')  # Get API key from request
        ai_model = body.get('ai_model', 'chatgpt')  # Get AI model from request
        optimization_options = body.get('optimization_options', {})
        use_filtering = body.get('use_filtering', True)  # Enable filtering by default
        min_confidence = body.get('min_confidence', 0.7)  # Confidence threshold
        force_regenerate = body.get('force_regenerate', False)  # Force regeneration
        
        logger.info(f"Ranking request for article {article_id}, ai_model: {ai_model}, api_key provided: {bool(api_key)}, force_regenerate: {force_regenerate}")
        
        # Check if API key is provided (required for ChatGPT and Anthropic)
        if ai_model == 'chatgpt' and not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required for ChatGPT. Please configure it in Settings.")
        elif ai_model == 'anthropic' and not api_key:
            raise HTTPException(status_code=400, detail="Anthropic API key is required for Claude. Please configure it in Settings.")
        
        # Check for existing ranking data (unless force regeneration is requested)
        if not force_regenerate:
            existing_ranking = article.article_metadata.get('gpt4o_ranking') if article.article_metadata else None
            if existing_ranking:
                logger.info(f"Returning existing ranking for article {article_id}")
                return {
                    "success": True,
                    "article_id": article_id,
                    "analysis": existing_ranking.get('analysis', ''),
                    "analyzed_at": existing_ranking.get('analyzed_at', ''),
                    "model_used": existing_ranking.get('model_used', ''),
                    "model_name": existing_ranking.get('model_name', ''),
                    "optimization_options": existing_ranking.get('optimization_options', {}),
                    "content_filtering": existing_ranking.get('content_filtering', {})
                }
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Use content filtering for high-value chunks if enabled
        content_filtering_enabled = os.getenv('CONTENT_FILTERING_ENABLED', 'true').lower() == 'true'
        
        if content_filtering_enabled and use_filtering:
            from src.utils.gpt4o_optimizer import optimize_article_content
            
            try:
                optimization_result = await optimize_article_content(
                    article.content, 
                    min_confidence=min_confidence,
                    article_metadata=article.article_metadata,
                    content_hash=article.content_hash
                )
                if optimization_result['success']:
                    content_to_analyze = optimization_result['filtered_content']
                    logger.info(f"Content filtered for GPT-4o ranking: {optimization_result['tokens_saved']:,} tokens saved, "
                              f"{optimization_result['cost_reduction_percent']:.1f}% cost reduction")
                else:
                    # Fallback to original content if filtering fails
                    content_to_analyze = article.content
                    logger.warning("Content filtering failed for GPT-4o ranking, using original content")
            except Exception as e:
                logger.error(f"Content filtering error for GPT-4o ranking: {e}, using original content")
                content_to_analyze = article.content
        else:
            # Use original content if filtering is disabled
            content_to_analyze = article.content
        
        # Use environment-configured content limits (no hardcoded truncation)
        # Content filtering already optimizes content, so we trust the configured limits
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # Choose prompt based on AI model
        if ai_model in ['chatgpt', 'anthropic']:
            # Use detailed prompt for cloud models
            sigma_prompt = format_prompt("gpt4o_sigma_ranking", 
                title=article.title,
                source=source_name,
                url=article.canonical_url or 'N/A',
                content=content_to_analyze
            )
        elif ai_model == 'lmstudio':
            # Use ultra-short prompt for LMStudio
            sigma_prompt = format_prompt("lmstudio_sigma_ranking", 
                title=article.title,
                source=source_name,
                content=content_to_analyze[:2000]  # Limit content to 2000 chars
            )
        else:
            # Use simplified prompt for other local LLMs
            sigma_prompt = format_prompt("llm_sigma_ranking_simple", 
                title=article.title,
                source=source_name,
                url=article.canonical_url or 'N/A',
                content=content_to_analyze
            )
        
        # Generate ranking based on AI model
        if ai_model == 'chatgpt':
            # Use ChatGPT API
            chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    chatgpt_api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {
                                "role": "user",
                                "content": sigma_prompt
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"OpenAI API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
                
                result = response.json()
                analysis = result['choices'][0]['message']['content']
                model_used = 'chatgpt'
                model_name = 'gpt-4o'
        elif ai_model == 'anthropic':
            # Use Anthropic API
            anthropic_api_url = os.getenv('ANTHROPIC_API_URL', 'https://api.anthropic.com/v1/messages')
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    anthropic_api_url,
                    headers={
                        "x-api-key": api_key,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": "claude-sonnet-4-5",
                        "max_tokens": 2000,
                        "temperature": 0.3,
                        "messages": [
                            {
                                "role": "user",
                                "content": sigma_prompt
                            }
                        ]
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Anthropic API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"Anthropic API error: {error_detail}")
                
                result = response.json()
                analysis = result['content'][0]['text']
                model_used = 'anthropic'
                model_name = 'claude-sonnet-4-5'
        elif ai_model == 'tinyllama':
            # Use Ollama API with TinyLlama model
            ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
            
            logger.info(f"Using Ollama at {ollama_url} with TinyLlama model")
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{ollama_url}/api/generate",
                        json={
                            "model": "tinyllama",
                            "prompt": sigma_prompt,
                            "stream": True,  # Enable streaming for better responsiveness
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 2000
                            }
                        },
                        timeout=300.0
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                        raise HTTPException(status_code=500, detail=f"Failed to get ranking from TinyLlama: {response.status_code}")
                    
                    # Collect streaming response
                    analysis = ""
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                if 'response' in chunk:
                                    analysis += chunk['response']
                                if chunk.get('done', False):
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    if not analysis:
                        analysis = "No analysis available"
                    
                    model_used = 'tinyllama'
                    model_name = 'tinyllama'
                    logger.info(f"Successfully got ranking from TinyLlama: {len(analysis)} characters")
                    
                except Exception as e:
                    logger.error(f"TinyLlama API request failed: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to get ranking from TinyLlama: {str(e)}")
        elif ai_model == 'lmstudio':
            # Use LMStudio API
            lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
            lmstudio_model = os.getenv("LMSTUDIO_MODEL", "llama-3.2-1b-instruct")
            
            logger.info(f"Using LMStudio at {lmstudio_url} with model {lmstudio_model}")
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{lmstudio_url}/chat/completions",
                        headers={
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": lmstudio_model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": sigma_prompt
                                }
                            ],
                            "max_tokens": 2000,
                            "temperature": 0.3
                        },
                        timeout=300.0
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"LMStudio API error: {response.status_code} - {response.text}")
                        raise HTTPException(status_code=500, detail=f"Failed to get ranking from LMStudio: {response.status_code}")
                    
                    result = response.json()
                    analysis = result['choices'][0]['message']['content']
                    
                    if not analysis:
                        analysis = "No analysis available"
                    
                    model_used = 'lmstudio'
                    model_name = lmstudio_model
                    logger.info(f"Successfully got ranking from LMStudio: {len(analysis)} characters")
                    
                except Exception as e:
                    logger.error(f"LMStudio API request failed: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to get ranking from LMStudio: {str(e)}")
        elif ai_model == 'ollama':
            # Use Ollama API with default model (Llama 3.2 1B)
            ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
            ollama_model = os.getenv('LLM_MODEL', 'llama3.2:1b')
            
            logger.info(f"Using Ollama at {ollama_url} with model {ollama_model}")
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{ollama_url}/api/generate",
                        json={
                            "model": ollama_model,
                            "prompt": sigma_prompt,
                            "stream": True,  # Enable streaming for better responsiveness
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 2000
                            }
                        },
                        timeout=300.0
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                        raise HTTPException(status_code=500, detail=f"Failed to get ranking from Ollama: {response.status_code}")
                    
                    # Collect streaming response
                    analysis = ""
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                if 'response' in chunk:
                                    analysis += chunk['response']
                                if chunk.get('done', False):
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    if not analysis:
                        analysis = "No analysis available"
                    
                    model_used = 'ollama'
                    model_name = ollama_model
                    logger.info(f"Successfully got ranking from Ollama: {len(analysis)} characters")
                    
                except Exception as e:
                    logger.error(f"Ollama API request failed: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to get ranking from Ollama: {str(e)}")
        else:
            # Default fallback - use OpenAI API
            logger.warning(f"Unknown AI model '{ai_model}', falling back to OpenAI")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {
                                "role": "user",
                                "content": sigma_prompt
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"OpenAI API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
                
                result = response.json()
                analysis = result['choices'][0]['message']['content']
                model_used = 'openai'
                model_name = 'gpt-4o'
        
        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}
        
        article.article_metadata['gpt4o_ranking'] = {
            'analysis': analysis,
            'analyzed_at': datetime.now().isoformat(),
            'model_used': model_used,
            'model_name': model_name,
            'optimization_options': optimization_options,
            'content_filtering': {
                'enabled': content_filtering_enabled and use_filtering,
                'min_confidence': min_confidence if content_filtering_enabled and use_filtering else None,
                'tokens_saved': optimization_result.get('tokens_saved', 0) if content_filtering_enabled and use_filtering else 0,
                'cost_reduction_percent': optimization_result.get('cost_reduction_percent', 0) if content_filtering_enabled and use_filtering else 0
            }
        }
        
        # Update the article
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "analyzed_at": article.article_metadata['gpt4o_ranking']['analyzed_at'],
            "model_used": model_used,
            "model_name": model_name,
            "optimization_options": optimization_options,
            "content_filtering": article.article_metadata['gpt4o_ranking']['content_filtering']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/gpt4o-rank")
async def api_gpt4o_rank(article_id: int, request: Request):
    """API endpoint for GPT4o SIGMA huntability ranking."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        article_url = body.get('url')
        api_key = body.get('api_key')  # Get API key from request
        
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Use full content (no hardcoded truncation)
        content_to_analyze = article.content
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # SIGMA-focused prompt
        sigma_prompt = format_prompt("gpt4o_sigma_ranking", 
            title=article.title,
            source=source_name,
            url=article.canonical_url or 'N/A',
            content=content_to_analyze
        )
        
        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze
        )
        
        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
            
            result = response.json()
            analysis = result['choices'][0]['message']['content']
        
        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}
        
        article.article_metadata['gpt4o_ranking'] = {
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat(),
            'model': 'gpt-4o'
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/gpt4o-rank-optimized")
async def api_gpt4o_rank_optimized(article_id: int, request: Request):
    """Enhanced API endpoint for GPT4o SIGMA huntability ranking with content filtering."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        article_url = body.get('url')
        api_key = body.get('api_key')
        use_filtering = body.get('use_filtering', True)  # Enable filtering by default
        min_confidence = body.get('min_confidence', 0.7)  # Confidence threshold
        
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Import the optimizer
        from src.utils.gpt4o_optimizer import optimize_article_content
        
        # Optimize content if filtering is enabled
        if use_filtering:
            logger.info(f"Optimizing content for article {article_id} with confidence threshold {min_confidence}")
            optimization_result = await optimize_article_content(article.content, min_confidence)
            
            if optimization_result['success']:
                content_to_analyze = optimization_result['filtered_content']
                cost_savings = optimization_result['cost_savings']
                tokens_saved = optimization_result['tokens_saved']
                chunks_removed = optimization_result['chunks_removed']
                
                logger.info(f"Content optimization completed: "
                           f"{tokens_saved:,} tokens saved, "
                           f"${cost_savings:.4f} cost savings, "
                           f"{chunks_removed} chunks removed")
            else:
                logger.warning("Content optimization failed, using original content")
                content_to_analyze = article.content
                cost_savings = 0.0
                tokens_saved = 0
                chunks_removed = 0
        else:
            content_to_analyze = article.content
            cost_savings = 0.0
            tokens_saved = 0
            chunks_removed = 0
        
        # Use full content (no hardcoded truncation)
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # SIGMA-focused prompt (same as original)
        sigma_prompt = format_prompt("gpt4o_sigma_ranking", 
            title=article.title,
            source=source_name,
            url=article.canonical_url or 'N/A',
            content=content_to_analyze
        )
        
        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze
        )
        
        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
            
            result = response.json()
            analysis = result['choices'][0]['message']['content']
        
        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}
        
        article.article_metadata['gpt4o_ranking'] = {
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat(),
            'model': 'gpt-4o',
            'optimization_enabled': use_filtering,
            'cost_savings': cost_savings,
            'tokens_saved': tokens_saved,
            'chunks_removed': chunks_removed,
            'min_confidence': min_confidence if use_filtering else None
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat(),
            "optimization": {
                "enabled": use_filtering,
                "cost_savings": cost_savings,
                "tokens_saved": tokens_saved,
                "chunks_removed": chunks_removed,
                "min_confidence": min_confidence if use_filtering else None
            },
            "debug_info": {
                "removed_chunks": optimization_result.get('removed_chunks', []) if use_filtering and optimization_result.get('success') else [],
                "original_length": len(article.content),
                "filtered_length": len(content_to_analyze),
                "reduction_percent": round((len(article.content) - len(content_to_analyze)) / max(len(article.content), 1) * 100, 1) if use_filtering else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/extract-iocs")
async def api_extract_iocs(article_id: int, request: Request):
    """Extract IOCs (Indicators of Compromise) from an article using AI."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        api_key = body.get('api_key')
        ai_model = body.get('ai_model', 'chatgpt')
        use_llm_validation = body.get('use_llm_validation', False)
        debug_mode = body.get('debug_mode', False)
        
        # Only require API key for cloud-based models
        if ai_model in ['chatgpt', 'anthropic'] and not api_key:
            key_type = 'OpenAI' if ai_model == 'chatgpt' else 'Anthropic'
            raise HTTPException(status_code=400, detail=f"{key_type} API key is required. Please configure it in Settings.")
        
        # Use the IOC extractor
        from src.utils.ioc_extractor import HybridIOCExtractor
        
        # Enable LLM validation for all models
        effective_llm_validation = use_llm_validation
        if use_llm_validation:
            logger.info(f"LLM validation enabled for {ai_model} model")
        
        extractor = HybridIOCExtractor(use_llm_validation=effective_llm_validation)
        
        # Extract IOCs from the article content
        result = await extractor.extract_iocs(
            content=article.content,
            api_key=api_key,
            ai_model=ai_model  # Pass AI model to extractor
        )
        
        # Update article metadata with extracted IOCs
        if result.iocs and len(result.iocs) > 0:
            # Get current metadata and merge with new IOCs data
            current_metadata = article.article_metadata or {}
            current_metadata['extracted_iocs'] = {
                'iocs': result.iocs,
                'extraction_method': result.extraction_method,
                'confidence': result.confidence,
                'extracted_at': datetime.now().isoformat(),
                'ai_model': ai_model,
                'use_llm_validation': result.extraction_method == 'hybrid',  # Store actual validation status
                'processing_time': result.processing_time,
                'raw_count': result.raw_count,
                'validated_count': result.validated_count,
                'metadata': result.metadata  # Store prompt and response
            }
            
            # Update the article in the database
            from src.models.article import ArticleUpdate
            update_data = ArticleUpdate(article_metadata=current_metadata)
            await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": len(result.iocs) > 0,
            "iocs": result.iocs,
            "method": result.extraction_method,
            "confidence": result.confidence,
            "processing_time": result.processing_time,
            "raw_count": result.raw_count,
            "validated_count": result.validated_count,
            "debug_info": result.metadata if debug_mode else None,
            "llm_prompt": result.metadata.get('prompt') if result.metadata else None,
            "llm_response": result.metadata.get('response') if result.metadata else None,
            "error": None if len(result.iocs) > 0 else "No IOCs found"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IOCs extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/generate-sigma")
async def api_generate_sigma(article_id: int, request: Request):
    """Generate SIGMA detection rules from an article using AI."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        api_key = body.get('api_key')
        ai_model = body.get('ai_model', 'chatgpt')
        author_name = body.get('author_name', 'CTI Scraper User')
        force_regenerate = body.get('force_regenerate', False)
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required. Please configure it in Settings.")
        
        # Check for existing SIGMA rules (unless force regeneration is requested)
        if not force_regenerate and article.article_metadata and article.article_metadata.get('sigma_rules'):
            existing_rules = article.article_metadata.get('sigma_rules')
            return {
                "success": True,
                "rules": existing_rules.get('rules', []),
                "metadata": existing_rules.get('metadata', {}),
                "cached": True,
                "error": None
            }
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for SIGMA rule generation")
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # Apply content filtering to optimize for SIGMA generation
        from src.utils.gpt4o_optimizer import optimize_article_content
        
        # Use content filtering with high confidence threshold for SIGMA generation
        min_confidence = 0.7
        logger.info(f"Optimizing content for SIGMA generation with confidence threshold {min_confidence}")
        optimization_result = await optimize_article_content(article.content, min_confidence)
        
        if optimization_result['success']:
            content_to_analyze = optimization_result['filtered_content']
            cost_savings = optimization_result['cost_savings']
            tokens_saved = optimization_result['tokens_saved']
            chunks_removed = optimization_result['chunks_removed']
            
            logger.info(f"Content optimization completed for SIGMA generation: "
                       f"{tokens_saved:,} tokens saved, "
                       f"${cost_savings:.4f} cost savings, "
                       f"{chunks_removed} chunks removed")
        else:
            logger.warning("Content optimization failed for SIGMA generation, using original content")
            content_to_analyze = article.content
            cost_savings = 0.0
            tokens_saved = 0
            chunks_removed = 0
        
        # Load SIGMA generation prompt with filtered content
        sigma_prompt = format_prompt("sigma_generation",
            title=article.title,
            source=source_name,
            url=article.canonical_url or 'N/A',
            content=content_to_analyze
        )
        
        # Call OpenAI API for SIGMA rule generation
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a senior cybersecurity detection engineer specializing in SIGMA rule creation. Generate high-quality, actionable SIGMA rules based on threat intelligence articles. Always use proper SIGMA syntax and include all required fields according to SigmaHQ standards."
                        },
                        {
                            "role": "user",
                            "content": sigma_prompt
                        }
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.3
                },
                timeout=120.0
            )
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {response.status_code}")
            
            result = response.json()
            sigma_response = result['choices'][0]['message']['content']
        
        # Implement iterative SIGMA rule generation with validation feedback
        from src.services.sigma_validator import validate_sigma_rule, clean_sigma_rule
        
        conversation_log = []
        validation_results = []
        rules = []
        max_attempts = 3
        
        for attempt in range(max_attempts):
            logger.info(f"SIGMA generation attempt {attempt + 1}/{max_attempts}")
            
            # Prepare the prompt for this attempt
            if attempt == 0:
                # First attempt - use the original prompt
                current_prompt = sigma_prompt
            else:
                # Subsequent attempts - include validation feedback
                previous_errors = []
                for result in validation_results:
                    if not result.is_valid and result.errors:
                        previous_errors.extend(result.errors)
                
                if previous_errors:
                    error_feedback = "\n\n".join(previous_errors)
                    current_prompt = f"""{sigma_prompt}

IMPORTANT: The previous attempt had validation errors. Please fix these issues:

VALIDATION ERRORS FROM PREVIOUS ATTEMPT:
{error_feedback}

CRITICAL: Output ONLY the YAML rule content. Do NOT include markdown code blocks (```yaml or ```). Do NOT include any explanatory text. Start directly with the YAML content.

Please generate corrected SIGMA rules that address these validation errors. Ensure all required fields are present and the YAML syntax is correct."""
                else:
                    # No errors to fix, break the loop
                    break
            
            # Call OpenAI API for SIGMA rule generation
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a senior cybersecurity detection engineer specializing in SIGMA rule creation. Generate high-quality, actionable SIGMA rules based on threat intelligence articles. Always use proper SIGMA syntax and include all required fields according to SigmaHQ standards."
                            },
                            {
                                "role": "user",
                                "content": current_prompt
                            }
                        ],
                        "max_tokens": 4000,
                        "temperature": 0.3
                    },
                    timeout=120.0
                )
                
                if response.status_code == 429:
                    error_detail = "OpenAI API rate limit exceeded. Please wait a few minutes and try again, or check your API usage limits."
                    logger.warning(f"OpenAI rate limit hit: {response.text}")
                    raise HTTPException(status_code=429, detail=error_detail)
                elif response.status_code != 200:
                    error_detail = f"OpenAI API error: {response.status_code}"
                    if response.status_code == 401:
                        error_detail = "OpenAI API key is invalid or expired. Please check your API key in Settings."
                    elif response.status_code == 402:
                        error_detail = "OpenAI API billing issue. Please check your account billing."
                    logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                    raise HTTPException(status_code=500, detail=error_detail)
                
                result = response.json()
                sigma_response = result['choices'][0]['message']['content']
            
            # Clean the response and extract YAML rules
            cleaned_response = clean_sigma_rule(sigma_response)
            
            # Parse and validate the rules
            attempt_validation_results = []
            attempt_rules = []
            all_valid = True
            
            # Split response into individual rules (separated by --- or multiple yaml blocks)
            rule_blocks = cleaned_response.split('---')
            for i, block in enumerate(rule_blocks):
                block = block.strip()
                if not block or not block.startswith('title:'):
                    continue
                    
                try:
                    validation_result = validate_sigma_rule(block)
                    validation_result.rule_index = i + 1
                    attempt_validation_results.append(validation_result)
                    
                    if validation_result.is_valid:
                        attempt_rules.append({
                            'content': block,
                            'title': validation_result.metadata.get('title', f'Rule {i+1}'),
                            'level': validation_result.metadata.get('level', 'medium'),
                            'validated': True
                        })
                    else:
                        all_valid = False
                        attempt_rules.append({
                            'content': block,
                            'title': f'Rule {i+1} (Validation Failed)',
                            'level': 'low',
                            'validated': False,
                            'errors': validation_result.errors
                        })
                except Exception as e:
                    logger.error(f"SIGMA rule validation error: {e}")
                    all_valid = False
                    attempt_rules.append({
                        'content': block,
                        'title': f'Rule {i+1} (Parse Error)',
                        'level': 'low',
                        'validated': False,
                        'errors': [str(e)]
                    })
            
            # Store conversation log entry
            conversation_log.append({
                'attempt': attempt + 1,
                'messages': [
                    {
                        'role': 'system',
                        'content': 'You are a senior cybersecurity detection engineer specializing in SIGMA rule creation.'
                    },
                    {
                        'role': 'user',
                        'content': current_prompt
                    }
                ],
                'llm_response': sigma_response,
                'validation': attempt_validation_results,
                'all_valid': all_valid,
                'error': None
            })
            
            # Update validation results and rules
            validation_results = attempt_validation_results
            rules = attempt_rules
            
            # If all rules are valid, break the loop
            if all_valid:
                logger.info(f"SIGMA generation successful on attempt {attempt + 1}")
                break
            else:
                logger.info(f"SIGMA generation attempt {attempt + 1} had validation errors, retrying...")
        
        # Log final results
        if validation_results and all(result.is_valid for result in validation_results):
            logger.info(f"SIGMA generation completed successfully after {len(conversation_log)} attempts")
        else:
            logger.warning(f"SIGMA generation completed with errors after {len(conversation_log)} attempts")
        
        # Update article metadata with generated SIGMA rules
        current_metadata = article.article_metadata or {}
        current_metadata['sigma_rules'] = {
            'rules': rules,
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'ai_model': ai_model,
                'author': author_name,
                'total_rules': len(rules),
                'valid_rules': len([r for r in rules if r.get('validated', False)]),
                'validation_results': validation_results,
                'conversation': conversation_log,
                'attempts': len(conversation_log),
                'successful': len(conversation_log) > 0 and all(result.is_valid for result in validation_results),
                'optimization': {
                    'enabled': True,
                    'cost_savings': cost_savings,
                    'tokens_saved': tokens_saved,
                    'chunks_removed': chunks_removed,
                    'min_confidence': min_confidence
                }
            }
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(article_metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": len(rules) > 0,
            "rules": rules,
            "metadata": current_metadata['sigma_rules']['metadata'],
            "cached": False,
            "error": None if len(rules) > 0 else "No valid SIGMA rules could be generated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SIGMA rules generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/custom-prompt")
async def api_custom_prompt(article_id: int, request: Request):
    """Process a custom AI prompt for an article."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        prompt = body.get('prompt')
        api_key = body.get('api_key')
        ai_model = body.get('ai_model', 'chatgpt')
        
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        # Only require API key for cloud-based models
        if ai_model in ['chatgpt', 'anthropic'] and not api_key:
            key_type = 'OpenAI' if ai_model == 'chatgpt' else 'Anthropic'
            raise HTTPException(status_code=400, detail=f"{key_type} API key is required. Please configure it in Settings.")
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # Create the full prompt with article context
        full_prompt = f"""Article Title: {article.title}
Source: {source_name}
URL: {article.canonical_url or 'N/A'}

Article Content:
{article.content}

User Request: {prompt}

Please provide a detailed analysis based on the article content and the user's request."""
        
        # Call the appropriate AI API
        if ai_model == 'anthropic':
            # Use Anthropic API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": "claude-sonnet-4-5",
                        "max_tokens": 2000,
                        "messages": [
                            {
                                "role": "user",
                                "content": full_prompt
                            }
                        ]
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Anthropic API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"Anthropic API error: {error_detail}")
                
                result = response.json()
                analysis = result['content'][0]['text']
                model_used = 'anthropic'
                model_name = 'claude-sonnet-4-5'
        elif ai_model == 'ollama':
            # Use Ollama API
            ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": "llama3.2:1b",
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 2000
                        }
                    },
                    timeout=300.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Ollama API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"Ollama API error: {error_detail}")
                
                result = response.json()
                analysis = result['response']
                model_used = 'ollama'
                model_name = 'llama3.2:1b'
        elif ai_model == 'tinyllama':
            # Use Ollama API with TinyLlama
            ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": "tinyllama",
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 2000
                        }
                    },
                    timeout=300.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Ollama API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"Ollama API error: {error_detail}")
                
                result = response.json()
                analysis = result['response']
                model_used = 'tinyllama'
                model_name = 'tinyllama'
        elif ai_model == 'lmstudio':
            # Use LMStudio API
            lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
            lmstudio_model = os.getenv("LMSTUDIO_MODEL", "llama-3.2-1b-instruct")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{lmstudio_url}/chat/completions",
                    headers={
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": lmstudio_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": full_prompt
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3
                    },
                    timeout=300.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"LMStudio API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"LMStudio API error: {error_detail}")
                
                result = response.json()
                analysis = result['choices'][0]['message']['content']
                model_used = 'lmstudio'
                model_name = lmstudio_model
        else:
            # Use OpenAI API (default)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {
                                "role": "user",
                                "content": full_prompt
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"OpenAI API error: {error_detail}")
                    raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
                
                result = response.json()
                analysis = result['choices'][0]['message']['content']
                model_used = 'openai'
                model_name = 'gpt-4o'
        
        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}
        
        article.article_metadata['custom_prompt'] = {
            'prompt': prompt,
            'response': analysis,
            'analyzed_at': datetime.now().isoformat(),
            'model_used': model_used,
            'model_name': model_name
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "response": analysis,
            "analyzed_at": article.article_metadata['custom_prompt']['analyzed_at'],
            "model_used": model_used,
            "model_name": model_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom prompt error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
