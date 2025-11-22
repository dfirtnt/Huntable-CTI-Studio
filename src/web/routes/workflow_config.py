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
    agent_models: Optional[Dict[str, Any]] = None  # Changed from Dict[str, str] to allow None values
    qa_enabled: Optional[Dict[str, bool]] = None
    sigma_fallback_enabled: bool = False
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
    agent_models: Optional[Dict[str, Any]] = None  # Changed from Dict[str, str] to allow numeric temperatures
    qa_enabled: Optional[Dict[str, bool]] = None
    sigma_fallback_enabled: Optional[bool] = False


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
                    description="Default configuration",
                    sigma_fallback_enabled=False,
                    qa_enabled={}
                )
                db_session.add(config)
                db_session.commit()
                db_session.refresh(config)
            
            # Ensure agent_models, agent_prompts, and qa_enabled are properly serialized
            # JSONB fields should already be dicts, but ensure they're not None
            agent_models = config.agent_models if config.agent_models is not None else {}
            agent_prompts = config.agent_prompts if config.agent_prompts is not None else {}
            qa_enabled = config.qa_enabled if config.qa_enabled is not None else {}
            
            return WorkflowConfigResponse(
                id=config.id,
                min_hunt_score=config.min_hunt_score,
                ranking_threshold=config.ranking_threshold,
                similarity_threshold=config.similarity_threshold,
                junk_filter_threshold=config.junk_filter_threshold,
                version=config.version,
                is_active=config.is_active,
                description=config.description,
                agent_prompts=agent_prompts,
                agent_models=agent_models,
                qa_enabled=qa_enabled,
                sigma_fallback_enabled=config.sigma_fallback_enabled if hasattr(config, 'sigma_fallback_enabled') else False,
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
            sigma_fallback = config_update.sigma_fallback_enabled if config_update.sigma_fallback_enabled is not None else (current_config.sigma_fallback_enabled if current_config and hasattr(current_config, 'sigma_fallback_enabled') else False)
            
            # Merge agent_models instead of replacing (preserve existing models when updating)
            merged_agent_models = None
            if config_update.agent_models is not None:
                # Start with current config's agent_models if it exists
                if current_config and current_config.agent_models:
                    merged_agent_models = current_config.agent_models.copy()
                else:
                    merged_agent_models = {}
                # Update with new values from config_update
                merged_agent_models.update(config_update.agent_models)
                logger.info(f"Merged agent_models: {merged_agent_models} (update: {config_update.agent_models}, current: {current_config.agent_models if current_config else None})")
            elif current_config:
                merged_agent_models = current_config.agent_models
            
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=config_update.min_hunt_score if config_update.min_hunt_score is not None else (current_config.min_hunt_score if current_config else 97.0),
                ranking_threshold=ranking_threshold,
                similarity_threshold=similarity_threshold,
                junk_filter_threshold=junk_filter_threshold,
                version=new_version,
                is_active=True,
                description=config_update.description or (current_config.description if current_config else "Updated configuration"),
                agent_prompts=config_update.agent_prompts if config_update.agent_prompts is not None else (current_config.agent_prompts if current_config else None),
                agent_models=merged_agent_models,
                qa_enabled=config_update.qa_enabled if config_update.qa_enabled is not None else (current_config.qa_enabled if current_config and current_config.qa_enabled is not None else {}),
                sigma_fallback_enabled=sigma_fallback
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
                agent_models=new_config.agent_models,
                qa_enabled=new_config.qa_enabled,
                sigma_fallback_enabled=new_config.sigma_fallback_enabled,
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
            
            # Get model names from config first, then fall back to environment
            import os
            default_model = os.getenv("LMSTUDIO_MODEL", "mistralai/mistral-7b-instruct-v0.3")
            rank_model_env = os.getenv("LMSTUDIO_MODEL_RANK", "").strip()
            extract_model_env = os.getenv("LMSTUDIO_MODEL_EXTRACT", "").strip()
            sigma_model_env = os.getenv("LMSTUDIO_MODEL_SIGMA", "").strip()
            
            # Use config models if available, otherwise fall back to env vars
            agent_models = config.agent_models if config.agent_models is not None else {}
            rank_model = agent_models.get("RankAgent") or rank_model_env or "[Not configured - requires LMSTUDIO_MODEL_RANK]"
            extract_model = agent_models.get("ExtractAgent") or extract_model_env or default_model
            sigma_model = agent_models.get("SigmaAgent") or sigma_model_env or default_model
            
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
                    "instructions": extract_instructions,
                    "model": extract_model
                }
            
            # RankAgent
            rank_prompt_path = prompts_dir / "lmstudio_sigma_ranking.txt"
            if rank_prompt_path.exists():
                with open(rank_prompt_path, 'r') as f:
                    rank_prompt = f.read()
                default_prompts["RankAgent"] = {
                    "prompt": rank_prompt,
                    "instructions": "",
                    "model": rank_model
                }
            
            # SigmaAgent
            sigma_prompt_path = prompts_dir / "sigma_generation.txt"
            if sigma_prompt_path.exists():
                with open(sigma_prompt_path, 'r') as f:
                    sigma_prompt = f.read()
                default_prompts["SigmaAgent"] = {
                    "prompt": sigma_prompt,
                    "instructions": "",
                    "model": sigma_model
                }
            
            # QAAgent
            qa_agent_path = prompts_dir / "QAAgentCMD"
            if qa_agent_path.exists():
                with open(qa_agent_path, 'r') as f:
                    qa_prompt = f.read()
                default_prompts["QAAgent"] = {
                    "prompt": qa_prompt,
                    "instructions": "",
                    "model": extract_model  # Use extract model for QA
                }

            # --- New Sub-Agents ---
            sub_agents = [
                ("CmdlineExtract", "CmdLineQA"),
                ("SigExtract", "SigQA"),
                ("EventCodeExtract", "EventCodeQA"),
                ("ProcTreeExtract", "ProcTreeQA"),
                ("RegExtract", "RegQA")
            ]
            
            for agent_name, qa_name in sub_agents:
                # Load Extraction Agent
                agent_path = prompts_dir / agent_name
                if agent_path.exists():
                    with open(agent_path, 'r') as f:
                        prompt_content = f.read()
                    default_prompts[agent_name] = {
                        "prompt": prompt_content,
                        "instructions": "", # Instructions are inside the JSON prompt file
                        "model": extract_model
                    }
                
                # Load QA Agent
                qa_path = prompts_dir / qa_name
                if qa_path.exists():
                     with open(qa_path, 'r') as f:
                        qa_content = f.read()
                     default_prompts[qa_name] = {
                        "prompt": qa_content,
                        "instructions": "",
                        "model": extract_model
                     }

            # Merge database prompts with defaults (database takes precedence)
            if config.agent_prompts:
                for agent_name, prompt_data in config.agent_prompts.items():
                    # Preserve model info if not in database prompt data
                    if agent_name in default_prompts and "model" not in prompt_data:
                        prompt_data["model"] = default_prompts[agent_name].get("model", default_model)
                    elif agent_name not in default_prompts:
                        # Add model info for agents not in defaults
                        if agent_name == "ExtractAgent":
                            prompt_data["model"] = extract_model
                        elif agent_name == "RankAgent":
                            prompt_data["model"] = rank_model
                        elif agent_name == "SigmaAgent":
                            prompt_data["model"] = sigma_model
                        # Use extract model for sub-agents
                        elif agent_name in [a for pair in sub_agents for a in pair]:
                             prompt_data["model"] = extract_model
                        else:
                            prompt_data["model"] = default_model
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
            
            # Create new config version - preserve all fields including agent_models and qa_enabled
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=current_config.min_hunt_score,
                ranking_threshold=current_config.ranking_threshold,
                similarity_threshold=current_config.similarity_threshold,
                junk_filter_threshold=current_config.junk_filter_threshold,
                version=new_version,
                is_active=True,
                description=current_config.description or "Updated configuration",
                agent_prompts=agent_prompts,
                agent_models=current_config.agent_models.copy() if current_config.agent_models else {},
                qa_enabled=current_config.qa_enabled.copy() if current_config.qa_enabled else {}
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


