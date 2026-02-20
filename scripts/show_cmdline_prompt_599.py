#!/usr/bin/env python3
"""Print CmdlineExtract prompt for workflow config version 599."""

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable


def main():
    db = DatabaseManager()
    session = db.get_session()
    try:
        config_version = 599
        agent_name = "CmdlineExtract"
        # Try agent_prompt_versions first
        pv = (
            session.query(AgentPromptVersionTable)
            .filter(
                AgentPromptVersionTable.agent_name == agent_name,
                AgentPromptVersionTable.workflow_config_version == config_version,
            )
            .order_by(AgentPromptVersionTable.version.desc())
            .first()
        )
        if pv:
            print("Source: agent_prompt_versions")
            print("workflow_config_version:", config_version, "prompt_version:", pv.version)
            print()
            print("--- PROMPT ---")
            print(pv.prompt or "")
            if pv.instructions:
                print()
                print("--- INSTRUCTIONS ---")
                print(pv.instructions)
            return
        config = (
            session.query(AgenticWorkflowConfigTable)
            .filter(AgenticWorkflowConfigTable.version == config_version)
            .first()
        )
        if config and config.agent_prompts and agent_name in config.agent_prompts:
            data = config.agent_prompts[agent_name]
            print("Source: agentic_workflow_config.agent_prompts")
            print()
            print("--- PROMPT ---")
            print(data.get("prompt", ""))
            if data.get("instructions"):
                print()
                print("--- INSTRUCTIONS ---")
                print(data.get("instructions", ""))
            return
        print("No CmdlineExtract prompt found for config version 599")
    finally:
        session.close()


if __name__ == "__main__":
    main()
