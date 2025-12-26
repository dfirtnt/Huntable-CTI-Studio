"""
Service for creating immutable preset snapshots for evaluation.

Snapshots include full prompt text resolved from the database,
ensuring reproducibility of evaluation runs.
"""

import json
import hashlib
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Session

from src.database.models import (
    AgenticWorkflowConfigTable,
    AgentPromptVersionTable,
    EvalPresetSnapshotTable
)

logger = logging.getLogger(__name__)


class EvalPresetSnapshotService:
    """Service for creating and managing eval preset snapshots."""
    
    def __init__(self, db_session: Session):
        """Initialize with database session."""
        self.db = db_session
    
    def create_snapshot(self, preset_id: Optional[int] = None, description: Optional[str] = None) -> UUID:
        """
        Create an immutable preset snapshot with resolved prompts.
        
        Args:
            preset_id: Optional preset ID (defaults to active preset)
            description: Optional description for the snapshot
        
        Returns:
            UUID of the created snapshot
        """
        # Load preset config
        if preset_id:
            config = self.db.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.id == preset_id
            ).first()
        else:
            # Get active config
            config = self.db.query(AgenticWorkflowConfigTable).filter(
                AgenticWorkflowConfigTable.is_active == True
            ).order_by(
                AgenticWorkflowConfigTable.version.desc()
            ).first()
        
        if not config:
            raise ValueError(f"Preset {preset_id} not found" if preset_id else "No active preset found")
        
        # Build snapshot data
        snapshot_data = {
            "preset_id": config.id,
            "preset_version": config.version,
            "thresholds": {
                "min_hunt_score": config.min_hunt_score,
                "ranking_threshold": config.ranking_threshold,
                "similarity_threshold": config.similarity_threshold,
                "junk_filter_threshold": config.junk_filter_threshold,
            },
            "agent_models": config.agent_models or {},
            "qa_enabled": config.qa_enabled or {},
            "sigma_fallback_enabled": config.sigma_fallback_enabled,
            "rank_agent_enabled": config.rank_agent_enabled,
            "qa_max_retries": config.qa_max_retries,
            "extractor_version": "v1",
            "evaluation_scope": "cmdline_only",  # Explicit scope prevents accidental reuse
            "snapshot_timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Resolve prompts from database
        agent_prompts = {}
        if config.agent_prompts:
            logger.info(f"Loading prompts from config.agent_prompts. Available agents: {list(config.agent_prompts.keys())}")
            for agent_name, prompt_data in config.agent_prompts.items():
                # If prompt_data is a dict with prompt text, use it directly
                if isinstance(prompt_data, dict) and "prompt" in prompt_data:
                    agent_prompts[agent_name] = {
                        "prompt": prompt_data["prompt"],
                        "instructions": prompt_data.get("instructions", ""),
                        "model": prompt_data.get("model", snapshot_data["agent_models"].get(agent_name, ""))
                    }
                else:
                    # Try to resolve from AgentPromptVersionTable
                    prompt_version = self.db.query(AgentPromptVersionTable).filter(
                        AgentPromptVersionTable.agent_name == agent_name,
                        AgentPromptVersionTable.workflow_config_version == config.version
                    ).order_by(
                        AgentPromptVersionTable.version.desc()
                    ).first()
                    
                    if prompt_version:
                        agent_prompts[agent_name] = {
                            "prompt": prompt_version.prompt,
                            "instructions": prompt_version.instructions or "",
                            "model": snapshot_data["agent_models"].get(agent_name, "")
                        }
                    else:
                        logger.warning(f"Could not resolve prompt for {agent_name}, using empty prompt")
                        agent_prompts[agent_name] = {
                            "prompt": "",
                            "instructions": "",
                            "model": snapshot_data["agent_models"].get(agent_name, "")
                        }
        
        snapshot_data["agent_prompts"] = agent_prompts
        
        # Canonicalize JSON (sorted keys) for consistent hashing
        canonical_json = json.dumps(snapshot_data, sort_keys=True, ensure_ascii=False)
        
        # Compute SHA-256 hash
        snapshot_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
        
        # Check if snapshot with same hash already exists
        existing = self.db.query(EvalPresetSnapshotTable).filter(
            EvalPresetSnapshotTable.snapshot_hash == snapshot_hash
        ).first()
        
        if existing:
            logger.info(f"Snapshot with hash {snapshot_hash[:16]}... already exists (id: {existing.id})")
            return existing.id
        
        # Create snapshot record
        snapshot = EvalPresetSnapshotTable(
            original_preset_id=config.id,
            original_preset_version=config.version,
            snapshot_data=snapshot_data,
            snapshot_hash=snapshot_hash,
            description=description or f"Snapshot of preset {config.id} (v{config.version})"
        )
        
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        
        logger.info(f"Created eval preset snapshot {snapshot.id} for preset {config.id} (v{config.version})")
        return snapshot.id
    
    def get_snapshot(self, snapshot_id: UUID) -> Optional[EvalPresetSnapshotTable]:
        """Get snapshot by UUID."""
        return self.db.query(EvalPresetSnapshotTable).filter(
            EvalPresetSnapshotTable.id == snapshot_id
        ).first()

