#!/usr/bin/env python3
"""Get full HuntQueriesExtract prompts for versions 1643 and 1729."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable

def get_prompt_for_version(agent_name: str, config_version: int, db_session):
    """Get prompt for a specific agent and config version."""
    # First try agent_prompt_versions table
    prompt_version = db_session.query(AgentPromptVersionTable).filter(
        AgentPromptVersionTable.agent_name == agent_name,
        AgentPromptVersionTable.workflow_config_version == config_version
    ).order_by(AgentPromptVersionTable.version.desc()).first()
    
    if prompt_version:
        return {
            "source": "agent_prompt_versions",
            "prompt": prompt_version.prompt,
            "instructions": prompt_version.instructions,
        }
    
    # Fall back to workflow config's agent_prompts JSONB
    config = db_session.query(AgenticWorkflowConfigTable).filter(
        AgenticWorkflowConfigTable.version == config_version
    ).first()
    
    if config and config.agent_prompts and agent_name in config.agent_prompts:
        prompt_data = config.agent_prompts[agent_name]
        return {
            "source": "agentic_workflow_config.agent_prompts",
            "prompt": prompt_data.get("prompt", ""),
            "instructions": prompt_data.get("instructions", ""),
        }
    
    return None

def main():
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        print("=" * 80)
        print("HUNTQUERIESEXTRACT PROMPTS: v1643 vs v1729")
        print("=" * 80)
        
        prompt_1643 = get_prompt_for_version("HuntQueriesExtract", 1643, db_session)
        prompt_1729 = get_prompt_for_version("HuntQueriesExtract", 1729, db_session)
        
        if prompt_1643:
            print("\n" + "=" * 80)
            print("VERSION 1643 PROMPT:")
            print("=" * 80)
            print(prompt_1643['prompt'])
        
        if prompt_1729:
            print("\n" + "=" * 80)
            print("VERSION 1729 PROMPT:")
            print("=" * 80)
            print(prompt_1729['prompt'])
        
    finally:
        db_session.close()

if __name__ == "__main__":
    main()
