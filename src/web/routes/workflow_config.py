"""
API routes for agentic workflow configuration management.
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable, WorkflowConfigPresetTable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class WorkflowConfigResponse(BaseModel):
    """Response model for workflow configuration."""

    id: int
    min_hunt_score: float
    ranking_threshold: float
    similarity_threshold: float
    junk_filter_threshold: float
    auto_trigger_hunt_score_threshold: float
    version: int
    is_active: bool
    description: str | None
    agent_prompts: dict[str, Any] | None = None
    agent_models: dict[str, Any] | None = None  # Changed from Dict[str, str] to allow None values
    qa_enabled: dict[str, bool] | None = None
    sigma_fallback_enabled: bool = False
    qa_max_retries: int = 5
    rank_agent_enabled: bool = True
    created_at: str
    updated_at: str


class WorkflowConfigUpdate(BaseModel):
    """Request model for updating workflow configuration."""

    min_hunt_score: float | None = Field(None, ge=0.0, le=100.0)
    ranking_threshold: float | None = Field(None, ge=0.0, le=10.0, description="Must be between 0.0 and 10.0")
    similarity_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Must be between 0.0 and 1.0")
    junk_filter_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Must be between 0.0 and 1.0")
    auto_trigger_hunt_score_threshold: float | None = Field(
        None, ge=0.0, le=100.0, description="RegexHuntScore threshold for auto-triggering workflows (0-100)"
    )
    description: str | None = None
    agent_prompts: dict[str, Any] | None = None
    agent_models: dict[str, Any] | None = None  # Changed from Dict[str, str] to allow numeric temperatures
    qa_enabled: dict[str, bool] | None = None
    sigma_fallback_enabled: bool | None = None
    rank_agent_enabled: bool | None = None
    qa_max_retries: int | None = Field(None, ge=1, le=20, description="Maximum QA retry attempts (1-20)")


class AgentPromptUpdate(BaseModel):
    """Request model for updating agent prompts."""

    agent_name: str
    prompt: str | None = None
    instructions: str | None = None
    change_description: str | None = None


class RollbackRequest(BaseModel):
    """Request model for rolling back agent prompts."""

    version_id: int


class SaveConfigPresetRequest(BaseModel):
    """Request model for saving a workflow config preset."""

    name: str
    description: str | None = None
    config: dict[str, Any]


@router.get("/config", response_model=WorkflowConfigResponse)
async def get_workflow_config(request: Request):
    """Get active workflow configuration."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .first()
            )

            if not config:
                # Create default config
                config = AgenticWorkflowConfigTable(
                    min_hunt_score=97.0,
                    ranking_threshold=6.0,
                    similarity_threshold=0.5,
                    junk_filter_threshold=0.8,
                    auto_trigger_hunt_score_threshold=60.0,
                    version=1,
                    is_active=True,
                    description="Default configuration",
                    sigma_fallback_enabled=False,
                    qa_enabled={},
                    qa_max_retries=5,
                )
                db_session.add(config)
                db_session.commit()
                db_session.refresh(config)

            # Ensure agent_models, agent_prompts, and qa_enabled are properly serialized
            # JSONB fields should already be dicts, but ensure they're not None
            agent_models = config.agent_models if config.agent_models is not None else {}
            agent_prompts = config.agent_prompts if config.agent_prompts is not None else {}
            qa_enabled = config.qa_enabled if config.qa_enabled is not None else {}

            # Get auto_trigger_hunt_score_threshold, handling both attribute access and potential None
            auto_trigger_threshold = 60.0  # default
            try:
                if hasattr(config, "auto_trigger_hunt_score_threshold"):
                    auto_trigger_threshold = (
                        config.auto_trigger_hunt_score_threshold
                        if config.auto_trigger_hunt_score_threshold is not None
                        else 60.0
                    )
            except (AttributeError, TypeError):
                pass

            return WorkflowConfigResponse(
                id=config.id,
                min_hunt_score=config.min_hunt_score,
                ranking_threshold=config.ranking_threshold,
                similarity_threshold=config.similarity_threshold,
                junk_filter_threshold=config.junk_filter_threshold,
                auto_trigger_hunt_score_threshold=auto_trigger_threshold,
                version=config.version,
                is_active=config.is_active,
                description=config.description,
                agent_prompts=agent_prompts,
                agent_models=agent_models,
                qa_enabled=qa_enabled,
                sigma_fallback_enabled=config.sigma_fallback_enabled
                if hasattr(config, "sigma_fallback_enabled")
                else False,
                qa_max_retries=config.qa_max_retries if hasattr(config, "qa_max_retries") else 5,
                rank_agent_enabled=config.rank_agent_enabled if hasattr(config, "rank_agent_enabled") else True,
                created_at=config.created_at.isoformat(),
                updated_at=config.updated_at.isoformat(),
            )
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error getting workflow config: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/config", response_model=WorkflowConfigResponse)
async def update_workflow_config(request: Request, config_update: WorkflowConfigUpdate):
    """Update workflow configuration (creates new version)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # Deactivate current active config
            # CRITICAL: Use order_by and lock to prevent race conditions
            current_config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .with_for_update()
                .first()
            )  # Lock the row to prevent concurrent updates

            if current_config:
                current_config.is_active = False
                db_session.flush()  # Ensure old config is deactivated before creating new one
                new_version = current_config.version + 1
            else:
                new_version = 1

            # Validate thresholds
            ranking_threshold = (
                config_update.ranking_threshold
                if config_update.ranking_threshold is not None
                else (current_config.ranking_threshold if current_config else 6.0)
            )
            similarity_threshold = (
                config_update.similarity_threshold
                if config_update.similarity_threshold is not None
                else (current_config.similarity_threshold if current_config else 0.5)
            )
            junk_filter_threshold = (
                config_update.junk_filter_threshold
                if config_update.junk_filter_threshold is not None
                else (current_config.junk_filter_threshold if current_config else 0.8)
            )
            auto_trigger_hunt_score_threshold = (
                config_update.auto_trigger_hunt_score_threshold
                if config_update.auto_trigger_hunt_score_threshold is not None
                else (
                    current_config.auto_trigger_hunt_score_threshold
                    if current_config and hasattr(current_config, "auto_trigger_hunt_score_threshold")
                    else 60.0
                )
            )

            if not (0.0 <= ranking_threshold <= 10.0):
                raise HTTPException(
                    status_code=400, detail=f"Ranking threshold must be between 0.0 and 10.0, got {ranking_threshold}"
                )
            if not (0.0 <= similarity_threshold <= 1.0):
                raise HTTPException(
                    status_code=400,
                    detail=f"Similarity threshold must be between 0.0 and 1.0, got {similarity_threshold}",
                )
            if not (0.0 <= junk_filter_threshold <= 1.0):
                raise HTTPException(
                    status_code=400,
                    detail=f"Junk filter threshold must be between 0.0 and 1.0, got {junk_filter_threshold}",
                )
            if not (0.0 <= auto_trigger_hunt_score_threshold <= 100.0):
                raise HTTPException(
                    status_code=400,
                    detail=f"Auto trigger hunt score threshold must be between 0.0 and 100.0, got {auto_trigger_hunt_score_threshold}",
                )

            # Create new config version
            sigma_fallback = (
                config_update.sigma_fallback_enabled
                if config_update.sigma_fallback_enabled is not None
                else (
                    current_config.sigma_fallback_enabled
                    if current_config and hasattr(current_config, "sigma_fallback_enabled")
                    else False
                )
            )
            qa_max_retries = (
                config_update.qa_max_retries
                if config_update.qa_max_retries is not None
                else (
                    current_config.qa_max_retries if current_config and hasattr(current_config, "qa_max_retries") else 5
                )
            )

            # Validate qa_max_retries
            if not (1 <= qa_max_retries <= 20):
                raise HTTPException(
                    status_code=400, detail=f"QA max retries must be between 1 and 20, got {qa_max_retries}"
                )

            # Merge agent_models instead of replacing (preserve existing models when updating)
            merged_agent_models = None
            if config_update.agent_models is not None:
                # Start with current config's agent_models if it exists
                if current_config and current_config.agent_models:
                    merged_agent_models = current_config.agent_models.copy()
                else:
                    merged_agent_models = {}
                # First, identify keys that should be removed (explicitly set to None in update)
                keys_to_remove = set()
                if config_update.agent_models:
                    for key, value in config_update.agent_models.items():
                        if value is None:
                            keys_to_remove.add(key)
                # Update with new values from config_update (excluding None values)
                for key, value in config_update.agent_models.items():
                    if value is not None:
                        merged_agent_models[key] = value
                # Remove keys that were explicitly set to None
                for key in keys_to_remove:
                    if key in merged_agent_models:
                        del merged_agent_models[key]
                logger.info(
                    f"Merged agent_models: {merged_agent_models} (update: {config_update.agent_models}, current: {current_config.agent_models if current_config else None}, removed: {list(keys_to_remove)})"
                )
            elif current_config:
                merged_agent_models = current_config.agent_models

            # Determine final values for new config
            final_min_hunt_score = (
                config_update.min_hunt_score
                if config_update.min_hunt_score is not None
                else (current_config.min_hunt_score if current_config else 97.0)
            )
            final_description = config_update.description or (
                current_config.description if current_config else "Updated configuration"
            )
            final_agent_prompts = (
                config_update.agent_prompts
                if config_update.agent_prompts is not None
                else (current_config.agent_prompts if current_config else None)
            )
            final_qa_enabled = (
                config_update.qa_enabled
                if config_update.qa_enabled is not None
                else (current_config.qa_enabled if current_config and current_config.qa_enabled is not None else {})
            )
            final_rank_agent_enabled = (
                config_update.rank_agent_enabled
                if config_update.rank_agent_enabled is not None
                else (
                    current_config.rank_agent_enabled
                    if current_config
                    and hasattr(current_config, "rank_agent_enabled")
                    and current_config.rank_agent_enabled is not None
                    else True
                )
            )

            # Validate all agent prompts are valid JSON (for extraction agents that use JSON prompts)
            if final_agent_prompts:
                extraction_agents = [
                    "CmdlineExtract",
                    "ProcTreeExtract",
                    "HuntQueriesExtract",
                    "CmdLineQA",
                    "ProcTreeQA",
                    "HuntQueriesQA",
                ]
                for agent_name, prompt_data in final_agent_prompts.items():
                    if agent_name in extraction_agents and isinstance(prompt_data, dict):
                        prompt_str = prompt_data.get("prompt")
                        if prompt_str and isinstance(prompt_str, str):
                            try:
                                json.loads(prompt_str)
                            except json.JSONDecodeError as e:
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"Invalid JSON format for {agent_name} prompt in workflow config. Please fix the prompt in the UI. Error: {e}",
                                ) from e

            # Check if the new config would be identical to the current one
            if current_config:
                # Compare all fields

                configs_identical = (
                    abs(current_config.min_hunt_score - final_min_hunt_score) < 0.0001
                    and abs(current_config.ranking_threshold - ranking_threshold) < 0.0001
                    and abs(current_config.similarity_threshold - similarity_threshold) < 0.0001
                    and abs(current_config.junk_filter_threshold - junk_filter_threshold) < 0.0001
                    and current_config.sigma_fallback_enabled == sigma_fallback
                    and current_config.qa_max_retries == qa_max_retries
                    and getattr(current_config, "rank_agent_enabled", True) == final_rank_agent_enabled
                )

                # Deep compare JSONB fields
                if configs_identical:
                    # Compare agent_models
                    current_models = current_config.agent_models or {}
                    new_models = merged_agent_models or {}
                    if json.dumps(current_models, sort_keys=True) != json.dumps(new_models, sort_keys=True):
                        configs_identical = False

                if configs_identical:
                    # Compare qa_enabled
                    current_qa = current_config.qa_enabled or {}
                    new_qa = final_qa_enabled or {}
                    if json.dumps(current_qa, sort_keys=True) != json.dumps(new_qa, sort_keys=True):
                        configs_identical = False

                if configs_identical:
                    # Compare agent_prompts
                    current_prompts = current_config.agent_prompts or {}
                    new_prompts = final_agent_prompts or {}
                    if json.dumps(current_prompts, sort_keys=True) != json.dumps(new_prompts, sort_keys=True):
                        configs_identical = False

                if configs_identical:
                    # No changes detected - reactivate current config and return it
                    current_config.is_active = True
                    db_session.commit()
                    db_session.refresh(current_config)
                    logger.info(f"No changes detected - keeping current config version {current_config.version}")

                    return WorkflowConfigResponse(
                        id=current_config.id,
                        min_hunt_score=current_config.min_hunt_score,
                        ranking_threshold=current_config.ranking_threshold,
                        similarity_threshold=current_config.similarity_threshold,
                        junk_filter_threshold=current_config.junk_filter_threshold,
                        auto_trigger_hunt_score_threshold=current_config.auto_trigger_hunt_score_threshold
                        if hasattr(current_config, "auto_trigger_hunt_score_threshold")
                        else 60.0,
                        version=current_config.version,
                        is_active=current_config.is_active,
                        description=current_config.description,
                        agent_prompts=current_config.agent_prompts,
                        agent_models=current_config.agent_models,
                        qa_enabled=current_config.qa_enabled,
                        sigma_fallback_enabled=current_config.sigma_fallback_enabled,
                        qa_max_retries=current_config.qa_max_retries,
                        rank_agent_enabled=current_config.rank_agent_enabled
                        if hasattr(current_config, "rank_agent_enabled")
                        else True,
                        created_at=current_config.created_at.isoformat(),
                        updated_at=current_config.updated_at.isoformat(),
                    )

            # Create new config version (only if changes were detected)
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=final_min_hunt_score,
                ranking_threshold=ranking_threshold,
                similarity_threshold=similarity_threshold,
                junk_filter_threshold=junk_filter_threshold,
                auto_trigger_hunt_score_threshold=auto_trigger_hunt_score_threshold,
                version=new_version,
                is_active=True,
                description=final_description,
                agent_prompts=final_agent_prompts,
                agent_models=merged_agent_models,
                qa_enabled=final_qa_enabled,
                sigma_fallback_enabled=sigma_fallback,
                qa_max_retries=qa_max_retries,
                rank_agent_enabled=final_rank_agent_enabled,
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
                auto_trigger_hunt_score_threshold=new_config.auto_trigger_hunt_score_threshold
                if hasattr(new_config, "auto_trigger_hunt_score_threshold")
                else 60.0,
                version=new_config.version,
                is_active=new_config.is_active,
                description=new_config.description,
                agent_prompts=new_config.agent_prompts,
                agent_models=new_config.agent_models,
                qa_enabled=new_config.qa_enabled,
                sigma_fallback_enabled=new_config.sigma_fallback_enabled,
                qa_max_retries=new_config.qa_max_retries,
                rank_agent_enabled=new_config.rank_agent_enabled if hasattr(new_config, "rank_agent_enabled") else True,
                created_at=new_config.created_at.isoformat(),
                updated_at=new_config.updated_at.isoformat(),
            )
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error updating workflow config: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/preset/save")
async def save_config_preset(save_request: SaveConfigPresetRequest):
    """Save or update a workflow config preset (upsert by name)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            existing = (
                db_session.query(WorkflowConfigPresetTable)
                .filter(WorkflowConfigPresetTable.name == save_request.name)
                .first()
            )
            if existing:
                existing.description = save_request.description
                existing.config_json = save_request.config
                db_session.commit()
                db_session.refresh(existing)
                return {
                    "success": True,
                    "id": existing.id,
                    "message": "Preset updated",
                    "created_at": existing.created_at.isoformat(),
                    "updated_at": existing.updated_at.isoformat(),
                }
            preset = WorkflowConfigPresetTable(
                name=save_request.name,
                description=save_request.description,
                config_json=save_request.config,
            )
            db_session.add(preset)
            db_session.commit()
            db_session.refresh(preset)
            return {
                "success": True,
                "id": preset.id,
                "message": "Preset saved",
                "created_at": preset.created_at.isoformat(),
                "updated_at": preset.updated_at.isoformat(),
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error saving config preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/preset/list")
async def list_config_presets(request: Request, scope: str | None = None):
    """List workflow config presets (id, name, description, scope, created_at, updated_at; no config_json).
    Optional scope filter: 'full', 'cmdline', 'proctree', 'huntqueries'. Presets without scope treated as full."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            presets = db_session.query(WorkflowConfigPresetTable).order_by(WorkflowConfigPresetTable.name.asc()).all()
            preset_list = []
            for p in presets:
                cfg = p.config_json or {}
                preset_scope = cfg.get("scope")
                if scope is not None:
                    if scope == "full" and preset_scope not in (None, "full"):
                        continue
                    if scope != "full" and preset_scope != scope:
                        continue
                preset_list.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "scope": preset_scope,
                        "created_at": p.created_at.isoformat(),
                        "updated_at": p.updated_at.isoformat(),
                    }
                )
            return {"success": True, "presets": preset_list}
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error listing config presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/preset/{preset_id}")
async def get_config_preset(request: Request, preset_id: int):
    """Get a workflow config preset by id; merge config_json into response for applyPreset."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            row = db_session.query(WorkflowConfigPresetTable).filter(WorkflowConfigPresetTable.id == preset_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Preset not found")
            out = {
                "success": True,
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            out.update(row.config_json or {})
            return out
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting config preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/config/preset/{preset_id}")
async def delete_config_preset(request: Request, preset_id: int):
    """Delete a workflow config preset by id."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            row = db_session.query(WorkflowConfigPresetTable).filter(WorkflowConfigPresetTable.id == preset_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Preset not found")
            db_session.delete(row)
            db_session.commit()
            return {"success": True, "message": "Preset deleted"}
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting config preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


def _config_row_to_preset_dict(config: AgenticWorkflowConfigTable) -> dict[str, Any]:
    """Build preset-shaped dict from agentic_workflow_config row for applyPreset()."""
    return {
        "version": "1.0",
        "thresholds": {
            "junk_filter_threshold": config.junk_filter_threshold,
            "ranking_threshold": config.ranking_threshold,
            "similarity_threshold": config.similarity_threshold,
        },
        "agent_models": config.agent_models if config.agent_models is not None else {},
        "qa_enabled": config.qa_enabled if config.qa_enabled is not None else {},
        "sigma_fallback_enabled": getattr(config, "sigma_fallback_enabled", False) or False,
        "rank_agent_enabled": getattr(config, "rank_agent_enabled", True)
        if getattr(config, "rank_agent_enabled", None) is not None
        else True,
        "qa_max_retries": getattr(config, "qa_max_retries", 5) or 5,
        "extract_agent_settings": {"disabled_agents": []},
        "agent_prompts": config.agent_prompts if config.agent_prompts is not None else {},
    }


@router.get("/config/versions")
async def list_config_versions(request: Request):
    """List workflow config versions (version, is_active, description, created_at, updated_at, id)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            rows = (
                db_session.query(AgenticWorkflowConfigTable).order_by(AgenticWorkflowConfigTable.version.desc()).all()
            )
            return {
                "success": True,
                "versions": [
                    {
                        "id": r.id,
                        "version": r.version,
                        "is_active": r.is_active,
                        "description": r.description or "",
                        "created_at": r.created_at.isoformat(),
                        "updated_at": r.updated_at.isoformat(),
                    }
                    for r in rows
                ],
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error listing config versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/version/{version_number}")
async def get_config_by_version(request: Request, version_number: int):
    """Get full workflow config by version number; returns preset-shaped payload for applyPreset."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.version == version_number)
                .first()
            )
            if not config:
                raise HTTPException(status_code=404, detail=f"No config with version {version_number}")
            return _config_row_to_preset_dict(config)
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting config by version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/prompts")
async def get_agent_prompts(request: Request):
    """Get agent prompts from active workflow configuration."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # Use with_for_update(skip_locked=True) to ensure we get the latest committed data
            # This prevents race conditions where a new config was just created but not yet visible
            # skip_locked=True allows the query to proceed even if another transaction has a lock
            config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .with_for_update(skip_locked=True)
                .first()
            )

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
            rank_model = (
                agent_models.get("RankAgent") or rank_model_env or "[Not configured - requires LMSTUDIO_MODEL_RANK]"
            )
            extract_model = agent_models.get("ExtractAgent") or extract_model_env or default_model
            sigma_model = agent_models.get("SigmaAgent") or sigma_model_env or default_model

            # IMPORTANT: Only return prompts from database (what workflow actually uses)
            # The workflow has NO file fallback - it requires prompts to be in the database
            # Showing file-based prompts in UI would be misleading

            prompts_dict = {}

            # Sub-agents list for model assignment
            sub_agents = [
                "CmdlineExtract",
                "CmdLineQA",
                "ProcTreeExtract",
                "ProcTreeQA",
                "HuntQueriesExtract",
                "HuntQueriesQA",
            ]

            # Deleted subagents that should be filtered out
            deleted_agents = {"SigExtract", "RegExtract", "EventCodeExtract", "SigQA", "RegQA", "EventCodeQA"}

            # Only use database prompts (what workflow actually uses)
            if config.agent_prompts:
                for agent_name, prompt_data in config.agent_prompts.items():
                    # Skip deleted agents
                    if agent_name in deleted_agents:
                        continue

                    # Preserve ExtractAgentSettings (contains disabled_agents list)
                    if agent_name == "ExtractAgentSettings":
                        prompts_dict[agent_name] = prompt_data
                        continue

                    # Add model info if not in database prompt data
                    if "model" not in prompt_data:
                        if agent_name == "ExtractAgent":
                            prompt_data["model"] = extract_model
                        elif agent_name == "RankAgent":
                            prompt_data["model"] = rank_model
                        elif agent_name == "SigmaAgent":
                            prompt_data["model"] = sigma_model
                        elif agent_name in sub_agents:
                            prompt_data["model"] = extract_model
                        else:
                            prompt_data["model"] = default_model
                    prompts_dict[agent_name] = prompt_data

            return {"prompts": prompts_dict}
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/prompts/{agent_name}")
async def get_agent_prompt(request: Request, agent_name: str):
    """Get prompt for a specific agent from active workflow configuration."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .first()
            )

            if not config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")

            if not config.agent_prompts or agent_name not in config.agent_prompts:
                raise HTTPException(status_code=404, detail=f"Prompt not found for agent {agent_name}")

            prompt_data = config.agent_prompts[agent_name]

            # Also get from AgentPromptVersionTable if available for metadata
            prompt_version = (
                db_session.query(AgentPromptVersionTable)
                .filter(
                    AgentPromptVersionTable.agent_name == agent_name,
                    AgentPromptVersionTable.workflow_config_version == config.version,
                )
                .order_by(AgentPromptVersionTable.version.desc())
                .first()
            )

            result = {
                "agent_name": agent_name,
                "workflow_config_version": config.version,
                "prompt": prompt_data.get("prompt", ""),
                "instructions": prompt_data.get("instructions", ""),
            }

            if prompt_version:
                result["prompt_version"] = prompt_version.version
                result["created_at"] = prompt_version.created_at.isoformat() if prompt_version.created_at else None
                result["change_description"] = prompt_version.change_description

            return result
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/config/prompts")
async def update_agent_prompts(request: Request, prompt_update: AgentPromptUpdate):
    """Update agent prompt in active workflow configuration."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # CRITICAL: Use order_by to ensure we get the latest active config
            # This prevents race conditions where another operation creates a new config
            # between when we query and when we update
            current_config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .with_for_update()
                .first()
            )  # Lock the row to prevent concurrent updates

            if not current_config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")

            # Get existing prompts or create new dict
            agent_prompts = current_config.agent_prompts.copy() if current_config.agent_prompts else {}

            # Get current prompt values for version history
            old_prompt = agent_prompts.get(prompt_update.agent_name, {}).get("prompt", "")
            old_instructions = agent_prompts.get(prompt_update.agent_name, {}).get("instructions", "")

            # Deactivate current config
            current_config.is_active = False
            db_session.flush()  # Ensure old config is deactivated before creating new one
            new_version = current_config.version + 1

            # Update or create agent prompt
            if prompt_update.agent_name not in agent_prompts:
                agent_prompts[prompt_update.agent_name] = {}

            # Validate JSON format for extraction agents
            if prompt_update.prompt is not None:
                extraction_agents = [
                    "CmdlineExtract",
                    "ProcTreeExtract",
                    "HuntQueriesExtract",
                    "CmdLineQA",
                    "ProcTreeQA",
                    "HuntQueriesQA",
                ]
                if prompt_update.agent_name in extraction_agents:
                    try:
                        json.loads(prompt_update.prompt)
                    except json.JSONDecodeError as e:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid JSON format for {prompt_update.agent_name} prompt in workflow config. Please fix the prompt in the UI. Error: {e}",
                        ) from e
                agent_prompts[prompt_update.agent_name]["prompt"] = prompt_update.prompt
            if prompt_update.instructions is not None:
                agent_prompts[prompt_update.agent_name]["instructions"] = prompt_update.instructions

            # Create new config version - preserve all fields including agent_models and qa_enabled
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=current_config.min_hunt_score,
                ranking_threshold=current_config.ranking_threshold,
                similarity_threshold=current_config.similarity_threshold,
                junk_filter_threshold=current_config.junk_filter_threshold,
                auto_trigger_hunt_score_threshold=current_config.auto_trigger_hunt_score_threshold
                if hasattr(current_config, "auto_trigger_hunt_score_threshold")
                else 60.0,
                version=new_version,
                is_active=True,
                description=current_config.description or "Updated configuration",
                agent_prompts=agent_prompts,
                agent_models=current_config.agent_models.copy() if current_config.agent_models else {},
                qa_enabled=current_config.qa_enabled.copy() if current_config.qa_enabled else {},
                sigma_fallback_enabled=current_config.sigma_fallback_enabled
                if hasattr(current_config, "sigma_fallback_enabled")
                else False,
                rank_agent_enabled=current_config.rank_agent_enabled
                if hasattr(current_config, "rank_agent_enabled")
                else True,
                qa_max_retries=current_config.qa_max_retries if hasattr(current_config, "qa_max_retries") else 5,
            )

            db_session.add(new_config)
            db_session.flush()  # Flush to get new_config.id

            # Save version history
            # Get the highest version number for this agent
            max_version = (
                db_session.query(func.max(AgentPromptVersionTable.version))
                .filter(AgentPromptVersionTable.agent_name == prompt_update.agent_name)
                .scalar()
                or 0
            )

            # Always save version history for all agents (same behavior as CmdlineExtract)
            # Use the new prompt/instructions if provided, otherwise use the old ones
            version_prompt = prompt_update.prompt if prompt_update.prompt is not None else old_prompt
            version_instructions = (
                prompt_update.instructions if prompt_update.instructions is not None else old_instructions
            )

            prompt_version = AgentPromptVersionTable(
                agent_name=prompt_update.agent_name,
                prompt=version_prompt,
                instructions=version_instructions,
                version=max_version + 1,
                workflow_config_version=new_version,
                change_description=prompt_update.change_description,
            )

            db_session.add(prompt_version)
            db_session.commit()

            logger.debug(
                f"Saved prompt version history for {prompt_update.agent_name}: version={max_version + 1}, workflow_config_version={new_version}"
            )
            db_session.refresh(new_config)

            logger.info(f"Updated agent prompt for {prompt_update.agent_name} in config version {new_version}")

            return {
                "success": True,
                "message": f"Agent prompt updated for {prompt_update.agent_name}",
                "version": new_version,
                "prompt": version_prompt,
                "instructions": version_instructions or "",
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/prompts/{agent_name}/versions")
async def get_agent_prompt_versions(request: Request, agent_name: str):
    """Get version history for an agent prompt."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            versions = (
                db_session.query(AgentPromptVersionTable)
                .filter(AgentPromptVersionTable.agent_name == agent_name)
                .order_by(AgentPromptVersionTable.version.desc())
                .all()
            )

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
                        "created_at": v.created_at.isoformat(),
                    }
                    for v in versions
                ],
            }
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Error getting prompt versions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/prompts/{agent_name}/by-config-version/{config_version}")
async def get_prompt_by_config_version(request: Request, agent_name: str, config_version: int):
    """Get prompt for a specific agent and workflow config version."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # First try agent_prompt_versions table
            prompt_version = (
                db_session.query(AgentPromptVersionTable)
                .filter(
                    AgentPromptVersionTable.agent_name == agent_name,
                    AgentPromptVersionTable.workflow_config_version == config_version,
                )
                .order_by(AgentPromptVersionTable.version.desc())
                .first()
            )

            if prompt_version:
                return {
                    "agent_name": agent_name,
                    "workflow_config_version": config_version,
                    "source": "agent_prompt_versions",
                    "prompt": prompt_version.prompt,
                    "instructions": prompt_version.instructions,
                    "prompt_version": prompt_version.version,
                    "created_at": prompt_version.created_at.isoformat() if prompt_version.created_at else None,
                    "change_description": prompt_version.change_description,
                }

            # Fall back to workflow config's agent_prompts JSONB
            config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.version == config_version)
                .first()
            )

            if config and config.agent_prompts and agent_name in config.agent_prompts:
                prompt_data = config.agent_prompts[agent_name]
                return {
                    "agent_name": agent_name,
                    "workflow_config_version": config_version,
                    "source": "agentic_workflow_config.agent_prompts",
                    "prompt": prompt_data.get("prompt", ""),
                    "instructions": prompt_data.get("instructions", ""),
                }

            # If not found, find most recent version before this one
            prev_version = (
                db_session.query(AgentPromptVersionTable)
                .filter(
                    AgentPromptVersionTable.agent_name == agent_name,
                    AgentPromptVersionTable.workflow_config_version < config_version,
                )
                .order_by(AgentPromptVersionTable.workflow_config_version.desc())
                .first()
            )

            if prev_version:
                return {
                    "agent_name": agent_name,
                    "workflow_config_version": config_version,
                    "source": f"agent_prompt_versions (inherited from v{prev_version.workflow_config_version})",
                    "prompt": prev_version.prompt,
                    "instructions": prev_version.instructions,
                    "prompt_version": prev_version.version,
                    "inherited_from": prev_version.workflow_config_version,
                    "note": f"Config v{config_version} inherits from v{prev_version.workflow_config_version}",
                }

            raise HTTPException(
                status_code=404, detail=f"Prompt not found for {agent_name} at config version {config_version}"
            )
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prompt by config version: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/prompts/{agent_name}/rollback")
async def rollback_agent_prompt(request: Request, agent_name: str, rollback_request: RollbackRequest):
    """Rollback an agent prompt to a previous version."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # Get the version to rollback to
            target_version = (
                db_session.query(AgentPromptVersionTable)
                .filter(
                    AgentPromptVersionTable.id == rollback_request.version_id,
                    AgentPromptVersionTable.agent_name == agent_name,
                )
                .first()
            )

            if not target_version:
                raise HTTPException(status_code=404, detail="Version not found")

            # Get current active config
            # CRITICAL: Use order_by and lock to prevent race conditions
            current_config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .with_for_update()
                .first()
            )  # Lock the row to prevent concurrent updates

            if not current_config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")

            # Deactivate current config
            current_config.is_active = False
            db_session.flush()  # Ensure old config is deactivated before creating new one
            new_version = current_config.version + 1

            # Get existing prompts
            agent_prompts = current_config.agent_prompts.copy() if current_config.agent_prompts else {}

            # Restore prompt from target version
            agent_prompts[agent_name] = {"prompt": target_version.prompt, "instructions": target_version.instructions}

            # Create new config version
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=current_config.min_hunt_score,
                ranking_threshold=current_config.ranking_threshold,
                similarity_threshold=current_config.similarity_threshold,
                junk_filter_threshold=current_config.junk_filter_threshold,
                auto_trigger_hunt_score_threshold=current_config.auto_trigger_hunt_score_threshold
                if hasattr(current_config, "auto_trigger_hunt_score_threshold")
                else 60.0,
                version=new_version,
                is_active=True,
                description=current_config.description or "Rolled back configuration",
                agent_prompts=agent_prompts,
                agent_models=current_config.agent_models.copy() if current_config.agent_models else {},
                qa_enabled=current_config.qa_enabled.copy() if current_config.qa_enabled else {},
                sigma_fallback_enabled=current_config.sigma_fallback_enabled
                if hasattr(current_config, "sigma_fallback_enabled")
                else False,
                rank_agent_enabled=current_config.rank_agent_enabled
                if hasattr(current_config, "rank_agent_enabled")
                else True,
                qa_max_retries=current_config.qa_max_retries if hasattr(current_config, "qa_max_retries") else 5,
            )

            db_session.add(new_config)
            db_session.flush()

            # Create new version entry for rollback
            max_version = (
                db_session.query(func.max(AgentPromptVersionTable.version))
                .filter(AgentPromptVersionTable.agent_name == agent_name)
                .scalar()
                or 0
            )

            prompt_version = AgentPromptVersionTable(
                agent_name=agent_name,
                prompt=target_version.prompt,
                instructions=target_version.instructions,
                version=max_version + 1,
                workflow_config_version=new_version,
                change_description=f"Rolled back to version {target_version.version}",
            )

            db_session.add(prompt_version)
            db_session.commit()
            db_session.refresh(new_config)

            logger.info(f"Rolled back agent prompt for {agent_name} to version {target_version.version}")

            # Return rolled-back prompt so frontend can update UI immediately (avoids race/cache)
            return {
                "success": True,
                "message": f"Rolled back {agent_name} to version {target_version.version}",
                "version": new_version,
                "prompt": target_version.prompt,
                "instructions": target_version.instructions or "",
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back agent prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


class TestSubAgentRequest(BaseModel):
    """Request model for testing a sub-agent."""

    article_id: int = Field(2155, description="Article ID to test with")
    agent_name: str = Field(..., description="Name of the sub-agent (e.g., CmdlineExtract, ProcTreeExtract)")
    use_junk_filter: bool = Field(True, description="Whether to apply content filtering")
    junk_filter_threshold: float = Field(0.8, description="Content filter confidence threshold")


class TestRankAgentRequest(BaseModel):
    """Request model for testing Rank Agent."""

    article_id: int = Field(2155, description="Article ID to test with")
    use_junk_filter: bool = Field(True, description="Whether to apply content filtering")
    junk_filter_threshold: float = Field(0.8, description="Content filter confidence threshold")


class TestSigmaAgentRequest(BaseModel):
    """Request model for testing SIGMA generation agent."""

    article_id: int = Field(2155, description="Article ID to test with")
    use_junk_filter: bool = Field(True, description="Whether to apply content filtering")
    junk_filter_threshold: float = Field(0.8, description="Content filter confidence threshold")
    max_attempts: int = Field(3, ge=1, le=10, description="Maximum SIGMA generation attempts")


@router.post("/config/test-subagent")
async def test_sub_agent(request: Request, test_request: TestSubAgentRequest):
    """Test a sub-agent extraction on a specific article (dispatches to worker)."""
    try:
        from src.worker.tasks.test_agents import test_sub_agent_task

        # Dispatch task to worker
        task = test_sub_agent_task.delay(
            agent_name=test_request.agent_name,
            article_id=test_request.article_id,
            use_junk_filter=test_request.use_junk_filter,
            junk_filter_threshold=test_request.junk_filter_threshold,
        )

        return {
            "success": True,
            "task_id": task.id,
            "status": "pending",
            "message": "Test task dispatched to worker. Use /api/workflow/config/test-status/{task_id} to check status.",
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        error_type = type(e).__name__

        # Check for chained exceptions - prioritize the original error over generator cleanup errors
        original_error = e
        if hasattr(e, "__cause__") and e.__cause__:
            original_error = e.__cause__
        elif hasattr(e, "__context__") and e.__context__:
            original_error = e.__context__

        original_error_msg = str(original_error).lower()

        # If the original error is NOT a generator error, use that instead
        if "generator" not in original_error_msg and "generator" in error_msg:
            # Generator error is masking a real error - use the original error
            error_msg = original_error_msg
            error_type = type(original_error).__name__
            e = original_error

        # Check if error is related to LMStudio being busy/unavailable
        # Only flag as "busy" for genuine connection failures or timeouts, not connection attempts in progress
        # Don't flag generator errors as busy if they're masking a real error (like 400)
        is_generator_error_only = (
            "generator didn't stop after throw" in error_msg
            and "400" not in error_msg
            and "context length" not in error_msg
            and "invalid request" not in error_msg
        )

        is_lmstudio_busy = (
            # Generator errors (Langfuse cleanup issues) - but only if not masking a real error
            is_generator_error_only
            or
            # Actual connection failures (refused, not reachable)
            (
                "cannot connect" in error_msg
                and ("refused" in error_msg or "not reachable" in error_msg or "name resolution" in error_msg)
            )
            or
            # Timeout errors (but not if it's a connection timeout during initial setup)
            ("timeout" in error_msg and ("request timeout" in error_msg or "read timeout" in error_msg))
            or
            # Overloaded errors
            "overloaded" in error_msg
            or
            # HTTP 503/429 (service unavailable/too many requests)
            ("503" in error_msg or "429" in error_msg)
            or
            # Connection errors that are actual failures (not in-progress)
            (error_type == "ConnectError" and "refused" in error_msg)
        )

        if is_lmstudio_busy:
            logger.warning(f"Error testing sub-agent (LMStudio may be busy): {e}")
            raise HTTPException(
                status_code=503,
                detail=(
                    "LMStudio appears to be busy or unavailable. "
                    "The model may be processing another request. "
                    "Would you like to wait and try again, or retry later?"
                ),
            ) from e
        logger.error(f"Error testing sub-agent: {e}", exc_info=True)
        # Format error message for better user experience
        error_detail = str(e)

        # Extract key information from common error patterns
        if "context length" in error_detail.lower():
            # Extract the key message from JSON error if present
            import re

            json_match = re.search(r'"error":"([^"]+)"', error_detail)
            if json_match:
                core_message = json_match.group(1)
                error_detail = f"Context length error: {core_message}"
            else:
                # Fallback: extract the key part
                if "greater than the context length" in error_detail:
                    error_detail = "The prompt is too long for the model's context window. Please increase the context length in LMStudio or use a shorter prompt."

        raise HTTPException(status_code=500, detail=error_detail) from e


@router.post("/config/prompts/bootstrap")
async def bootstrap_prompts_from_files(request: Request):
    """Bootstrap agent prompts from flat files into database (one-time initialization)."""
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            # CRITICAL: Use order_by and lock to prevent race conditions
            current_config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .with_for_update()
                .first()
            )  # Lock the row to prevent concurrent updates

            if not current_config:
                raise HTTPException(status_code=404, detail="No active workflow configuration found")

            # Load prompts from files
            import os
            from pathlib import Path

            prompts_dir = Path(__file__).parent.parent.parent / "prompts"

            default_model = os.getenv("LMSTUDIO_MODEL", "mistralai/mistral-7b-instruct-v0.3")
            rank_model_env = os.getenv("LMSTUDIO_MODEL_RANK", "").strip()
            extract_model_env = os.getenv("LMSTUDIO_MODEL_EXTRACT", "").strip()
            sigma_model_env = os.getenv("LMSTUDIO_MODEL_SIGMA", "").strip()

            agent_models = current_config.agent_models if current_config.agent_models is not None else {}
            rank_model = (
                agent_models.get("RankAgent") or rank_model_env or "[Not configured - requires LMSTUDIO_MODEL_RANK]"
            )
            extract_model = agent_models.get("ExtractAgent") or extract_model_env or default_model
            sigma_model = agent_models.get("SigmaAgent") or sigma_model_env or default_model

            loaded_prompts = {}

            # RankAgent
            rank_prompt_path = prompts_dir / "lmstudio_sigma_ranking.txt"
            if rank_prompt_path.exists():
                with open(rank_prompt_path) as f:
                    loaded_prompts["RankAgent"] = {"prompt": f.read(), "instructions": ""}

            # SigmaAgent
            sigma_prompt_path = prompts_dir / "sigma_generation.txt"
            if sigma_prompt_path.exists():
                with open(sigma_prompt_path) as f:
                    loaded_prompts["SigmaAgent"] = {"prompt": f.read(), "instructions": ""}

            # QAAgent
            qa_agent_path = prompts_dir / "QAAgentCMD"
            if qa_agent_path.exists():
                with open(qa_agent_path) as f:
                    loaded_prompts["QAAgent"] = {"prompt": f.read(), "instructions": ""}

            # Sub-Agents
            sub_agents = [
                ("CmdlineExtract", "CmdLineQA"),
                ("ProcTreeExtract", "ProcTreeQA"),
                ("HuntQueriesExtract", "HuntQueriesQA"),
            ]

            for agent_name, qa_name in sub_agents:
                # Load Extraction Agent
                agent_path = prompts_dir / agent_name
                if agent_path.exists():
                    with open(agent_path) as f:
                        loaded_prompts[agent_name] = {"prompt": f.read(), "instructions": ""}

                # Load QA Agent
                qa_path = prompts_dir / qa_name
                if qa_path.exists():
                    with open(qa_path) as f:
                        loaded_prompts[qa_name] = {"prompt": f.read(), "instructions": ""}

            if not loaded_prompts:
                raise HTTPException(status_code=404, detail="No prompt files found to bootstrap from")

            # Deactivate current config
            current_config.is_active = False
            db_session.flush()
            new_version = current_config.version + 1

            # Create new config with bootstrapped prompts
            new_config = AgenticWorkflowConfigTable(
                min_hunt_score=current_config.min_hunt_score,
                ranking_threshold=current_config.ranking_threshold,
                similarity_threshold=current_config.similarity_threshold,
                junk_filter_threshold=current_config.junk_filter_threshold,
                auto_trigger_hunt_score_threshold=current_config.auto_trigger_hunt_score_threshold
                if hasattr(current_config, "auto_trigger_hunt_score_threshold")
                else 60.0,
                version=new_version,
                is_active=True,
                description="Bootstrapped prompts from files",
                agent_prompts=loaded_prompts,
                agent_models=current_config.agent_models.copy() if current_config.agent_models else {},
                qa_enabled=current_config.qa_enabled.copy() if current_config.qa_enabled else {},
                sigma_fallback_enabled=current_config.sigma_fallback_enabled
                if hasattr(current_config, "sigma_fallback_enabled")
                else False,
                rank_agent_enabled=current_config.rank_agent_enabled
                if hasattr(current_config, "rank_agent_enabled")
                else True,
                qa_max_retries=current_config.qa_max_retries if hasattr(current_config, "qa_max_retries") else 5,
            )

            db_session.add(new_config)
            db_session.commit()
            db_session.refresh(new_config)

            logger.info(f"Bootstrapped {len(loaded_prompts)} prompts from files into config version {new_version}")

            return {
                "success": True,
                "message": f"Successfully bootstrapped {len(loaded_prompts)} agent prompts from files",
                "version": new_version,
                "prompts_loaded": list(loaded_prompts.keys()),
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bootstrapping prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/config/test-status/{task_id}")
async def get_test_status(request: Request, task_id: str):
    """Get the status and result of a test task."""
    try:
        from celery.result import AsyncResult

        from src.worker.celery_app import celery_app

        task_result = AsyncResult(task_id, app=celery_app)

        if task_result.ready():
            if task_result.successful():
                result = task_result.result
                return {"success": True, "task_id": task_id, "status": "completed", "result": result}
            # Task failed
            error = str(task_result.result) if task_result.result else "Unknown error"
            return {"success": False, "task_id": task_id, "status": "failed", "error": error}
        # Task still running
        return {"success": True, "task_id": task_id, "status": "pending", "message": "Test is still running in worker"}
    except Exception as e:
        logger.error(f"Error checking test status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/test-sigmaagent")
async def test_sigma_agent(request: Request, test_request: TestSigmaAgentRequest):
    """Test SIGMA generation agent on a specific article (dispatches to worker)."""
    try:
        from src.worker.tasks.test_agents import test_sigma_agent_task

        # Dispatch task to worker
        task = test_sigma_agent_task.delay(
            article_id=test_request.article_id,
            use_junk_filter=test_request.use_junk_filter,
            junk_filter_threshold=test_request.junk_filter_threshold,
            max_attempts=test_request.max_attempts,
        )

        return {
            "success": True,
            "task_id": task.id,
            "status": "pending",
            "message": "Test task dispatched to worker. Use /api/workflow/config/test-status/{task_id} to check status.",
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        is_lmstudio_busy = (
            "busy" in error_msg
            or "unavailable" in error_msg
            or "overloaded" in error_msg
            or "503" in error_msg
            or "429" in error_msg
            or ("timeout" in error_msg and "read" in error_msg)
        )

        if is_lmstudio_busy:
            logger.warning(f"Error testing SIGMA agent (LMStudio may be busy): {e}")
            raise HTTPException(
                status_code=503,
                detail=(
                    "LMStudio appears to be busy or unavailable. "
                    "The model may be processing another request. "
                    "Would you like to wait and try again, or retry later?"
                ),
            ) from e

        logger.error(f"Error testing SIGMA agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/config/test-rankagent")
async def test_rank_agent(request: Request, test_request: TestRankAgentRequest):
    """Test Rank Agent on a specific article (dispatches to worker)."""
    try:
        from src.worker.tasks.test_agents import test_rank_agent_task

        # Dispatch task to worker
        task = test_rank_agent_task.delay(
            article_id=test_request.article_id,
            use_junk_filter=test_request.use_junk_filter,
            junk_filter_threshold=test_request.junk_filter_threshold,
        )

        return {
            "success": True,
            "task_id": task.id,
            "status": "pending",
            "message": "Test task dispatched to worker. Use /api/workflow/config/test-status/{task_id} to check status.",
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        error_type = type(e).__name__

        # Check for chained exceptions - prioritize the original error over generator cleanup errors
        original_error = e
        if hasattr(e, "__cause__") and e.__cause__:
            original_error = e.__cause__
        elif hasattr(e, "__context__") and e.__context__:
            original_error = e.__context__

        original_error_msg = str(original_error).lower()

        # If the original error is NOT a generator error, use that instead
        if "generator" not in original_error_msg and "generator" in error_msg:
            # Generator error is masking a real error - use the original error
            error_msg = original_error_msg
            error_type = type(original_error).__name__
            e = original_error

        # Check if error is related to LMStudio being busy/unavailable
        # Only flag as "busy" for genuine connection failures or timeouts, not connection attempts in progress
        # Don't flag generator errors as busy if they're masking a real error (like 400)
        is_generator_error_only = (
            "generator didn't stop after throw" in error_msg
            and "400" not in error_msg
            and "context length" not in error_msg
            and "invalid request" not in error_msg
        )

        is_lmstudio_busy = (
            # Generator errors (Langfuse cleanup issues) - but only if not masking a real error
            is_generator_error_only
            or
            # Actual connection failures (refused, not reachable)
            (
                "cannot connect" in error_msg
                and ("refused" in error_msg or "not reachable" in error_msg or "name resolution" in error_msg)
            )
            or
            # Timeout errors (but not if it's a connection timeout during initial setup)
            ("timeout" in error_msg and ("request timeout" in error_msg or "read timeout" in error_msg))
            or
            # Overloaded errors
            "overloaded" in error_msg
            or
            # HTTP 503/429 (service unavailable/too many requests)
            ("503" in error_msg or "429" in error_msg)
            or
            # Connection errors that are actual failures (not in-progress)
            (error_type == "ConnectError" and "refused" in error_msg)
        )

        if is_lmstudio_busy:
            logger.warning(f"Error testing Rank Agent (LMStudio may be busy): {e}")
            raise HTTPException(
                status_code=503,
                detail=(
                    "LMStudio appears to be busy or unavailable. "
                    "The model may be processing another request. "
                    "Would you like to wait and try again, or retry later?"
                ),
            ) from e
        logger.error(f"Error testing Rank Agent: {e}", exc_info=True)
        # Format error message for better user experience
        error_detail = str(e)

        # Extract key information from common error patterns
        if "context length" in error_detail.lower():
            # Extract the key message from JSON error if present
            import re

            json_match = re.search(r'"error":"([^"]+)"', error_detail)
            if json_match:
                core_message = json_match.group(1)
                error_detail = f"Context length error: {core_message}"
            else:
                # Fallback: extract the key part
                if "greater than the context length" in error_detail:
                    error_detail = "The prompt is too long for the model's context window. Please increase the context length in LMStudio or use a shorter prompt."

        raise HTTPException(status_code=500, detail=error_detail) from e
