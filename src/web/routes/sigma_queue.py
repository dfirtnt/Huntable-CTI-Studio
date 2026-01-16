"""
API routes for SIGMA rule queue management.
"""

import logging
import json
import os
import httpx
import yaml
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleQueueTable, ArticleTable, EnrichmentPromptVersionTable, EnrichmentPresetTable
from src.utils.prompt_loader import format_prompt
from src.utils.content_filter import ContentFilter
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_validator import validate_sigma_rule
from src.services.sigma_pr_service import SigmaPRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-queue", tags=["sigma-queue"])


class QueuedRuleResponse(BaseModel):
    """Response model for queued rule."""
    id: int
    article_id: int
    article_title: Optional[str]
    workflow_execution_id: Optional[int]
    rule_yaml: str
    rule_metadata: Optional[Dict[str, Any]]
    similarity_scores: Optional[List[Dict[str, Any]]]
    max_similarity: Optional[float]
    status: str
    reviewed_by: Optional[str]
    review_notes: Optional[str]
    pr_submitted: bool
    pr_url: Optional[str]
    created_at: str
    reviewed_at: Optional[str]


class QueueUpdateRequest(BaseModel):
    """Request model for updating queue status."""
    status: Optional[str] = None  # pending, approved, rejected, submitted
    review_notes: Optional[str] = None
    pr_url: Optional[str] = None
    pr_repository: Optional[str] = None
    rule_yaml: Optional[str] = None  # Updated rule YAML content


class RuleYamlUpdateRequest(BaseModel):
    """Request model for updating rule YAML."""
    rule_yaml: str


class EnrichRuleRequest(BaseModel):
    """Request model for enriching a rule."""
    instruction: Optional[str] = None  # Optional user instruction for enrichment
    system_prompt: Optional[str] = None  # Optional system prompt override
    current_rule_yaml: Optional[str] = None  # Optional current rule YAML for iterative enrichment
    provider: Optional[str] = None  # LLM provider (openai, anthropic, gemini)
    model: Optional[str] = None  # Model name
    include_article_content: Optional[bool] = False  # Include junk-filtered article content


class ValidateRuleRequest(BaseModel):
    """Request model for validating a rule."""
    provider: Optional[str] = None  # LLM provider (openai, anthropic, gemini, lmstudio)
    model: Optional[str] = None  # Model name


class SavePromptRequest(BaseModel):
    """Request model for saving a prompt version."""
    system_prompt: str
    user_instruction: Optional[str] = None
    change_description: Optional[str] = None


class SavePresetRequest(BaseModel):
    """Request model for saving an enrichment preset."""
    name: str
    description: Optional[str] = None
    provider: str
    model: str
    system_prompt: str
    user_instruction: Optional[str] = None


@router.get("/list", response_model=List[QueuedRuleResponse])
async def list_queued_rules(request: Request, status: Optional[str] = None, limit: int = 50):
    """List queued SIGMA rules."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            query = db_session.query(SigmaRuleQueueTable)
            
            if status:
                query = query.filter(SigmaRuleQueueTable.status == status)
            
            rules = query.order_by(SigmaRuleQueueTable.created_at.desc()).limit(limit).all()
            
            result = []
            matching_service = None  # Lazy initialization
            
            for rule in rules:
                # Get article title
                article = db_session.query(ArticleTable).filter(ArticleTable.id == rule.article_id).first()
                
                # Calculate max_similarity on-the-fly if missing
                max_similarity = rule.max_similarity
                if max_similarity is None:
                    try:
                        # Lazy initialize matching service
                        if matching_service is None:
                            matching_service = SigmaMatchingService(db_session)
                        
                        # Parse rule YAML
                        rule_dict = yaml.safe_load(rule.rule_yaml) if rule.rule_yaml else {}
                        if rule_dict and rule_dict.get('title') and rule_dict.get('detection'):
                            # Normalize rule structure
                            normalized_rule = {
                                'title': rule_dict.get('title', ''),
                                'description': rule_dict.get('description', ''),
                                'tags': rule_dict.get('tags', []),
                                'logsource': rule_dict.get('logsource', {}),
                                'detection': rule_dict.get('detection', {}),
                                'level': rule_dict.get('level'),
                                'status': rule_dict.get('status', 'experimental'),
                            }
                            
                            # Calculate similarity using algorithmic evaluator
                            similar_matches = matching_service.compare_proposed_rule_to_embeddings(
                                proposed_rule=normalized_rule,
                                threshold=0.0,  # Get all matches
                            )
                            
                            # Calculate max similarity
                            max_similarity = max([m.get('similarity', 0.0) for m in similar_matches], default=0.0) if similar_matches else 0.0
                            
                            # Store in database for future use
                            rule.max_similarity = max_similarity
                            rule.similarity_scores = similar_matches[:10]  # Store top 10
                            db_session.commit()
                            logger.info(f"Calculated and stored max_similarity={max_similarity:.3f} for queued rule {rule.id}")
                    except Exception as e:
                        logger.warning(f"Failed to calculate max_similarity for queued rule {rule.id}: {e}")
                        # Keep max_similarity as None if calculation fails
                        max_similarity = None
                
                result.append(QueuedRuleResponse(
                    id=rule.id,
                    article_id=rule.article_id,
                    article_title=article.title if article else None,
                    workflow_execution_id=rule.workflow_execution_id,
                    rule_yaml=rule.rule_yaml,
                    rule_metadata=rule.rule_metadata,
                    similarity_scores=rule.similarity_scores,
                    max_similarity=max_similarity,
                    status=rule.status,
                    reviewed_by=rule.reviewed_by,
                    review_notes=rule.review_notes,
                    pr_submitted=rule.pr_submitted,
                    pr_url=rule.pr_url,
                    created_at=rule.created_at.isoformat(),
                    reviewed_at=rule.reviewed_at.isoformat() if rule.reviewed_at else None
                ))
            
            return result
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error listing queued rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{queue_id}/approve")
async def approve_queued_rule(request: Request, queue_id: int, update: QueueUpdateRequest):
    """Approve a queued rule."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            rule = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == queue_id).first()
            if not rule:
                raise HTTPException(status_code=404, detail="Queued rule not found")
            
            rule.status = update.status or "approved"
            rule.reviewed_at = datetime.now()
            rule.review_notes = update.review_notes
            rule.reviewed_by = "system"  # TODO: Get from auth context
            
            # Update rule YAML if provided
            if update.rule_yaml:
                rule.rule_yaml = update.rule_yaml
            
            if update.pr_url:
                rule.pr_url = update.pr_url
                rule.pr_repository = update.pr_repository
                rule.pr_submitted = True
                rule.submitted_at = datetime.now()
            
            db_session.commit()
            
            return {"success": True, "message": f"Rule {queue_id} approved"}
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving queued rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{queue_id}/reject")
async def reject_queued_rule(request: Request, queue_id: int):
    """Reject a queued rule."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            rule = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == queue_id).first()
            if not rule:
                raise HTTPException(status_code=404, detail="Queued rule not found")
            
            rule.status = "rejected"
            rule.reviewed_at = datetime.now()
            rule.reviewed_by = "system"  # TODO: Get from auth context
            
            # Try to parse JSON body first (new format with rule_yaml support)
            try:
                body = await request.json()
                if body:
                    rule.review_notes = body.get("review_notes")
                    if body.get("rule_yaml"):
                        rule.rule_yaml = body["rule_yaml"]
            except:
                # Fall back to query params (backward compatibility)
                review_notes = request.query_params.get("review_notes")
                if review_notes:
                    rule.review_notes = review_notes
            
            db_session.commit()
            
            return {"success": True, "message": f"Rule {queue_id} rejected"}
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting queued rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{queue_id}/yaml")
async def update_rule_yaml(request: Request, queue_id: int, update: RuleYamlUpdateRequest):
    """Update the YAML content of a queued rule."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            rule = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == queue_id).first()
            if not rule:
                raise HTTPException(status_code=404, detail="Queued rule not found")
            
            rule.rule_yaml = update.rule_yaml
            db_session.commit()
            
            return {"success": True, "message": f"Rule {queue_id} YAML updated"}
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating rule YAML: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _sanitize_error_detail(detail: str) -> str:
    """Sanitize error detail to prevent serialization issues."""
    if not detail:
        return "Unknown error"
    # Replace all problematic characters
    sanitized = str(detail).replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    # Remove any control characters
    sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
    return sanitized.strip()


