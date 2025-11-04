"""
API routes for agentic workflow configuration management.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class WorkflowConfigResponse(BaseModel):
    """Response model for workflow configuration."""
    id: int
    min_hunt_score: float
    ranking_threshold: float
    similarity_threshold: float
    junk_filter_threshold: float
    version: int
    is_active: bool
    description: Optional[str]
    agent_prompts: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str


class WorkflowConfigUpdate(BaseModel):
    """Request model for updating workflow configuration."""
    min_hunt_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    ranking_threshold: Optional[float] = Field(None, ge=0.0, le=10.0, description="Must be between 0.0 and 10.0")
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Must be between 0.0 and 1.0")
    junk_filter_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Must be between 0.0 and 1.0")
    description: Optional[str] = None
    agent_prompts: Optional[Dict[str, Any]] = None


class AgentPromptUpdate(BaseModel):
    """Request model for updating agent prompts."""
    agent_name: str
    prompt: Optional[str] = None
    instructions: Optional[str] = None
    change_description: Optional[str] = None


class RollbackRequest(BaseModel):
    """Request model for rolling back agent prompts."""
    version_id: int


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
                    junk_filter_threshold=0.8,
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
                junk_filter_threshold=config.junk_filter_threshold,
                version=config.version,
                is_active=config.is_active,
                description=config.description,
                agent_prompts=config.agent_prompts,
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
            
            # Validate thresholds
            ranking_threshold = config_update.ranking_threshold if config_update.ranking_threshold is not None else (current_config.ranking_threshold if current_config else 6.0)
            similarity_threshold = config_update.similarity_threshold if config_update.similarity_threshold is not None else (current_config.similarity_threshold if current_config else 0.5)
            junk_filter_threshold = config_update.junk_filter_threshold if config_update.junk_filter_threshold is not None else (current_config.junk_filter_threshold if current_config else 0.8)
            
            if not (0.0 <= ranking_threshold <= 10.0):
                raise HTTPException(status_code=400, detail=f"Ranking threshold must be between 0.0 and 10.0, got {ranking_threshold}")
            if not (0.0 <= similarity_threshold <= 1.0):
                raise HTTPException(status_code=400, detail=f"Similarity threshold must be between 0.0 and 1.0, got {similarity_threshold}")
            if not (0.0 <= junk_filter_threshold <= 1.0):
                raise HTTPException(status_code=400, detail=f"Junk filter threshold must be between 0.0 and 1.0, got {junk_filter_threshold}")
            
            # Create new config version
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=config_update.min_hunt_score if config_update.min_hunt_score is not None else (current_config.min_hunt_score if current_config else 97.0),
                ranking_threshold=ranking_threshold,
                similarity_threshold=similarity_threshold,
                junk_filter_threshold=junk_filter_threshold,
                version=new_version,
                is_active=True,
                description=config_update.description or (current_config.description if current_config else "Updated configuration"),
                agent_prompts=config_update.agent_prompts if config_update.agent_prompts is not None else (current_config.agent_prompts if current_config else None)
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
                junk_filter_threshold=new_config.junk_filter_threshold,
                version=new_config.version,
                is_active=new_config.is_active,
                description=new_config.description,
                agent_prompts=new_config.agent_prompts,
                created_at=new_config.created_at.isoformat(),
                updated_at=new_config.updated_at.isoformat()
            )
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error updating workflow config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/prompts")
async def get_agent_prompts(request: Request):
    """Get agent prompts from active workflow configuration."""
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
                raise HTTPException(status_code=404, detail="No active workflow configuration found")
            
            # Load default prompts from files if not in database
            from pathlib import Path
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"
            
            default_prompts = {}
            
            # ExtractAgent
            extract_agent_path = prompts_dir / "ExtractAgent"
            extract_instructions_path = prompts_dir / "ExtractAgentInstructions.txt"
            if extract_agent_path.exists() and extract_instructions_path.exists():
                with open(extract_agent_path, 'r') as f:
                    extract_prompt = f.read()
                with open(extract_instructions_path, 'r') as f:
                    extract_instructions = f.read()
                default_prompts["ExtractAgent"] = {
                    "prompt": extract_prompt,
                    "instructions": extract_instructions
                }
            
            # RankAgent
            rank_prompt_path = prompts_dir / "lmstudio_sigma_ranking.txt"
            if rank_prompt_path.exists():
                with open(rank_prompt_path, 'r') as f:
                    rank_prompt = f.read()
                default_prompts["RankAgent"] = {
                    "prompt": rank_prompt,
                    "instructions": ""
                }
            
            # SigmaAgent
            sigma_prompt_path = prompts_dir / "sigma_generation.txt"
            if sigma_prompt_path.exists():
                with open(sigma_prompt_path, 'r') as f:
                    sigma_prompt = f.read()
                default_prompts["SigmaAgent"] = {
                    "prompt": sigma_prompt,
                    "instructions": ""
                }
            
            # Merge database prompts with defaults (database takes precedence)
            if config.agent_prompts:
                for agent_name, prompt_data in config.agent_prompts.items():
                    default_prompts[agent_name] = prompt_data
            
            return {"prompts": default_prompts}
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/prompts")
async def update_agent_prompts(request: Request, prompt_update: AgentPromptUpdate):
    """Update agent prompt in active workflow configuration."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            current_config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).first()
            
            if not current_config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")
            
            # Get existing prompts or create new dict
            agent_prompts = current_config.agent_prompts.copy() if current_config.agent_prompts else {}
            
            # Get current prompt values for version history
            old_prompt = agent_prompts.get(prompt_update.agent_name, {}).get("prompt", "")
            old_instructions = agent_prompts.get(prompt_update.agent_name, {}).get("instructions", "")
            
            # Deactivate current config
            current_config.is_active = False
            new_version = current_config.version + 1
            
            # Update or create agent prompt
            if prompt_update.agent_name not in agent_prompts:
                agent_prompts[prompt_update.agent_name] = {}
            
            if prompt_update.prompt is not None:
                agent_prompts[prompt_update.agent_name]["prompt"] = prompt_update.prompt
            if prompt_update.instructions is not None:
                agent_prompts[prompt_update.agent_name]["instructions"] = prompt_update.instructions
            
            # Create new config version
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=current_config.min_hunt_score,
                ranking_threshold=current_config.ranking_threshold,
                similarity_threshold=current_config.similarity_threshold,
                junk_filter_threshold=current_config.junk_filter_threshold,
                version=new_version,
                is_active=True,
                description=current_config.description or "Updated configuration",
                agent_prompts=agent_prompts
            )
            
            db_session.add(new_config)
            db_session.flush()  # Flush to get new_config.id
            
            # Save version history
            # Get the highest version number for this agent
            max_version = db_session.query(func.max(AgentPromptVersionTable.version)).filter(
                AgentPromptVersionTable.agent_name == prompt_update.agent_name
            ).scalar() or 0
            
            prompt_version = AgentPromptVersionTable(
                agent_name=prompt_update.agent_name,
                prompt=prompt_update.prompt or old_prompt,
                instructions=prompt_update.instructions if prompt_update.instructions is not None else old_instructions,
                version=max_version + 1,
                workflow_config_version=new_version,
                change_description=prompt_update.change_description
            )
            
            db_session.add(prompt_version)
            db_session.commit()
            db_session.refresh(new_config)
            
            logger.info(f"Updated agent prompt for {prompt_update.agent_name} in config version {new_version}")
            
            return {"success": True, "message": f"Agent prompt updated for {prompt_update.agent_name}", "version": new_version}
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/prompts/{agent_name}/versions")
async def get_agent_prompt_versions(request: Request, agent_name: str):
    """Get version history for an agent prompt."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            versions = db_session.query(AgentPromptVersionTable).filter(
                AgentPromptVersionTable.agent_name == agent_name
            ).order_by(
                AgentPromptVersionTable.version.desc()
            ).all()
            
            return {
                "agent_name": agent_name,
                "versions": [
                    {
                        "id": v.id,
                        "version": v.version,
                        "prompt": v.prompt,
                        "instructions": v.instructions,
                        "workflow_config_version": v.workflow_config_version,
                        "change_description": v.change_description,
                        "created_at": v.created_at.isoformat()
                    }
                    for v in versions
                ]
            }
        finally:
            db_session.close()
            
    except Exception as e:
        logger.error(f"Error getting prompt versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/prompts/{agent_name}/rollback")
async def rollback_agent_prompt(request: Request, agent_name: str, rollback_request: RollbackRequest):
    """Rollback an agent prompt to a previous version."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get the version to rollback to
            target_version = db_session.query(AgentPromptVersionTable).filter(
                AgentPromptVersionTable.id == rollback_request.version_id,
                AgentPromptVersionTable.agent_name == agent_name
            ).first()
            
            if not target_version:
                raise HTTPException(status_code=404, detail="Version not found")
            
            # Get current active config
            current_config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).first()
            
            if not current_config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")
            
            # Deactivate current config
            current_config.is_active = False
            new_version = current_config.version + 1
            
            # Get existing prompts
            agent_prompts = current_config.agent_prompts.copy() if current_config.agent_prompts else {}
            
            # Restore prompt from target version
            agent_prompts[agent_name] = {
                "prompt": target_version.prompt,
                "instructions": target_version.instructions
            }
            
            # Create new config version
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=current_config.min_hunt_score,
                ranking_threshold=current_config.ranking_threshold,
                similarity_threshold=current_config.similarity_threshold,
                junk_filter_threshold=current_config.junk_filter_threshold,
                version=new_version,
                is_active=True,
                description=current_config.description or "Rolled back configuration",
                agent_prompts=agent_prompts
            )
            
            db_session.add(new_config)
            db_session.flush()
            
            # Create new version entry for rollback
            max_version = db_session.query(func.max(AgentPromptVersionTable.version)).filter(
                AgentPromptVersionTable.agent_name == agent_name
            ).scalar() or 0
            
            prompt_version = AgentPromptVersionTable(
                agent_name=agent_name,
                prompt=target_version.prompt,
                instructions=target_version.instructions,
                version=max_version + 1,
                workflow_config_version=new_version,
                change_description=f"Rolled back to version {target_version.version}"
            )
            
            db_session.add(prompt_version)
            db_session.commit()
            db_session.refresh(new_config)
            
            logger.info(f"Rolled back agent prompt for {agent_name} to version {target_version.version}")
            
            return {"success": True, "message": f"Rolled back {agent_name} to version {target_version.version}", "version": new_version}
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back agent prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))

