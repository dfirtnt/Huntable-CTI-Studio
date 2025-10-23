"""
AI-powered article analysis endpoints.
"""

from __future__ import annotations

import os
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
        else:
            # Use simplified prompt for local LLMs
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
                        "model": "claude-3-haiku-20240307",
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
                model_name = 'claude-3-haiku-20240307'
        else:
            # Use Ollama API
            ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
            ollama_model = os.getenv('LLM_MODEL')
            
            logger.info(f"Using Ollama at {ollama_url} with model {ollama_model}")
            
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{ollama_url}/api/generate",
                        json={
                            "model": ollama_model,
                            "prompt": sigma_prompt,
                            "stream": False,
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
                    
                    result = response.json()
                    analysis = result.get('response', 'No analysis available')
                    model_used = 'ollama'
                    model_name = ollama_model
                    logger.info(f"Successfully got ranking from Ollama: {len(analysis)} characters")
                    
                except Exception as e:
                    logger.error(f"Ollama API request failed: {e}")
                    raise HTTPException(status_code=500, detail=f"Failed to get ranking from Ollama: {str(e)}")
        
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
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required. Please configure it in Settings.")
        
        # Use the IOC extractor
        from src.utils.ioc_extractor import HybridIOCExtractor
        
        extractor = HybridIOCExtractor(use_llm_validation=use_llm_validation)
        
        # Extract IOCs from the article content
        result = await extractor.extract_iocs(
            content=article.content,
            api_key=api_key
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
                'use_llm_validation': use_llm_validation,
                'processing_time': result.processing_time,
                'raw_count': result.raw_count,
                'validated_count': result.validated_count
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
            "error": None if len(result.iocs) > 0 else "No IOCs found"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IOCs extraction error: {e}")
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
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required. Please configure it in Settings.")
        
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
                        "model": "claude-3-haiku-20240307",
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
                model_name = 'claude-3-haiku-20240307'
        else:
            # Use OpenAI API
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
