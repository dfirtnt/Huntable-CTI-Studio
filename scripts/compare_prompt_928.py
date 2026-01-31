#!/usr/bin/env python3
"""Compare prompt for version 928 with current prompt."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable


def get_prompt_for_version(agent_name: str, config_version: int, db_session):
    """Get prompt for a specific agent and config version."""
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
            "source": "agent_prompt_versions",
            "prompt": prompt_version.prompt,
            "instructions": prompt_version.instructions,
            "version": prompt_version.version,
            "workflow_config_version": prompt_version.workflow_config_version,
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
            "source": "agentic_workflow_config.agent_prompts",
            "workflow_config_version": config_version,
            "prompt": prompt_data.get("prompt", ""),
            "instructions": prompt_data.get("instructions", ""),
        }

    return None


def main():
    agent_name = "CmdlineExtract"
    target_version = 928

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        # Get prompt for version 928
        prompt_v928 = get_prompt_for_version(agent_name, target_version, db_session)

        # Get current active config
        current_config = (
            db_session.query(AgenticWorkflowConfigTable)
            .filter(AgenticWorkflowConfigTable.is_active == True)
            .order_by(AgenticWorkflowConfigTable.version.desc())
            .first()
        )

        current_prompt_data = None
        if current_config:
            current_version = current_config.version
            current_prompt_data = get_prompt_for_version(agent_name, current_version, db_session)

        print("=" * 80)
        print("PROMPT COMPARISON: Version 928 vs Current")
        print("=" * 80)

        print("\n📋 VERSION 928 PROMPT:")
        print("-" * 80)
        if prompt_v928:
            print(f"Source: {prompt_v928['source']}")
            print(f"Prompt Version: {prompt_v928.get('version', 'N/A')}")
            print(f"Workflow Config Version: {prompt_v928.get('workflow_config_version', 'N/A')}")
            print(f"Created: {prompt_v928.get('created_at', 'N/A')}")
            print(f"Change Description: {prompt_v928.get('change_description', 'N/A')}")
            print(f"\nPrompt Text ({len(prompt_v928['prompt'])} chars):")
            print(prompt_v928["prompt"])
            if prompt_v928.get("instructions"):
                print(f"\nInstructions: {prompt_v928['instructions']}")
        else:
            print("❌ No prompt found for version 928")

        print("\n\n📋 CURRENT PROMPT:")
        print("-" * 80)
        if current_config and current_prompt_data:
            print(f"Current Config Version: {current_config.version}")
            print(f"Source: {current_prompt_data['source']}")
            print(f"Prompt Version: {current_prompt_data.get('version', 'N/A')}")
            print(f"\nPrompt Text ({len(current_prompt_data['prompt'])} chars):")
            print(current_prompt_data["prompt"])
            if current_prompt_data.get("instructions"):
                print(f"\nInstructions: {current_prompt_data['instructions']}")
        else:
            print("❌ No current prompt found")

        print("\n\n🔍 COMPARISON:")
        print("-" * 80)
        if prompt_v928 and current_prompt_data:
            prompt_928_text = prompt_v928["prompt"]
            current_prompt_text = current_prompt_data["prompt"]

            if prompt_928_text == current_prompt_text:
                print("✅ PROMPTS ARE IDENTICAL")
            else:
                print("❌ PROMPTS ARE DIFFERENT")
                print("\nLength comparison:")
                print(f"  V928: {len(prompt_928_text)} chars")
                print(f"  Current: {len(current_prompt_text)} chars")
                print(f"  Difference: {abs(len(prompt_928_text) - len(current_prompt_text))} chars")

                # Show first difference
                min_len = min(len(prompt_928_text), len(current_prompt_text))
                for i in range(min_len):
                    if prompt_928_text[i] != current_prompt_text[i]:
                        start = max(0, i - 50)
                        end = min(min_len, i + 50)
                        print(f"\nFirst difference at position {i}:")
                        print(f"  V928: ...{prompt_928_text[start:end]}...")
                        print(f"  Current: ...{current_prompt_text[start:end]}...")
                        break
        else:
            print("⚠️ Cannot compare - missing data")

    finally:
        db_session.close()


if __name__ == "__main__":
    main()
