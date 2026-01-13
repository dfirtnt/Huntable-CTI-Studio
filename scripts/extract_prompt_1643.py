#!/usr/bin/env python3
"""Extract HuntQueriesExtract prompt for version 1643."""

import sys
import os
import json
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
        return prompt_version.prompt
    
    # Fall back to workflow config's agent_prompts JSONB
    config = db_session.query(AgenticWorkflowConfigTable).filter(
        AgenticWorkflowConfigTable.version == config_version
    ).first()
    
    if config and config.agent_prompts and agent_name in config.agent_prompts:
        prompt_data = config.agent_prompts[agent_name]
        return prompt_data.get("prompt", "")
    
    return None

def main():
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        prompt = get_prompt_for_version("HuntQueriesExtract", 1643, db_session)
        
        if prompt:
            # Try to parse as JSON if it's stored as JSON string
            try:
                parsed = json.loads(prompt)
                if isinstance(parsed, dict) and "role" in parsed:
                    # Extract the role field which contains the actual prompt
                    print(parsed["role"])
                else:
                    print(prompt)
            except (json.JSONDecodeError, TypeError):
                # Not JSON, print as-is
                print(prompt)
        else:
            print("❌ Prompt not found for HuntQueriesExtract v1643", file=sys.stderr)
            sys.exit(1)
        
    finally:
        db_session.close()

if __name__ == "__main__":
    main()
