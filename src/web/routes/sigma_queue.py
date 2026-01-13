"""
API routes for SIGMA rule queue management.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleQueueTable, ArticleTable

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
            for rule in rules:
                # Get article title
                article = db_session.query(ArticleTable).filter(ArticleTable.id == rule.article_id).first()
                
                result.append(QueuedRuleResponse(
                    id=rule.id,
                    article_id=rule.article_id,
                    article_title=article.title if article else None,
                    workflow_execution_id=rule.workflow_execution_id,
                    rule_yaml=rule.rule_yaml,
                    rule_metadata=rule.rule_metadata,
                    similarity_scores=rule.similarity_scores,
                    max_similarity=rule.max_similarity,
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

