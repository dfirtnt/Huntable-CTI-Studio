"""
API routes for agentic workflow configuration management.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class WorkflowConfigResponse(BaseModel):
    """Response model for workflow configuration."""
    id: int
    min_hunt_score: float
    ranking_threshold: float
    similarity_threshold: float
    version: int
    is_active: bool
    description: Optional[str]
    created_at: str
    updated_at: str


class WorkflowConfigUpdate(BaseModel):
    """Request model for updating workflow configuration."""
    min_hunt_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    ranking_threshold: Optional[float] = Field(None, ge=0.0, le=10.0)
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    description: Optional[str] = None


@router.get("/config", response_model=WorkflowConfigResponse)
async def get_workflow_config(request: Request):
    """Get active workflow configuration."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(
                AgenticWorkflowConfigTable.version.desc()
            ).first()
            
            if not config:
                # Create default config
                config = AgenticWorkflowConfigTable(
                    min_hunt_score=97.0,
                    ranking_threshold=6.0,
                    similarity_threshold=0.5,
                    version=1,
                    is_active=True,
                    description="Default configuration"
                )
                db_session.add(config)
                db_session.commit()
                db_session.refresh(config)
            
            return WorkflowConfigResponse(
                id=config.id,
                min_hunt_score=config.min_hunt_score,
                ranking_threshold=config.ranking_threshold,
                similarity_threshold=config.similarity_threshold,
                version=config.version,
                is_active=config.is_active,
                description=config.description,
                created_at=config.created_at.isoformat(),
                updated_at=config.updated_at.isoformat()
            )
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error getting workflow config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config", response_model=WorkflowConfigResponse)
async def update_workflow_config(request: Request, config_update: WorkflowConfigUpdate):
    """Update workflow configuration (creates new version)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Deactivate current active config
            current_config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).first()
            
            if current_config:
                current_config.is_active = False
                new_version = current_config.version + 1
            else:
                new_version = 1
            
            # Create new config version
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=config_update.min_hunt_score if config_update.min_hunt_score is not None else (current_config.min_hunt_score if current_config else 97.0),
                ranking_threshold=config_update.ranking_threshold if config_update.ranking_threshold is not None else (current_config.ranking_threshold if current_config else 6.0),
                similarity_threshold=config_update.similarity_threshold if config_update.similarity_threshold is not None else (current_config.similarity_threshold if current_config else 0.5),
                version=new_version,
                is_active=True,
                description=config_update.description or (current_config.description if current_config else "Updated configuration")
            )
            
            db_session.add(new_config)
            db_session.commit()
            db_session.refresh(new_config)
            
            logger.info(f"Updated workflow config to version {new_version}")
            
            return WorkflowConfigResponse(
                id=new_config.id,
                min_hunt_score=new_config.min_hunt_score,
                ranking_threshold=new_config.ranking_threshold,
                similarity_threshold=new_config.similarity_threshold,
                version=new_config.version,
                is_active=new_config.is_active,
                description=new_config.description,
                created_at=new_config.created_at.isoformat(),
                updated_at=new_config.updated_at.isoformat()
            )
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error updating workflow config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