@router.post("/{queue_id}/enrich")
async def enrich_rule(request: Request, queue_id: int, enrich_request: EnrichRuleRequest):
    """Enrich a SIGMA rule using AI assistance."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            rule = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == queue_id).first()
            if not rule:
                raise HTTPException(status_code=404, detail="Queued rule not found")
            
            # Get article for context
            article = db_session.query(ArticleTable).filter(ArticleTable.id == rule.article_id).first()
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            
            # Get provider and model from request, default to OpenAI
            provider = (enrich_request.provider or "openai").lower()
            model = enrich_request.model or "gpt-4o-mini"
            
            # Get API key from request headers (not needed for LMStudio)
            api_key = None
            if provider == "openai":
                api_key = request.headers.get("X-OpenAI-API-Key")
            elif provider == "anthropic":
                api_key = request.headers.get("X-Anthropic-API-Key")
            elif provider == "gemini":
                api_key = request.headers.get("X-Gemini-API-Key")
            elif provider == "lmstudio":
                # LMStudio doesn't need an API key, uses local URL
                api_key = "not_required"
            
            if provider != "lmstudio" and (not api_key or not api_key.strip()):
                raise HTTPException(
                    status_code=400,
                    detail=f"API key is required. Please provide X-{provider.capitalize()}-API-Key header. Provider: {provider}, Model: {model}",
                )
            
            # Build enrichment prompt
            instruction_text = enrich_request.instruction or "Improve and enrich this SIGMA rule with better detection logic, more comprehensive conditions, and proper metadata."
            
            # Use provided current rule YAML for iterative enrichment, or fall back to stored rule
            rule_yaml_to_enrich = enrich_request.current_rule_yaml or rule.rule_yaml
            
            # Get article content if requested (with 0.8 junk filter)
            article_content = None
            if enrich_request.include_article_content:
                try:
                    content_filter = ContentFilter()
                    hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0
                    filter_result = content_filter.filter_content(
                        article.content,
                        min_confidence=0.8,
                        hunt_score=hunt_score,
                        article_id=article.id
                    )
                    article_content = filter_result.filtered_content or article.content
                    logger.info(f"Including filtered article content ({len(article_content)} chars) for enrichment")
                except Exception as e:
                    logger.warning(f"Failed to filter article content: {e}, using original content")
                    article_content = article.content
            
            # Build prompt with optional article content
            prompt_params = {
                "rule_yaml": rule_yaml_to_enrich,
                "article_title": article.title,
                "article_url": article.canonical_url or 'N/A',
                "user_instruction": instruction_text,
            }
            
            if article_content:
                prompt_params["article_content_section"] = f"\nArticle Content (junk-filtered at 0.8 threshold):\n```\n{article_content}\n```\n"
            else:
                prompt_params["article_content_section"] = ""
            
            enrichment_prompt = format_prompt("sigma_enrichment", **prompt_params)
            
            # Use provided system prompt or fall back to default
            system_message = enrich_request.system_prompt or "You are a SIGMA rule validation and enrichment agent. Follow the OUTPUT CONTRACT: Return a JSON object with status 'pass'|'needs_revision'|'fail'. If status='pass', include 'updated_sigma_yaml' as YAML string. If status='needs_revision' or 'fail', 'updated_sigma_yaml' may be empty but 'issues' must explain. Output ONLY the JSON object, no markdown, no code blocks."
            
            logger.info(f"Enriching rule {queue_id} with provider={provider}, model={model}, has_system_prompt={bool(enrich_request.system_prompt)}")
            
            # Call provider API
            async with httpx.AsyncClient() as client:
                try:
                    if provider == "openai":
                        # gpt-4.1/gpt-5.x require max_completion_tokens (max_tokens unsupported)
                        is_newer_model = any(x in model.lower() for x in ['gpt-4.1', 'gpt-5', 'o1', 'o3', 'o4'])
                        # Some newer models (gpt-5.2+, gpt-5-nano, etc.) don't support custom temperature
                        # They only support the default value (1), so we omit the parameter
                        is_temperature_restricted = any(x in model.lower() for x in [
                            'gpt-5.2', 'gpt-5.1', 'gpt-5-nano', 'gpt-5-mini', 'gpt-5-chat'
                        ])
                        
                        payload = {
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": enrichment_prompt},
                            ],
                        }
                        
                        # Only add temperature if the model supports custom values
                        # Restricted models will use default temperature (1) if omitted
                        if not is_temperature_restricted:
                            payload["temperature"] = 0.2
                        
                        if is_newer_model:
                            payload["max_completion_tokens"] = 4000
                        else:
                            payload["max_tokens"] = 4000
                        
                        response = await client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                            timeout=120.0,
                        )
                        if response.status_code != 200:
                            error_detail = f"OpenAI API error: {response.status_code}"
                            try:
                                error_data = response.json()
                                if "error" in error_data:
                                    error_detail = error_data["error"].get("message", error_detail)
                            except:
                                error_detail = f"OpenAI API error: {response.status_code} - {response.text[:200]}"
                            
                            if response.status_code == 401:
                                error_detail = "OpenAI API key is invalid or expired. Please check your API key."
                            elif response.status_code == 429:
                                error_detail = "OpenAI API rate limit exceeded. Please wait and try again."
                            logger.error(f"OpenAI API error: {response.text}")
                            raise HTTPException(status_code=response.status_code, detail=error_detail)
                        response_data = response.json()
                        raw_response = response_data["choices"][0]["message"]["content"].strip()
                        
                    elif provider == "anthropic":
                        response = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={
                                "x-api-key": api_key,
                                "Content-Type": "application/json",
                                "anthropic-version": "2023-06-01",
                            },
                            json={
                                "model": model,
                                "max_tokens": 4000,
                                "temperature": 0.2,
                                "system": system_message,
                                "messages": [{"role": "user", "content": enrichment_prompt}],
                            },
                            timeout=120.0,
                        )
                        if response.status_code != 200:
                            error_detail = f"Anthropic API error: {response.status_code}"
                            if response.status_code == 401:
                                error_detail = "Anthropic API key is invalid or expired. Please check your API key."
                            elif response.status_code == 429:
                                error_detail = "Anthropic API rate limit exceeded. Please wait and try again."
                            logger.error(f"Anthropic API error: {response.text}")
                            raise HTTPException(status_code=response.status_code, detail=error_detail)
                        response_data = response.json()
                        content = response_data.get("content", [])
                        raw_response = content[0].get("text", "").strip() if content else ""
                        
                    elif provider == "gemini":
                        # Gemini API endpoint
                        response = await client.post(
                            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                            headers={"Content-Type": "application/json"},
                            json={
                                "contents": [{
                                    "parts": [{"text": f"{system_message}\n\n{enrichment_prompt}"}]
                                }],
                                "generationConfig": {
                                    "temperature": 0.2,
                                    "maxOutputTokens": 4000,
                                }
                            },
                            timeout=120.0,
                        )
                        if response.status_code != 200:
                            error_detail = f"Gemini API error: {response.status_code}"
                            if response.status_code == 401:
                                error_detail = "Gemini API key is invalid or expired. Please check your API key."
                            elif response.status_code == 429:
                                error_detail = "Gemini API rate limit exceeded. Please wait and try again."
                            logger.error(f"Gemini API error: {response.text}")
                            raise HTTPException(status_code=response.status_code, detail=error_detail)
                        response_data = response.json()
                        candidates = response_data.get("candidates", [])
                        raw_response = ""
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts:
                                raw_response = parts[0].get("text", "").strip()
                    
                    elif provider == "lmstudio":
                        logger.info(f"Calling LMStudio API for rule {queue_id} with model {model}")
                        # LMStudio API (OpenAI-compatible, local) with URL fallback
                        def _lmstudio_url_candidates():
                            """Generate ordered LMStudio base URL candidates."""
                            raw_url = os.getenv("LMSTUDIO_API_URL", "http://localhost:1234/v1").strip()
                            if not raw_url:
                                raw_url = "http://localhost:1234/v1"
                            
                            normalized = raw_url.rstrip("/")
                            candidates = [normalized]
                            
                            if not normalized.lower().endswith("/v1"):
                                candidates.append(f"{normalized}/v1")
                            
                            # If URL contains localhost, also try host.docker.internal (for Docker containers)
                            if "localhost" in normalized.lower() or "127.0.0.1" in normalized:
                                docker_url = normalized.replace("localhost", "host.docker.internal").replace(
                                    "127.0.0.1", "host.docker.internal"
                                )
                                if docker_url not in candidates:
                                    candidates.append(docker_url)
                                if not docker_url.lower().endswith("/v1"):
                                    docker_url_v1 = f"{docker_url}/v1"
                                    if docker_url_v1 not in candidates:
                                        candidates.append(docker_url_v1)
                            
                            # Remove duplicates while preserving order
                            seen = set()
                            unique_candidates = []
                            for candidate in candidates:
                                if candidate not in seen:
                                    unique_candidates.append(candidate)
                                    seen.add(candidate)
                            return unique_candidates
                        
                        lmstudio_urls = _lmstudio_url_candidates()
                        logger.info(f"LMStudio URL candidates for rule {queue_id}: {lmstudio_urls}")
                        # Reduced timeouts to prevent hangs - LMStudio should respond faster
                        connect_timeout = 10.0
                        read_timeout = 180.0  # 3 minutes max for response
                        last_error = None
                        raw_response = None
                        
                        for idx, lmstudio_url in enumerate(lmstudio_urls):
                            try:
                                # Ensure URL ends with /v1 but not /v1/v1
                                base_url = lmstudio_url.rstrip('/')
                                if not base_url.endswith('/v1'):
                                    if base_url.endswith('/v1/v1'):
                                        base_url = base_url[:-3]  # Remove extra /v1
                                    chat_url = f"{base_url}/v1/chat/completions"
                                else:
                                    chat_url = f"{base_url}/chat/completions"
                                
                                logger.info(f"Attempting LMStudio at {chat_url} with model {model} (attempt {idx + 1}/{len(lmstudio_urls)})")
                                
                                # Use shorter timeout to fail fast if LMStudio isn't responding
                                response = await client.post(
                                    chat_url,
                                    headers={"Content-Type": "application/json"},
                                    json={
                                        "model": model,
                                        "messages": [
                                            {"role": "system", "content": system_message},
                                            {"role": "user", "content": enrichment_prompt},
                                        ],
                                        "max_tokens": 4000,
                                        "temperature": 0.2,
                                        "stream": False,  # Ensure non-streaming response
                                    },
                                    timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=30.0, pool=10.0),
                                )
                                
                                if response.status_code == 200:
                                    try:
                                        response_data = response.json()
                                        if "choices" not in response_data or len(response_data["choices"]) == 0:
                                            last_error = "No choices in LMStudio response"
                                            logger.error(f"LMStudio response missing choices: {response_data}")
                                            if idx < len(lmstudio_urls) - 1:
                                                continue
                                            raise HTTPException(
                                                status_code=500,
                                                detail="LMStudio returned invalid response format (no choices)"
                                            )
                                        message = response_data["choices"][0].get("message", {})
                                        content = message.get("content", "")
                                        raw_response = content.strip() if content else ""
                                        logger.info(f"LMStudio request succeeded using {chat_url}, response length: {len(raw_response)}")
                                        logger.debug(f"LMStudio response structure: choices={len(response_data.get('choices', []))}, message keys={list(message.keys())}")
                                        if not raw_response:
                                            last_error = "LMStudio returned empty response content"
                                            logger.warning(f"LMStudio returned empty content. Full response structure: {json.dumps(response_data, indent=2)[:2000]}")
                                            # Check if there's a finish_reason that might explain the empty response
                                            finish_reason = response_data["choices"][0].get("finish_reason", "unknown")
                                            if finish_reason != "stop":
                                                logger.warning(f"LMStudio finish_reason: {finish_reason} (expected 'stop')")
                                            if idx < len(lmstudio_urls) - 1:
                                                continue
                                            error_detail = f"LMStudio returned empty response (finish_reason: {finish_reason}). The model may not be loaded or may have encountered an error. Please check LMStudio is running and the model is loaded."
                                            raise HTTPException(
                                                status_code=503,
                                                detail=error_detail
                                            )
                                        break
                                    except (KeyError, IndexError, json.JSONDecodeError) as e:
                                        last_error = f"Failed to parse LMStudio response: {e}"
                                        logger.error(f"LMStudio response parsing error: {e}, Response: {response.text[:500]}")
                                        if idx < len(lmstudio_urls) - 1:
                                            continue
                                        error_detail = f"Failed to parse LMStudio response: {str(e)}"
                                        error_detail = error_detail.replace('\n', ' ').replace('\r', ' ').strip()
                                        raise HTTPException(
                                            status_code=500,
                                            detail=error_detail
                                        )
                                else:
                                    # Non-200 status code
                                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                                    error_detail = f"LMStudio API error: {response.status_code}"
                                    error_text = response.text[:500] if hasattr(response, 'text') else str(response)
                                    
                                    if response.status_code == 404:
                                        error_detail = f"LMStudio model '{model}' not found. Please ensure the model is loaded in LMStudio."
                                        if idx < len(lmstudio_urls) - 1:
                                            logger.warning(f"LMStudio 404 at {chat_url}, trying next URL...")
                                            continue
                                    elif response.status_code == 503:
                                        error_detail = "LMStudio service unavailable. Please ensure LMStudio is running."
                                        if idx < len(lmstudio_urls) - 1:
                                            logger.warning(f"LMStudio 503 at {chat_url}, trying next URL...")
                                            continue
                                    
                                    logger.error(f"LMStudio API error at {chat_url}: HTTP {response.status_code}, Response: {error_text}")
                                    if idx < len(lmstudio_urls) - 1:
                                        logger.warning(f"Trying next LMStudio URL...")
                                        continue
                                    raise HTTPException(status_code=response.status_code, detail=error_detail)
                            
                            except httpx.TimeoutException:
                                last_error = f"Timeout connecting to {lmstudio_url}"
                                if idx == len(lmstudio_urls) - 1:
                                    raise HTTPException(
                                        status_code=504,
                                        detail="LMStudio request timeout - the model may be slow or overloaded. Tried URLs: " + ", ".join(lmstudio_urls)
                                    )
                                logger.warning(f"LMStudio timeout at {lmstudio_url}, trying next URL...")
                                continue
                            
                            except httpx.ConnectError as e:
                                last_error = f"Cannot connect to {lmstudio_url}: {str(e)}"
                                logger.warning(f"LMStudio connection error at {lmstudio_url}: {e}")
                                if idx == len(lmstudio_urls) - 1:
                                    error_detail = f"Cannot connect to LMStudio service. Please ensure LMStudio is running and accessible. Tried: {', '.join(lmstudio_urls)}. Last error: {str(e)}"
                                    error_detail = error_detail.replace('\n', ' ').replace('\r', ' ').strip()
                                    raise HTTPException(
                                        status_code=503,
                                        detail=error_detail
                                    )
                                logger.warning(f"LMStudio connection failed at {lmstudio_url}, trying next URL...")
                                continue
                            except Exception as e:
                                last_error = f"Unexpected error with {lmstudio_url}: {str(e)}"
                                logger.error(f"LMStudio unexpected error at {lmstudio_url}: {e}", exc_info=True)
                                if idx == len(lmstudio_urls) - 1:
                                    error_detail = f"LMStudio request failed. Tried: {', '.join(lmstudio_urls)}. Last error: {str(e)}"
                                    error_detail = error_detail.replace('\n', ' ').replace('\r', ' ').strip()
                                    raise HTTPException(
                                        status_code=500,
                                        detail=error_detail
                                    )
                                continue
                        
                        if not raw_response:
                            error_detail = f"Failed to connect to LMStudio after trying all URLs: {', '.join(lmstudio_urls)}. Last error: {last_error}"
                            error_detail = error_detail.replace('\n', ' ').replace('\r', ' ').strip()
                            raise HTTPException(
                                status_code=503,
                                detail=error_detail
                            )
                    
                    else:
                        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
                    
                    # Validate we got a response
                    if not raw_response or not raw_response.strip():
                        logger.error(f"Empty response from {provider} API for rule {queue_id}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Received empty response from {provider} API. Please try again or use a different model."
                        )
                    
                    # Try to parse as JSON first (new prompt format), fall back to YAML (legacy format)
                    enriched_yaml = None
                    enrichment_result = None
                    
                    try:
                        # Try parsing as JSON (new format with status/updated_sigma_yaml)
                        # Remove markdown code blocks if present
                        json_text = raw_response.strip()
                        if json_text.startswith("```"):
                            lines = json_text.split("\n")
                            json_text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
                            json_text = json_text.strip()
                        
                        # Try to find JSON object in the text (in case there's extra text)
                        if "{" in json_text:
                            start_idx = json_text.find("{")
                            end_idx = json_text.rfind("}") + 1
                            if end_idx > start_idx:
                                json_text = json_text[start_idx:end_idx]
                        
                        # Ensure json_text is not empty before parsing
                        if not json_text or not json_text.strip():
                            raise ValueError("Empty JSON text after cleaning")
                        
                        enrichment_result = json.loads(json_text)
                        logger.debug(f"Parsed JSON response, keys: {list(enrichment_result.keys()) if isinstance(enrichment_result, dict) else 'not a dict'}")
                        
                        # Check if it's the new JSON format
                        if isinstance(enrichment_result, dict) and "status" in enrichment_result:
                            status = enrichment_result.get("status")
                            logger.info(f"Parsed JSON enrichment response with status: {status}")
                            # Validate status is a string
                            if not isinstance(status, str):
                                logger.warning(f"Invalid status type: {type(status)}, value: {status}")
                                status = str(status) if status else "unknown"
                            if status == "pass":
                                enriched_yaml = enrichment_result.get("updated_sigma_yaml", "")
                            elif status == "needs_revision":
                                enriched_yaml = enrichment_result.get("updated_sigma_yaml", "")
                                # Log issues if present
                                issues = enrichment_result.get("issues", [])
                                if issues:
                                    logger.warning(f"Enrichment needs revision: {issues}")
                            elif status == "fail":
                                issues = enrichment_result.get("issues", [])
                                error_msg = enrichment_result.get("summary", "Enrichment failed")
                                if issues:
                                    error_details = "; ".join([f"{i.get('type', 'unknown')}: {i.get('message', '')}" for i in issues[:3]])
                                    error_msg = f"{error_msg}. {error_details}"
                                # Clean error message
                                error_msg = error_msg.replace('\n', ' ').replace('\r', ' ').strip()
                                raise HTTPException(
                                    status_code=400,
                                    detail=error_msg
                                )
                            else:
                                # Unknown status, try to extract YAML anyway
                                enriched_yaml = enrichment_result.get("updated_sigma_yaml", "")
                        else:
                            # JSON parsed but doesn't have expected structure, treat as legacy
                            logger.debug(f"JSON parsed but missing 'status' field, treating as legacy format")
                            enriched_yaml = raw_response
                    except (json.JSONDecodeError, ValueError) as e:
                        # Not JSON, treat as legacy YAML format
                        error_msg = _sanitize_error_detail(str(e))
                        # Log with repr to see exact content
                        logger.warning(f"Response is not valid JSON, treating as YAML. Error: {error_msg}, Response length: {len(raw_response)}, Response preview (first 500 chars): {repr(raw_response[:500])}")
                        enriched_yaml = raw_response
                        enrichment_result = None  # Ensure it's cleared on parse failure
                    except KeyError as e:
                        # Missing expected key in JSON, log and fall back to YAML
                        logger.warning(f"JSON response missing expected key: {e}, Response preview: {raw_response[:200]}")
                        enriched_yaml = raw_response
                        enrichment_result = None  # Ensure it's cleared on key error
                    except Exception as e:
                        # Unexpected error during JSON parsing, log and fall back to YAML
                        error_msg = _sanitize_error_detail(str(e))
                        logger.error(f"Unexpected error parsing enrichment response: {error_msg}, Type: {type(e)}, Response preview: {raw_response[:200]}", exc_info=True)
                        enriched_yaml = raw_response
                        enrichment_result = None  # Ensure it's cleared on unexpected error
                    
                    # Extract YAML from response (remove markdown code blocks if present)
                    if enriched_yaml and enriched_yaml.startswith("```"):
                        lines = enriched_yaml.split("\n")
                        enriched_yaml = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
                    
                    # Validate that we got a response
                    if not enriched_yaml or not enriched_yaml.strip():
                        logger.error(f"Empty enriched YAML received from {provider} API. Raw response: {raw_response[:500]}")
                        # If we have enrichment_result but no YAML, provide more context
                        if enrichment_result and isinstance(enrichment_result, dict):
                            status = enrichment_result.get('status', 'unknown')
                            error_detail = f"Enrichment returned status '{status}' but no YAML. "
                            issues = enrichment_result.get('issues')
                            if issues:
                                error_detail += f"Issues: {issues[:2] if isinstance(issues, list) else issues}"
                            # Sanitize error message
                            error_detail = error_detail.replace('\n', ' ').replace('\r', ' ').strip()
                            raise HTTPException(
                                status_code=400,
                                detail=error_detail
                            )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Received empty response from {provider} API. Please try again or use a different model."
                        )
                    
                    logger.info(f"Successfully enriched rule {queue_id} using {provider}/{model}, response length: {len(enriched_yaml)}")
                    
                    response_data = {
                        "success": True,
                        "enriched_yaml": enriched_yaml,
                        "raw_response": raw_response,
                        "message": f"Rule {queue_id} enriched successfully"
                    }
                    
                    # Include enrichment result metadata if available
                    if enrichment_result and isinstance(enrichment_result, dict):
                        response_data["enrichment_status"] = enrichment_result.get("status")
                        response_data["summary"] = enrichment_result.get("summary")
                        response_data["issues"] = enrichment_result.get("issues", [])
                        response_data["actions_taken"] = enrichment_result.get("actions_taken", [])
                        response_data["diff_notes"] = enrichment_result.get("diff_notes", [])
                    
                    return response_data
                except httpx.TimeoutException:
                    raise HTTPException(status_code=504, detail="Request timeout. Please try again.")
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error calling {provider} API: {e}", exc_info=True)
                    error_msg = _sanitize_error_detail(str(e) if e else "Unknown error")
                    raise HTTPException(status_code=500, detail=f"Error enriching rule: {error_msg}")
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enriching rule: {e}", exc_info=True)
        error_msg = _sanitize_error_detail(str(e) if e else "Unknown error")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/prompt/save")
async def save_prompt_version(save_request: SavePromptRequest):
    """Save a new version of the enrichment prompt."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get the latest version number
            latest = db_session.query(EnrichmentPromptVersionTable).order_by(
                EnrichmentPromptVersionTable.version.desc()
            ).first()
            
            next_version = (latest.version + 1) if latest else 1
            
            # Create new version
            prompt_version = EnrichmentPromptVersionTable(
                system_prompt=save_request.system_prompt,
                user_instruction=save_request.user_instruction,
                version=next_version,
                change_description=save_request.change_description
            )
            
            db_session.add(prompt_version)
            db_session.commit()
            db_session.refresh(prompt_version)
            
            logger.info(f"Saved prompt version {next_version}")
            
            return {
                "success": True,
                "version": next_version,
                "id": prompt_version.id,
                "created_at": prompt_version.created_at.isoformat()
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error saving prompt version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error saving prompt: {str(e)}")


@router.get("/prompt/history")
async def get_prompt_history(limit: int = 50):
    """Get history of saved prompt versions."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            versions = db_session.query(EnrichmentPromptVersionTable).order_by(
                EnrichmentPromptVersionTable.version.desc()
            ).limit(limit).all()
            
            history = [
                {
                    "id": v.id,
                    "version": v.version,
                    "system_prompt": v.system_prompt,
                    "user_instruction": v.user_instruction,
                    "change_description": v.change_description,
                    "created_at": v.created_at.isoformat()
                }
                for v in versions
            ]
            
            return {
                "success": True,
                "history": history
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting prompt history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting history: {str(e)}")


@router.get("/prompt/version/{version_id}")
async def get_prompt_version(version_id: int):
    """Get a specific prompt version by ID."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            version = db_session.query(EnrichmentPromptVersionTable).filter(
                EnrichmentPromptVersionTable.id == version_id
            ).first()
            
            if not version:
                raise HTTPException(status_code=404, detail="Prompt version not found")
            
            return {
                "success": True,
                "id": version.id,
                "version": version.version,
                "system_prompt": version.system_prompt,
                "user_instruction": version.user_instruction,
                "change_description": version.change_description,
                "created_at": version.created_at.isoformat()
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prompt version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting prompt version: {str(e)}")


@router.get("/prompt/latest")
async def get_latest_prompt_version():
    """Get the latest saved prompt version."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            latest = db_session.query(EnrichmentPromptVersionTable).order_by(
                EnrichmentPromptVersionTable.version.desc()
            ).first()
            
            if not latest:
                return {
                    "success": False,
                    "message": "No saved prompt versions found"
                }
            
            return {
                "success": True,
                "system_prompt": latest.system_prompt,
                "user_instruction": latest.user_instruction,
                "version": latest.version,
                "id": latest.id
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error getting latest prompt version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting latest prompt version: {str(e)}")


@router.get("/prompt/load/{version_id}")
async def load_prompt_version(version_id: int):
    """Load a specific prompt version (for rollback)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            version = db_session.query(EnrichmentPromptVersionTable).filter(
                EnrichmentPromptVersionTable.id == version_id
            ).first()
            
            if not version:
                raise HTTPException(status_code=404, detail="Prompt version not found")
            
            return {
                "success": True,
                "system_prompt": version.system_prompt,
                "user_instruction": version.user_instruction
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading prompt version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading prompt version: {str(e)}")


@router.post("/preset/save")
async def save_enrichment_preset(save_request: SavePresetRequest):
    """Save a new enrichment preset."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Check if preset with same name exists
            existing = db_session.query(EnrichmentPresetTable).filter(
                EnrichmentPresetTable.name == save_request.name
            ).first()
            
            if existing:
                # Update existing preset
                existing.description = save_request.description
                existing.provider = save_request.provider
                existing.model = save_request.model
                existing.system_prompt = save_request.system_prompt
                existing.user_instruction = save_request.user_instruction
                existing.updated_at = datetime.now()
                
                db_session.commit()
                db_session.refresh(existing)
                
                logger.info(f"Updated preset: {save_request.name}")
                
                return {
                    "success": True,
                    "id": existing.id,
                    "message": "Preset updated",
                    "created_at": existing.created_at.isoformat(),
                    "updated_at": existing.updated_at.isoformat()
                }
            else:
                # Create new preset
                preset = EnrichmentPresetTable(
                    name=save_request.name,
                    description=save_request.description,
                    provider=save_request.provider,
                    model=save_request.model,
                    system_prompt=save_request.system_prompt,
                    user_instruction=save_request.user_instruction
                )
                
                db_session.add(preset)
                db_session.commit()
                db_session.refresh(preset)
                
                logger.info(f"Saved preset: {save_request.name}")
                
                return {
                    "success": True,
                    "id": preset.id,
                    "message": "Preset saved",
                    "created_at": preset.created_at.isoformat(),
                    "updated_at": preset.updated_at.isoformat()
                }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error saving preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error saving preset: {str(e)}")


@router.get("/preset/list")
async def list_enrichment_presets():
    """Get list of all saved enrichment presets."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            presets = db_session.query(EnrichmentPresetTable).order_by(
                EnrichmentPresetTable.name.asc()
            ).all()
            
            preset_list = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "provider": p.provider,
                    "model": p.model,
                    "created_at": p.created_at.isoformat(),
                    "updated_at": p.updated_at.isoformat()
                }
                for p in presets
            ]
            
            return {
                "success": True,
                "presets": preset_list
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error listing presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing presets: {str(e)}")


@router.get("/preset/{preset_id}")
async def get_enrichment_preset(preset_id: int):
    """Get a specific enrichment preset by ID."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            preset = db_session.query(EnrichmentPresetTable).filter(
                EnrichmentPresetTable.id == preset_id
            ).first()
            
            if not preset:
                raise HTTPException(status_code=404, detail="Preset not found")
            
            return {
                "success": True,
                "id": preset.id,
                "name": preset.name,
                "description": preset.description,
                "provider": preset.provider,
                "model": preset.model,
                "system_prompt": preset.system_prompt,
                "user_instruction": preset.user_instruction,
                "created_at": preset.created_at.isoformat(),
                "updated_at": preset.updated_at.isoformat()
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting preset: {str(e)}")


@router.delete("/preset/{preset_id}")
async def delete_enrichment_preset(preset_id: int):
    """Delete an enrichment preset."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            preset = db_session.query(EnrichmentPresetTable).filter(
                EnrichmentPresetTable.id == preset_id
            ).first()
            
            if not preset:
                raise HTTPException(status_code=404, detail="Preset not found")
            
            db_session.delete(preset)
            db_session.commit()
            
            logger.info(f"Deleted preset: {preset_id}")
            
            return {
                "success": True,
                "message": "Preset deleted"
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting preset: {str(e)}")


class CompareRulesRequest(BaseModel):
    """Request model for comparing two rules."""
    original_rule_yaml: str
    enriched_rule_yaml: str


@router.post("/compare-similarity")
async def compare_rules_similarity(compare_request: CompareRulesRequest):
    """Compare original and enriched rules against database for similarity."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            matching_service = SigmaMatchingService(db_session)
            
            results = {
                "original": {"matches": [], "max_similarity": 0.0},
                "enriched": {"matches": [], "max_similarity": 0.0}
            }
            
            # Compare original rule
            try:
                original_yaml = yaml.safe_load(compare_request.original_rule_yaml)
                if original_yaml and original_yaml.get('detection'):
                    normalized_original = {
                        'title': original_yaml.get('title', ''),
                        'description': original_yaml.get('description', ''),
                        'tags': original_yaml.get('tags', []),
                        'logsource': original_yaml.get('logsource', {}),
                        'detection': original_yaml.get('detection', {}),
                        'level': original_yaml.get('level'),
                        'status': original_yaml.get('status', 'experimental'),
                    }
                    
                    if normalized_original['title'] and normalized_original['detection']:
                        original_matches = matching_service.compare_proposed_rule_to_embeddings(
                            proposed_rule=normalized_original,
                            threshold=0.0,
                        )
                        results["original"]["matches"] = original_matches[:10]
                        results["original"]["max_similarity"] = max(
                            [m.get('similarity', 0.0) for m in original_matches], 
                            default=0.0
                        ) if original_matches else 0.0
            except Exception as e:
                logger.warning(f"Error comparing original rule: {e}")
            
            # Compare enriched rule
            try:
                enriched_yaml = yaml.safe_load(compare_request.enriched_rule_yaml)
                if enriched_yaml and enriched_yaml.get('detection'):
                    normalized_enriched = {
                        'title': enriched_yaml.get('title', ''),
                        'description': enriched_yaml.get('description', ''),
                        'tags': enriched_yaml.get('tags', []),
                        'logsource': enriched_yaml.get('logsource', {}),
                        'detection': enriched_yaml.get('detection', {}),
                        'level': enriched_yaml.get('level'),
                        'status': enriched_yaml.get('status', 'experimental'),
                    }
                    
                    if normalized_enriched['title'] and normalized_enriched['detection']:
                        enriched_matches = matching_service.compare_proposed_rule_to_embeddings(
                            proposed_rule=normalized_enriched,
                            threshold=0.0,
                        )
                        results["enriched"]["matches"] = enriched_matches[:10]
                        results["enriched"]["max_similarity"] = max(
                            [m.get('similarity', 0.0) for m in enriched_matches], 
                            default=0.0
                        ) if enriched_matches else 0.0
            except Exception as e:
                logger.warning(f"Error comparing enriched rule: {e}")
            
            return {
                "success": True,
                "results": results
            }
            
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error comparing rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error comparing rules: {str(e)}")


@router.post("/{queue_id}/validate")
async def validate_rule(request: Request, queue_id: int, validate_request: Optional[ValidateRuleRequest] = None):
    """Validate a SIGMA rule using LLM + pySIGMA with retry loop."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            rule = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == queue_id).first()
            if not rule:
                raise HTTPException(status_code=404, detail="Queued rule not found")
            
            # Get article for context
            article = db_session.query(ArticleTable).filter(ArticleTable.id == rule.article_id).first()
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            
            # Get provider and model from request body if not in Pydantic model
            if not validate_request:
                try:
                    body = await request.json()
                    if body:
                        validate_request = ValidateRuleRequest(
                            provider=body.get("provider"),
                            model=body.get("model")
                        )
                except:
                    pass  # Body might be empty, use defaults
            
            # Get provider and model from request, default to OpenAI
            provider = (validate_request.provider if validate_request else None) or "openai"
            provider = provider.lower()
            model = (validate_request.model if validate_request else None) or "gpt-4o-mini"
            
            # Get API key from request headers (not needed for LMStudio)
            api_key = None
            if provider == "openai":
                api_key = request.headers.get("X-OpenAI-API-Key")
            elif provider == "anthropic":
                api_key = request.headers.get("X-Anthropic-API-Key")
            elif provider == "gemini":
                api_key = request.headers.get("X-Gemini-API-Key")
            elif provider == "lmstudio":
                # LMStudio doesn't need an API key, uses local URL
                api_key = "not_required"
            
            # Initialize conversation log before any early returns
            conversation_log = []
            validation_results = []
            
            if provider != "lmstudio" and (not api_key or not api_key.strip()):
                # Return error response with empty conversation log
                return {
                    "success": False,
                    "validated_yaml": None,
                    "errors": [f"API key is required. Please provide X-{provider.capitalize()}-API-Key header."],
                    "attempts": 0,
                    "message": f"API key is required for {provider}",
                    "conversation_log": conversation_log,
                    "validation_results": validation_results
                }
            
            # System message for validation (same as AI/ML Assistant modal)
            system_message = "You are a senior cybersecurity detection engineer specializing in SIGMA rule creation."
            
            # Start with the current rule YAML
            current_rule_yaml = rule.rule_yaml
            max_attempts = 3
            validation_errors = []
            enriched_yaml = None
            previous_yaml_preview = current_rule_yaml[:500] if current_rule_yaml else ""
            
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Validation attempt {attempt}/{max_attempts} for rule {queue_id} with provider={provider}, model={model}")
                
                # Build validation prompt (first attempt) or feedback prompt (subsequent attempts)
                try:
                    if attempt == 1:
                        # First attempt: Ask to validate and fix the existing rule
                        validation_prompt = f"""Validate and fix the following SIGMA rule. Ensure it is syntactically valid YAML and structurally valid according to SIGMA specifications.

Current Rule YAML:
```yaml
{current_rule_yaml}
```

**CRITICAL INSTRUCTIONS:**
1. **Output ONLY YAML - NO NARRATIVE TEXT**: Your response must start immediately with `title:` - no explanations, no "Here's the rule:", no commentary of any kind.
2. **Fix Any Validation Issues**: If the rule has syntax errors, structural issues, or missing required fields, fix them.
3. **Maintain Detection Logic**: Keep the original detection intent, but fix any syntax/structure issues.
4. **Required Structure**: Ensure your output includes ALL required fields:
   - `title:` (required)
   - `logsource:` with `category:` and `product:` (required)
   - `detection:` with `selection:` and `condition:` (required)
   - `level:` (recommended)
   - `tags:` (recommended)

**Output Format:**
Your response must be ONLY the corrected SIGMA rule in clean YAML format:
- NO markdown code blocks (no ```yaml or ```)
- NO explanatory text before or after
- Start immediately with `title:`
- Use 2-space indentation
- All field names lowercase

**Now output ONLY the validated/corrected YAML starting with 'title:':"""
                    else:
                        # Subsequent attempts: Use sigma_feedback prompt (same as AI/ML Assistant modal)
                        from src.utils.prompt_loader import format_prompt_async
                        
                        errors_text = "\n".join([f"- {err}" for err in validation_errors]) if validation_errors else "No valid SIGMA YAML detected. Output strictly valid SIGMA YAML starting with 'title:' using 2-space indentation."
                        validation_prompt = await format_prompt_async(
                            "sigma_feedback",
                            validation_errors=errors_text,
                            original_rule=previous_yaml_preview or "No YAML was detected in the previous attempt."
                        )
                except KeyError as e:
                    error_msg = f"Prompt formatting error: Missing parameter {e}"
                    logger.error(error_msg)
                    conversation_log.append({
                        'attempt': attempt,
                        'messages': [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": f"Error building prompt: {error_msg}"}
                        ],
                        'llm_response': "",
                        'validation': [],
                        'all_valid': False,
                        'error': error_msg
                    })
                    if attempt == max_attempts:
                        break
                    continue
                except Exception as e:
                    error_msg = f"Error building prompt: {str(e)}"
                    logger.error(error_msg)
                    conversation_log.append({
                        'attempt': attempt,
                        'messages': [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": f"Error building prompt: {error_msg}"}
                        ],
                        'llm_response': "",
                        'validation': [],
                        'all_valid': False,
                        'error': error_msg
                    })
                    if attempt == max_attempts:
                        break
                    continue
                
                # Store messages for conversation log
                attempt_messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": validation_prompt}
                ]
                
                # Call provider API to enrich/fix the rule
                async with httpx.AsyncClient() as client:
                    try:
                        raw_response = None
                        error_occurred = None
                        
                        if provider == "openai":
                            # gpt-4.1/gpt-5.x require max_completion_tokens (max_tokens unsupported)
                            is_newer_model = any(x in model.lower() for x in ['gpt-4.1', 'gpt-5', 'o1', 'o3', 'o4'])
                            is_temperature_restricted = any(x in model.lower() for x in [
                                'gpt-5.2', 'gpt-5.1', 'gpt-5-nano', 'gpt-5-mini', 'gpt-5-chat'
                            ])
                            
                            payload = {
                                "model": model,
                                "messages": attempt_messages,
                            }
                            
                            if not is_temperature_restricted:
                                payload["temperature"] = 0.2
                            
                            if is_newer_model:
                                payload["max_completion_tokens"] = 4000
                            else:
                                payload["max_tokens"] = 4000
                            
                            response = await client.post(
                                "https://api.openai.com/v1/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {api_key}",
                                    "Content-Type": "application/json",
                                },
                                json=payload,
                                timeout=120.0,
                            )
                            
                            if response.status_code != 200:
                                error_detail = f"OpenAI API error: {response.status_code}"
                                if response.status_code == 401:
                                    error_detail = "OpenAI API key is invalid or expired. Please check your API key."
                                elif response.status_code == 429:
                                    error_detail = "OpenAI API rate limit exceeded. Please wait and try again."
                                logger.error(f"OpenAI API error: {response.text}")
                                error_occurred = error_detail
                                raise HTTPException(status_code=response.status_code, detail=error_detail)
                            
                            response_data = response.json()
                            raw_response = response_data["choices"][0]["message"]["content"].strip()
                            
                        elif provider == "anthropic":
                            response = await client.post(
                                "https://api.anthropic.com/v1/messages",
                                headers={
                                    "x-api-key": api_key,
                                    "Content-Type": "application/json",
                                    "anthropic-version": "2023-06-01",
                                },
                                json={
                                    "model": model,
                                    "max_tokens": 4000,
                                    "temperature": 0.2,
                                    "system": system_message,
                                    "messages": [{"role": "user", "content": enrichment_prompt}],
                                },
                                timeout=120.0,
                            )
                            
                            if response.status_code != 200:
                                error_detail = f"Anthropic API error: {response.status_code}"
                                if response.status_code == 401:
                                    error_detail = "Anthropic API key is invalid or expired. Please check your API key."
                                elif response.status_code == 429:
                                    error_detail = "Anthropic API rate limit exceeded. Please wait and try again."
                                logger.error(f"Anthropic API error: {response.text}")
                                error_occurred = error_detail
                                raise HTTPException(status_code=response.status_code, detail=error_detail)
                            
                            response_data = response.json()
                            content = response_data.get("content", [])
                            raw_response = content[0].get("text", "").strip() if content else ""
                            
                        elif provider == "gemini":
                            response = await client.post(
                                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                                headers={"Content-Type": "application/json"},
                                json={
                                    "contents": [{
                                        "parts": [{"text": f"{system_message}\n\n{enrichment_prompt}"}]
                                    }],
                                    "generationConfig": {
                                        "temperature": 0.2,
                                        "maxOutputTokens": 4000,
                                    }
                                },
                                timeout=120.0,
                            )
                            
                            if response.status_code != 200:
                                error_detail = f"Gemini API error: {response.status_code}"
                                if response.status_code == 401:
                                    error_detail = "Gemini API key is invalid or expired. Please check your API key."
                                elif response.status_code == 429:
                                    error_detail = "Gemini API rate limit exceeded. Please wait and try again."
                                logger.error(f"Gemini API error: {response.text}")
                                error_occurred = error_detail
                                raise HTTPException(status_code=response.status_code, detail=error_detail)
                            
                            response_data = response.json()
                            candidates = response_data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts:
                                    raw_response = parts[0].get("text", "").strip()
                        
                        elif provider == "lmstudio":
                            # LMStudio API (OpenAI-compatible, local)
                            def _lmstudio_url_candidates():
                                raw_url = os.getenv("LMSTUDIO_API_URL", "http://localhost:1234/v1").strip()
                                if not raw_url:
                                    raw_url = "http://localhost:1234/v1"
                                normalized = raw_url.rstrip("/")
                                candidates = [normalized]
                                if not normalized.lower().endswith("/v1"):
                                    candidates.append(f"{normalized}/v1")
                                if "localhost" in normalized.lower() or "127.0.0.1" in normalized:
                                    docker_url = normalized.replace("localhost", "host.docker.internal").replace(
                                        "127.0.0.1", "host.docker.internal"
                                    )
                                    if docker_url not in candidates:
                                        candidates.append(docker_url)
                                    if not docker_url.lower().endswith("/v1"):
                                        docker_url_v1 = f"{docker_url}/v1"
                                        if docker_url_v1 not in candidates:
                                            candidates.append(docker_url_v1)
                                seen = set()
                                unique_candidates = []
                                for candidate in candidates:
                                    if candidate not in seen:
                                        unique_candidates.append(candidate)
                                        seen.add(candidate)
                                return unique_candidates
                            
                            lmstudio_urls = _lmstudio_url_candidates()
                            connect_timeout = 10.0
                            read_timeout = 180.0
                            last_error = None
                            
                            for idx, lmstudio_url in enumerate(lmstudio_urls):
                                try:
                                    base_url = lmstudio_url.rstrip('/')
                                    if not base_url.endswith('/v1'):
                                        if base_url.endswith('/v1/v1'):
                                            base_url = base_url[:-3]
                                        chat_url = f"{base_url}/v1/chat/completions"
                                    else:
                                        chat_url = f"{base_url}/chat/completions"
                                    
                                    response = await client.post(
                                        chat_url,
                                        headers={"Content-Type": "application/json"},
                                        json={
                                            "model": model,
                                            "messages": attempt_messages,
                                            "max_tokens": 4000,
                                            "temperature": 0.2,
                                            "stream": False,
                                        },
                                        timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=30.0, pool=10.0),
                                    )
                                    
                                    if response.status_code == 200:
                                        response_data = response.json()
                                        if "choices" not in response_data or len(response_data["choices"]) == 0:
                                            last_error = "No choices in LMStudio response"
                                            if idx < len(lmstudio_urls) - 1:
                                                continue
                                            raise HTTPException(status_code=500, detail="LMStudio returned invalid response format")
                                        message = response_data["choices"][0].get("message", {})
                                        content = message.get("content", "")
                                        raw_response = content.strip() if content else ""
                                        if not raw_response:
                                            last_error = "LMStudio returned empty response"
                                            if idx < len(lmstudio_urls) - 1:
                                                continue
                                            raise HTTPException(status_code=503, detail="LMStudio returned empty response")
                                        break
                                    else:
                                        last_error = f"HTTP {response.status_code}"
                                        if response.status_code == 404:
                                            if idx < len(lmstudio_urls) - 1:
                                                continue
                                        elif response.status_code == 503:
                                            if idx < len(lmstudio_urls) - 1:
                                                continue
                                        if idx == len(lmstudio_urls) - 1:
                                            raise HTTPException(status_code=response.status_code, detail=f"LMStudio API error: {last_error}")
                                except Exception as e:
                                    if idx == len(lmstudio_urls) - 1:
                                        raise
                                    continue
                            
                            if not raw_response:
                                raise HTTPException(status_code=503, detail=f"LMStudio failed on all URLs: {last_error}")
                        else:
                            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
                        
                        if not raw_response:
                            error_occurred = "Empty response from LLM"
                            raise HTTPException(status_code=500, detail="LLM returned empty response")
                        
                        # Extract YAML from response (remove markdown code blocks if present)
                        enriched_yaml = raw_response
                        if enriched_yaml.startswith("```"):
                            lines = enriched_yaml.split("\n")
                            enriched_yaml = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
                        
                        # Validate with pySIGMA
                        validation_result = validate_sigma_rule(enriched_yaml)
                        attempt_validation_results = [validation_result]
                        all_valid = validation_result.is_valid
                        
                        # Store validation result
                        validation_results.append({
                            'is_valid': validation_result.is_valid,
                            'errors': validation_result.errors,
                            'warnings': validation_result.warnings,
                            'rule_index': 1
                        })
                        
                        # Store conversation log entry
                        conversation_log.append({
                            'attempt': attempt,
                            'messages': attempt_messages,
                            'llm_response': raw_response if raw_response else "",
                            'validation': [
                                {
                                    'is_valid': validation_result.is_valid,
                                    'errors': validation_result.errors,
                                    'warnings': validation_result.warnings,
                                    'rule_index': 1
                                }
                            ],
                            'all_valid': all_valid,
                            'error': None
                        })
                        
                        if validation_result.is_valid:
                            # Validation passed!
                            logger.info(f"Validation passed on attempt {attempt} for rule {queue_id}")
                            return {
                                "success": True,
                                "validated_yaml": enriched_yaml,
                                "raw_response": raw_response,
                                "attempts": attempt,
                                "message": f"Rule validated successfully after {attempt} attempt(s)",
                                "conversation_log": conversation_log,
                                "validation_results": validation_results
                            }
                        else:
                            # Validation failed, collect errors for next attempt
                            validation_errors = validation_result.errors
                            current_rule_yaml = enriched_yaml  # Use enriched version for next attempt
                            # Update previous_yaml_preview for feedback prompt (same as AI/ML Assistant modal)
                            if validation_result.content_preview:
                                previous_yaml_preview = validation_result.content_preview
                            else:
                                previous_yaml_preview = enriched_yaml[:500] if enriched_yaml else ""
                            logger.warning(f"Validation failed on attempt {attempt}: {validation_errors}")
                            
                    except httpx.TimeoutException as e:
                        error_occurred = "Request timeout"
                        conversation_log.append({
                            'attempt': attempt,
                            'messages': attempt_messages,
                            'llm_response': "",
                            'validation': [],
                            'all_valid': False,
                            'error': "Request timeout"
                        })
                        # Don't raise, continue to next attempt or return with conversation log
                        if attempt == max_attempts:
                            break  # Exit loop to return final result
                        continue
                    except HTTPException as e:
                        if not error_occurred:
                            error_occurred = f"HTTP error: {e.detail}"
                        conversation_log.append({
                            'attempt': attempt,
                            'messages': attempt_messages,
                            'llm_response': "",
                            'validation': [],
                            'all_valid': False,
                            'error': error_occurred
                        })
                        # Don't raise, continue to next attempt or return with conversation log
                        if attempt == max_attempts:
                            break  # Exit loop to return final result
                        continue
                    except Exception as e:
                        error_occurred = str(e)
                        conversation_log.append({
                            'attempt': attempt,
                            'messages': attempt_messages,
                            'llm_response': "",
                            'validation': [],
                            'all_valid': False,
                            'error': str(e)
                        })
                        logger.error(f"Error calling {provider} API: {e}")
                        # Don't raise, continue to next attempt or return with conversation log
                        if attempt == max_attempts:
                            break  # Exit loop to return final result
                        continue
            
            # All attempts failed
            logger.error(f"Validation failed after {max_attempts} attempts for rule {queue_id}")
            return {
                "success": False,
                "validated_yaml": enriched_yaml,  # Return last attempt's YAML
                "errors": validation_errors,
                "attempts": max_attempts,
                "message": f"Validation failed after {max_attempts} attempts",
                "conversation_log": conversation_log,
                "validation_results": validation_results
            }
            
        finally:
            db_session.close()
            
    except HTTPException as e:
        # If we have a conversation log, include it in the error response
        if 'conversation_log' in locals():
            return {
                "success": False,
                "validated_yaml": None,
                "errors": [str(e.detail)],
                "attempts": len(conversation_log) if 'conversation_log' in locals() else 0,
                "message": str(e.detail),
                "conversation_log": conversation_log if 'conversation_log' in locals() else [],
                "validation_results": validation_results if 'validation_results' in locals() else []
            }
        raise
    except Exception as e:
        logger.error(f"Error validating rule: {e}")
        # Return error response with conversation log if available
        if 'conversation_log' in locals():
            return {
                "success": False,
                "validated_yaml": None,
                "errors": [str(e)],
                "attempts": len(conversation_log),
                "message": f"Error validating rule: {str(e)}",
                "conversation_log": conversation_log,
                "validation_results": validation_results if 'validation_results' in locals() else []
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{queue_id}/similar-rules")
async def get_similar_rules_for_queued_rule(request: Request, queue_id: int, force: bool = False):
    """
    Compare a queued rule's YAML against existing SigmaHQ rules using behavioral novelty assessment.
    
    This endpoint directly compares the queued rule's YAML (not the article's generated rules)
    to find similar rules in the repository.
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get the queued rule
            rule = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.id == queue_id).first()
            if not rule:
                raise HTTPException(status_code=404, detail="Queued rule not found")
            
            # Parse the rule YAML
            try:
                rule_yaml = yaml.safe_load(rule.rule_yaml)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid rule YAML: {str(e)}")
            
            # Normalize rule structure
            normalized_rule = {
                'title': rule_yaml.get('title', ''),
                'description': rule_yaml.get('description', ''),
                'tags': rule_yaml.get('tags', []),
                'logsource': rule_yaml.get('logsource', {}),
                'detection': rule_yaml.get('detection', {}),
                'level': rule_yaml.get('level'),
                'status': rule_yaml.get('status', 'experimental'),
            }
            
            # Skip if essential fields are missing
            if not normalized_rule['title'] or not normalized_rule['detection']:
                raise HTTPException(
                    status_code=400,
                    detail="Rule missing essential fields (title or detection)"
                )
            
            # Use behavioral novelty assessment to find similar rules
            matching_service = SigmaMatchingService(db_session)
            similar_matches = matching_service.compare_proposed_rule_to_embeddings(
                proposed_rule=normalized_rule,
                threshold=0.0,  # No threshold - get top matches
            )
            
            # Calculate max similarity
            max_similarity = max([m.get('similarity', 0.0) for m in similar_matches], default=0.0) if similar_matches else 0.0
            
            # Update the queued rule's max_similarity if it's None or different
            if rule.max_similarity is None or abs(rule.max_similarity - max_similarity) > 0.001:
                rule.max_similarity = max_similarity
                rule.similarity_scores = similar_matches[:10]  # Store top 10
                db_session.commit()
            
            # Prepare response
            return {
                "success": True,
                "matches": similar_matches[:20],  # Return top 20
                "max_similarity": max_similarity,
                "coverage_summary": {
                    "covered": len([m for m in similar_matches if m.get('coverage_status') == 'covered']),
                    "extend": len([m for m in similar_matches if m.get('coverage_status') == 'extend']),
                    "new": len([m for m in similar_matches if m.get('coverage_status') == 'new']),
                    "total": len(similar_matches),
                },
                "assessment_method": "behavioral_novelty",
            }
            
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding similar rules for queued rule {queue_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit-pr")
async def submit_pr_for_approved_rules(request: Request):
    """Submit all approved rules as a GitHub PR."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get all approved rules that haven't been submitted
            approved_rules = db_session.query(SigmaRuleQueueTable).filter(
                SigmaRuleQueueTable.status == "approved",
                SigmaRuleQueueTable.pr_submitted == False
            ).all()
            
            if not approved_rules:
                return {
                    "success": False,
                    "error": "No approved rules to submit",
                    "message": "Please approve rules before submitting a PR"
                }
            
            # Prepare rules for PR service
            rules_data = []
            for rule in approved_rules:
                rules_data.append({
                    "id": rule.id,
                    "rule_yaml": rule.rule_yaml,
                    "article_id": rule.article_id
                })
            
            # Submit PR (create new instance to ensure fresh settings)
            pr_service = SigmaPRService()
            logger.info(f"PR Service initialized with repo_path: {pr_service.repo_path}, exists: {pr_service.repo_path.exists()}")
            result = pr_service.submit_pr(rules_data)
            
            if result.get("success"):
                # Update database records
                pr_url = result.get("pr_url")
                pr_repository = pr_service.github_repo
                
                for rule in approved_rules:
                    rule.pr_submitted = True
                    rule.pr_url = pr_url
                    rule.pr_repository = pr_repository
                    rule.submitted_at = datetime.now()
                    rule.status = "submitted"
                
                db_session.commit()
                
                return {
                    "success": True,
                    "pr_url": pr_url,
                    "branch": result.get("branch"),
                    "rules_count": result.get("rules_count", len(approved_rules)),
                    "files_added": result.get("files_added", []),
                    "message": f"Successfully created PR with {len(approved_rules)} rules"
                }
            else:
                # PR creation failed
                error_msg = result.get("error", "Unknown error")
                logger.error(f"PR submission failed: {error_msg}")
                
                return {
                    "success": False,
                    "error": error_msg,
                    "branch": result.get("branch"),  # May have branch even if PR failed
                    "files_added": result.get("files_added", [])
                }
                
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error submitting PR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

