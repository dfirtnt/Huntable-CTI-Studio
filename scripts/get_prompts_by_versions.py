#!/usr/bin/env python3
"""Query agent prompts for multiple workflow config versions."""

import json
import sys

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable


def parse_prompt_structure(prompt_str):
    """Parse nested JSON prompt structure and extract readable content."""
    if not prompt_str:
        return {"raw": "", "role": "", "user_template": "", "parsed": False}

    try:
        # Try to parse as JSON
        prompt_obj = json.loads(prompt_str)

        # Extract role field - it may contain escaped JSON or plain text
        role = prompt_obj.get("role", "")

        # If role starts with {ROLE: it's a template format, extract the actual text
        if role.startswith("{ROLE:"):
            # Extract content after {ROLE:
            # Format is: {ROLE:"text"\n...} or {ROLE:"text"...}
            role = role[6:].strip()  # Remove "{ROLE:"

            # Remove trailing } if it's the last non-whitespace character
            role = role.rstrip()
            if role.endswith("}"):
                role = role[:-1].rstrip()

            # Unescape JSON strings (handle common escape sequences)
            # Order matters: handle \\ first, then \n, then \"
            role = role.replace("\\\\", "\x00")  # Temporary placeholder
            role = role.replace("\\n", "\n")
            role = role.replace('\\"', '"')
            role = role.replace("\x00", "\\")  # Restore actual backslashes

            # Remove leading quote if the string starts with a quoted section
            role = role.strip()
            if role.startswith('"'):
                # Find the matching closing quote (may be escaped)
                # Simple case: if it starts with ", find the first unescaped "
                i = 1
                while i < len(role):
                    if role[i] == '"' and role[i - 1] != "\\":
                        # Found matching quote, remove both
                        role = role[1:i] + role[i + 1 :]
                        break
                    i += 1
                else:
                    # No matching quote found, just remove leading quote
                    role = role[1:]

        # Try to parse role as JSON if it looks like it
        if role.startswith('{"role"'):
            try:
                role_obj = json.loads(role)
                role = role_obj.get("role", role)
            except:
                pass

        return {
            "raw": prompt_str,
            "role": role,
            "user_template": prompt_obj.get("user_template", ""),
            "task": prompt_obj.get("task", ""),
            "json_example": prompt_obj.get("json_example", ""),
            "instructions": prompt_obj.get("instructions", ""),
            "parsed": True,
        }
    except json.JSONDecodeError:
        # If not JSON, return as-is
        return {
            "raw": prompt_str,
            "role": prompt_str[:200] + "..." if len(prompt_str) > 200 else prompt_str,
            "parsed": False,
        }


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
        }

    # Fall back to workflow config's agent_prompts JSONB
    config = (
        db_session.query(AgenticWorkflowConfigTable)
        .filter(AgenticWorkflowConfigTable.version == config_version)
        .first()
    )

    if config and config.agent_prompts and agent_name in config.agent_prompts:
        prompt_data = config.agent_prompts[agent_name]
        prompt_str = prompt_data.get("prompt", "")
        parsed = parse_prompt_structure(prompt_str)

        result = {
            "source": "agentic_workflow_config.agent_prompts",
            "workflow_config_version": config_version,
            "prompt_text": parsed["role"],
            "user_template": parsed.get("user_template", ""),
            "instructions": prompt_data.get("instructions", "") or parsed.get("instructions", ""),
        }

        # Include raw if different from parsed
        if not parsed["parsed"] or parsed["raw"] != parsed["role"]:
            result["raw_prompt"] = prompt_str[:500] + "..." if len(prompt_str) > 500 else prompt_str

        return result

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
            "source": f"agent_prompt_versions (inherited from v{prev_version.workflow_config_version})",
            "prompt": prev_version.prompt,
            "instructions": prev_version.instructions,
            "version": prev_version.version,
            "workflow_config_version": prev_version.workflow_config_version,
            "note": f"Config v{config_version} inherits from v{prev_version.workflow_config_version}",
        }

    return None


def main():
    if len(sys.argv) < 3:
        print("Usage: python get_prompts_by_versions.py <agent_name> <version1> [version2] [version3] ...")
        print("Example: python get_prompts_by_versions.py CmdlineExtract 928 941 978")
        sys.exit(1)

    agent_name = sys.argv[1]
    versions = [int(v) for v in sys.argv[2:]]

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        results = {}
        for version in versions:
            result = get_prompt_for_version(agent_name, version, db_session)
            if result:
                results[version] = result
            else:
                results[version] = {"error": "Prompt not found for this version"}

        # Pretty print with better formatting
        output = json.dumps(results, indent=2, ensure_ascii=False)
        print(output)
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
