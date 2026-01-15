"""
API routes for SIGMA rule queue management.
"""

import logging
import httpx
import yaml
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleQueueTable, ArticleTable
from src.utils.prompt_loader import format_prompt
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
    current_rule_yaml: Optional[str] = None  # Optional current rule YAML for iterative enrichment


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
            
            # Get API key from request headers or body
            api_key_raw = (
                request.headers.get("X-OpenAI-API-Key")
                or request.headers.get("X-Anthropic-API-Key")
            )
            
            # If not in headers, try to get from body
            if not api_key_raw:
                try:
                    body = await request.json()
                    api_key_raw = body.get("api_key")
                except:
                    pass
            
            api_key = api_key_raw.strip() if api_key_raw else None
            
            if not api_key:
                raise HTTPException(
                    status_code=400,
                    detail="API key is required. Please provide X-OpenAI-API-Key or X-Anthropic-API-Key header, or api_key in body.",
                )
            
            # Build enrichment prompt
            instruction_text = enrich_request.instruction or "Improve and enrich this SIGMA rule with better detection logic, more comprehensive conditions, and proper metadata."
            
            # Use provided current rule YAML for iterative enrichment, or fall back to stored rule
            rule_yaml_to_enrich = enrich_request.current_rule_yaml or rule.rule_yaml
            
            enrichment_prompt = format_prompt(
                "sigma_enrichment",
                rule_yaml=rule_yaml_to_enrich,
                article_title=article.title,
                article_url=article.canonical_url or 'N/A',
                user_instruction=instruction_text
            )
            
            # Call OpenAI API
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries with proper structure. No markdown, no explanations, no code blocks.",
                                },
                                {"role": "user", "content": enrichment_prompt},
                            ],
                            "max_tokens": 4000,
                            "temperature": 0.2,
                        },
                        timeout=120.0,
                    )
                    
                    if response.status_code != 200:
                        error_detail = f"OpenAI API error: {response.status_code}"
                        if response.status_code == 401:
                            error_detail = "OpenAI API key is invalid or expired. Please check your API key."
                        elif response.status_code == 429:
                            error_detail = "OpenAI API rate limit exceeded. Please wait and try again."
                        logger.error(f"OpenAI API error: {response.text}")
                        raise HTTPException(status_code=response.status_code, detail=error_detail)
                    
                    response_data = response.json()
                    raw_response = response_data["choices"][0]["message"]["content"].strip()
                    
                    # Extract YAML from response (remove markdown code blocks if present)
                    enriched_yaml = raw_response
                    if enriched_yaml.startswith("```"):
                        lines = enriched_yaml.split("\n")
                        enriched_yaml = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
                    
                    return {
                        "success": True,
                        "enriched_yaml": enriched_yaml,
                        "raw_response": raw_response,
                        "message": f"Rule {queue_id} enriched successfully"
                    }
                except httpx.TimeoutException:
                    raise HTTPException(status_code=504, detail="Request timeout. Please try again.")
                except Exception as e:
                    logger.error(f"Error calling OpenAI API: {e}")
                    raise HTTPException(status_code=500, detail=f"Error enriching rule: {str(e)}")
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enriching rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{queue_id}/validate")
async def validate_rule(request: Request, queue_id: int):
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
            
            # Get API key from request headers (body is optional for this endpoint)
            api_key_raw = (
                request.headers.get("X-OpenAI-API-Key")
                or request.headers.get("X-Anthropic-API-Key")
            )
            
            api_key = api_key_raw.strip() if api_key_raw else None
            
            if not api_key:
                raise HTTPException(
                    status_code=400,
                    detail="API key is required. Please provide X-OpenAI-API-Key or X-Anthropic-API-Key header.",
                )
            
            # Start with the current rule YAML
            current_rule_yaml = rule.rule_yaml
            max_attempts = 3
            validation_errors = []
            enriched_yaml = None
            
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Validation attempt {attempt}/{max_attempts} for rule {queue_id}")
                
                # Build enrichment prompt (first attempt) or feedback prompt (subsequent attempts)
                if attempt == 1:
                    instruction_text = "Improve and enrich this SIGMA rule with better detection logic, more comprehensive conditions, and proper metadata. Ensure the rule is valid according to SIGMA specifications."
                    enrichment_prompt = format_prompt(
                        "sigma_enrichment",
                        rule_yaml=current_rule_yaml,
                        article_title=article.title,
                        article_url=article.canonical_url or 'N/A',
                        user_instruction=instruction_text
                    )
                else:
                    # Include validation errors in the prompt for retry
                    errors_text = "\n".join([f"- {err}" for err in validation_errors])
                    instruction_text = f"The previous attempt failed validation. Please fix the following errors:\n{errors_text}\n\nProvide a corrected SIGMA rule that addresses all these issues."
                    enrichment_prompt = format_prompt(
                        "sigma_enrichment",
                        rule_yaml=current_rule_yaml,
                        article_title=article.title,
                        article_url=article.canonical_url or 'N/A',
                        user_instruction=instruction_text
                    )
                
                # Call OpenAI API to enrich/fix the rule
                async with httpx.AsyncClient() as client:
                    try:
                        response = await client.post(
                            "https://api.openai.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json={
                                "model": "gpt-4o-mini",
                                "messages": [
                                    {
                                        "role": "system",
                                        "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries with proper structure. No markdown, no explanations, no code blocks.",
                                    },
                                    {"role": "user", "content": enrichment_prompt},
                                ],
                                "max_tokens": 4000,
                                "temperature": 0.2,
                            },
                            timeout=120.0,
                        )
                        
                        if response.status_code != 200:
                            error_detail = f"OpenAI API error: {response.status_code}"
                            if response.status_code == 401:
                                error_detail = "OpenAI API key is invalid or expired. Please check your API key."
                            elif response.status_code == 429:
                                error_detail = "OpenAI API rate limit exceeded. Please wait and try again."
                            logger.error(f"OpenAI API error: {response.text}")
                            raise HTTPException(status_code=response.status_code, detail=error_detail)
                        
                        response_data = response.json()
                        raw_response = response_data["choices"][0]["message"]["content"].strip()
                        
                        # Extract YAML from response (remove markdown code blocks if present)
                        enriched_yaml = raw_response
                        if enriched_yaml.startswith("```"):
                            lines = enriched_yaml.split("\n")
                            enriched_yaml = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
                        
                        # Validate with pySIGMA
                        validation_result = validate_sigma_rule(enriched_yaml)
                        
                        if validation_result.is_valid:
                            # Validation passed!
                            logger.info(f"Validation passed on attempt {attempt} for rule {queue_id}")
                            return {
                                "success": True,
                                "validated_yaml": enriched_yaml,
                                "raw_response": raw_response,
                                "attempts": attempt,
                                "message": f"Rule validated successfully after {attempt} attempt(s)"
                            }
                        else:
                            # Validation failed, collect errors for next attempt
                            validation_errors = validation_result.errors
                            current_rule_yaml = enriched_yaml  # Use enriched version for next attempt
                            logger.warning(f"Validation failed on attempt {attempt}: {validation_errors}")
                            
                    except httpx.TimeoutException:
                        raise HTTPException(status_code=504, detail="Request timeout. Please try again.")
                    except HTTPException:
                        raise
                    except Exception as e:
                        logger.error(f"Error calling OpenAI API: {e}")
                        raise HTTPException(status_code=500, detail=f"Error validating rule: {str(e)}")
            
            # All attempts failed
            logger.error(f"Validation failed after {max_attempts} attempts for rule {queue_id}")
            return {
                "success": False,
                "validated_yaml": enriched_yaml,  # Return last attempt's YAML
                "errors": validation_errors,
                "attempts": max_attempts,
                "message": f"Validation failed after {max_attempts} attempts"
            }
            
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating rule: {e}")
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