class TestSubAgentRequest(BaseModel):
    """Request model for testing a sub-agent."""
    article_id: int = Field(1427, description="Article ID to test with")
    agent_name: str = Field(..., description="Name of the sub-agent (e.g., SigExtract, EventCodeExtract)")


class TestRankAgentRequest(BaseModel):
    """Request model for testing Rank Agent."""
    article_id: int = Field(1427, description="Article ID to test with")


@router.post("/config/test-subagent")
async def test_sub_agent(request: Request, test_request: TestSubAgentRequest):
    """Test a sub-agent extraction on a specific article."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get article
            from src.database.models import ArticleTable
            article = db_session.query(ArticleTable).filter(ArticleTable.id == test_request.article_id).first()
            if not article:
                raise HTTPException(status_code=404, detail=f"Article {test_request.article_id} not found")
            
            # Get active config
            config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(
                AgenticWorkflowConfigTable.version.desc()
            ).first()
            
            if not config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")
            
            # Load prompt configs
            from pathlib import Path
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"
            
            agent_name = test_request.agent_name
            prompt_path = prompts_dir / agent_name
            
            if not prompt_path.exists():
                raise HTTPException(status_code=404, detail=f"Prompt file not found for {agent_name}")
            
            # Load prompt config
            import json
            with open(prompt_path, 'r') as f:
                prompt_config = json.load(f)
            
            # Load QA config if exists
            qa_agent_map = {
                "CmdlineExtract": "CmdLineQA",
                "SigExtract": "SigQA",
                "EventCodeExtract": "EventCodeQA",
                "ProcTreeExtract": "ProcTreeQA",
                "RegExtract": "RegQA"
            }
            qa_name = qa_agent_map.get(agent_name)
            qa_prompt_config = None
            if qa_name:
                qa_path = prompts_dir / qa_name
                if qa_path.exists():
                    with open(qa_path, 'r') as f:
                        qa_prompt_config = json.load(f)
            
            # Check if QA is enabled for this agent
            qa_enabled = config.qa_enabled or {}
            use_qa = qa_enabled.get(agent_name, False) and qa_prompt_config
            
            # Initialize LLM service
            from src.services.llm_service import LLMService
            agent_models = config.agent_models if config.agent_models else {}
            llm_service = LLMService(config_models=agent_models)
            
            # Get model and temperature for this agent
            model_key = f"{agent_name}_model"
            temperature_key = f"{agent_name}_temperature"
            agent_model = agent_models.get(model_key) or agent_models.get("ExtractAgent")
            agent_temperature = agent_models.get(temperature_key, 0.0)
            
            # Run extraction agent
            result = await llm_service.run_extraction_agent(
                agent_name=agent_name,
                content=article.content,
                title=article.title,
                url=article.canonical_url or "",
                prompt_config=prompt_config,
                qa_prompt_config=qa_prompt_config if use_qa else None,
                max_retries=5,
                execution_id=None,
                model_name=agent_model,
                temperature=float(agent_temperature),
                qa_model_override=agent_models.get(qa_name)
            )
            
            return {
                "success": True,
                "agent_name": agent_name,
                "article_id": test_request.article_id,
                "article_title": article.title,
                "qa_enabled": use_qa,
                "result": result
            }
            
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        # Check if error is related to LMStudio being busy
        is_lmstudio_busy = (
            "generator didn't stop after throw" in error_msg.lower() or
            "timeout" in error_msg.lower() or
            "overloaded" in error_msg.lower() or
            "cannot connect" in error_msg.lower() or
            "connection" in error_msg.lower()
        )
        
        if is_lmstudio_busy:
            logger.error(f"Error testing sub-agent (LMStudio may be busy): {e}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail=(
                    "LMStudio appears to be busy or unavailable. "
                    "The model may be processing another request. "
                    "Would you like to wait and try again, or retry later?"
                )
            )
        else:
            logger.error(f"Error testing sub-agent: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/test-rankagent")
async def test_rank_agent(request: Request, test_request: TestRankAgentRequest):
    """Test Rank Agent on a specific article."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Get article
            from src.database.models import ArticleTable
            article = db_session.query(ArticleTable).filter(ArticleTable.id == test_request.article_id).first()
            if not article:
                raise HTTPException(status_code=404, detail=f"Article {test_request.article_id} not found")
            
            # Get active config
            config = db_session.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(
                AgenticWorkflowConfigTable.version.desc()
            ).first()
            
            if not config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")
            
            # Initialize LLM service
            from src.services.llm_service import LLMService
            agent_models = config.agent_models if config.agent_models else {}
            logger.info(f"Testing Rank Agent with config agent_models: {agent_models}")
            rank_model = agent_models.get("RankAgent")
            if not rank_model:
                raise HTTPException(status_code=400, detail="RankAgent model not configured. Please set it in the workflow configuration.")
            logger.info(f"Using RankAgent model: {rank_model}")
            llm_service = LLMService(config_models=agent_models)
            
            # Get source name
            source_name = article.source.name if article.source else "Unknown"
            
            # Load ranking prompt
            from pathlib import Path
            prompts_dir = Path(__file__).parent.parent.parent / "prompts"
            prompt_file = prompts_dir / "lmstudio_sigma_ranking.txt"
            
            # Run ranking
            ranking_result = await llm_service.rank_article(
                title=article.title,
                content=article.content,
                source=source_name,
                url=article.canonical_url or "",
                prompt_template_path=str(prompt_file) if prompt_file.exists() else None,
                execution_id=None,
                article_id=test_request.article_id
            )
            
            return {
                "success": True,
                "agent_name": "RankAgent",
                "article_id": test_request.article_id,
                "article_title": article.title,
                "result": ranking_result
            }
            
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        # Check if error is related to LMStudio being busy
        is_lmstudio_busy = (
            "generator didn't stop after throw" in error_msg.lower() or
            "timeout" in error_msg.lower() or
            "overloaded" in error_msg.lower() or
            "cannot connect" in error_msg.lower() or
            "connection" in error_msg.lower()
        )
        
        if is_lmstudio_busy:
            logger.error(f"Error testing Rank Agent (LMStudio may be busy): {e}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail=(
                    "LMStudio appears to be busy or unavailable. "
                    "The model may be processing another request. "
                    "Would you like to wait and try again, or retry later?"
                )
            )
        else:
            logger.error(f"Error testing Rank Agent: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
