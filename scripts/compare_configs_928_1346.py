#!/usr/bin/env python3
"""Compare workflow config versions 928 and 1346."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable
import json
from deepdiff import DeepDiff

def get_config(version: int, db_session):
    """Get full workflow config for a version."""
    config = db_session.query(AgenticWorkflowConfigTable).filter(
        AgenticWorkflowConfigTable.version == version
    ).first()
    
    if not config:
        return None
    
    return {
        "id": config.id,
        "version": config.version,
        "is_active": config.is_active,
        "description": config.description,
        "min_hunt_score": config.min_hunt_score,
        "ranking_threshold": config.ranking_threshold,
        "similarity_threshold": config.similarity_threshold,
        "junk_filter_threshold": config.junk_filter_threshold,
        "auto_trigger_hunt_score_threshold": config.auto_trigger_hunt_score_threshold,
        "sigma_fallback_enabled": config.sigma_fallback_enabled,
        "qa_enabled": config.qa_enabled,
        "qa_max_retries": config.qa_max_retries,
        "agent_models": config.agent_models,
        "agent_prompts": config.agent_prompts,
        "created_at": config.created_at.isoformat() if config.created_at else None,
    }

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
            "version": prompt_version.version,
            "workflow_config_version": prompt_version.workflow_config_version,
            "created_at": prompt_version.created_at.isoformat() if prompt_version.created_at else None,
            "change_description": prompt_version.change_description
        }
    
    # Fall back to workflow config's agent_prompts JSONB
    config = db_session.query(AgenticWorkflowConfigTable).filter(
        AgenticWorkflowConfigTable.version == config_version
    ).first()
    
    if config and config.agent_prompts and agent_name in config.agent_prompts:
        prompt_data = config.agent_prompts[agent_name]
        return {
            "source": "agentic_workflow_config.agent_prompts",
            "workflow_config_version": config_version,
            "prompt": prompt_data.get("prompt", ""),
            "instructions": prompt_data.get("instructions", ""),
        }
    
    return None

def compare_dicts(d1, d2, path=""):
    """Recursively compare two dictionaries and return differences."""
    differences = []
    
    all_keys = set(d1.keys()) | set(d2.keys())
    
    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        
        if key not in d1:
            differences.append(f"  + {current_path}: {d2[key]} (only in v1346)")
        elif key not in d2:
            differences.append(f"  - {current_path}: {d1[key]} (only in v928)")
        elif d1[key] != d2[key]:
            if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                differences.extend(compare_dicts(d1[key], d2[key], current_path))
            else:
                differences.append(f"  ~ {current_path}:")
                differences.append(f"      v928:  {d1[key]}")
                differences.append(f"      v1346: {d2[key]}")
    
    return differences

def main():
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        print("=" * 80)
        print("WORKFLOW CONFIG COMPARISON: v928 vs v1346")
        print("=" * 80)
        
        # Get both configs
        config_928 = get_config(928, db_session)
        config_1346 = get_config(1346, db_session)
        
        if not config_928:
            print("❌ Config 928 not found")
            return
        
        if not config_1346:
            print("❌ Config 1346 not found")
            return
        
        print(f"\n📋 CONFIG 928:")
        print(f"  ID: {config_928['id']}")
        print(f"  Active: {config_928['is_active']}")
        print(f"  Description: {config_928['description']}")
        print(f"  Created: {config_928['created_at']}")
        
        print(f"\n📋 CONFIG 1346:")
        print(f"  ID: {config_1346['id']}")
        print(f"  Active: {config_1346['is_active']}")
        print(f"  Description: {config_1346['description']}")
        print(f"  Created: {config_1346['created_at']}")
        
        # Compare scalar fields
        print(f"\n🔍 SCALAR FIELD COMPARISON:")
        print("-" * 80)
        scalar_fields = [
            "min_hunt_score",
            "ranking_threshold",
            "similarity_threshold",
            "junk_filter_threshold",
            "auto_trigger_hunt_score_threshold",
            "sigma_fallback_enabled",
            "qa_max_retries",
        ]
        
        scalar_diffs = []
        for field in scalar_fields:
            v928_val = config_928.get(field)
            v1346_val = config_1346.get(field)
            if v928_val != v1346_val:
                scalar_diffs.append(f"  {field}:")
                scalar_diffs.append(f"    v928:  {v928_val}")
                scalar_diffs.append(f"    v1346: {v1346_val}")
        
        if scalar_diffs:
            print("\n".join(scalar_diffs))
        else:
            print("  ✅ All scalar fields are identical")
        
        # Compare qa_enabled
        print(f"\n🔍 QA_ENABLED COMPARISON:")
        print("-" * 80)
        qa_928 = config_928.get("qa_enabled") or {}
        qa_1346 = config_1346.get("qa_enabled") or {}
        if qa_928 != qa_1346:
            print("  Differences found:")
            qa_diffs = compare_dicts(qa_928, qa_1346)
            print("\n".join(qa_diffs))
        else:
            print("  ✅ qa_enabled is identical")
        
        # Compare agent_models
        print(f"\n🔍 AGENT_MODELS COMPARISON:")
        print("-" * 80)
        models_928 = config_928.get("agent_models") or {}
        models_1346 = config_1346.get("agent_models") or {}
        if models_928 != models_1346:
            print("  Differences found:")
            model_diffs = compare_dicts(models_928, models_1346)
            print("\n".join(model_diffs))
        else:
            print("  ✅ agent_models is identical")
        
        # Compare agent_prompts (structure only, not full text)
        print(f"\n🔍 AGENT_PROMPTS STRUCTURE COMPARISON:")
        print("-" * 80)
        prompts_928 = config_928.get("agent_prompts") or {}
        prompts_1346 = config_1346.get("agent_prompts") or {}
        
        all_agents = set(prompts_928.keys()) | set(prompts_1346.keys())
        prompt_structure_diffs = []
        
        for agent in all_agents:
            if agent not in prompts_928:
                prompt_structure_diffs.append(f"  + {agent}: (only in v1346)")
            elif agent not in prompts_1346:
                prompt_structure_diffs.append(f"  - {agent}: (only in v928)")
            else:
                # Compare prompt keys
                p928_keys = set(prompts_928[agent].keys())
                p1346_keys = set(prompts_1346[agent].keys())
                if p928_keys != p1346_keys:
                    prompt_structure_diffs.append(f"  ~ {agent} keys differ:")
                    prompt_structure_diffs.append(f"      v928:  {sorted(p928_keys)}")
                    prompt_structure_diffs.append(f"      v1346: {sorted(p1346_keys)}")
                else:
                    # Check if prompt text differs
                    p928_text = prompts_928[agent].get("prompt", "")
                    p1346_text = prompts_1346[agent].get("prompt", "")
                    if p928_text != p1346_text:
                        prompt_structure_diffs.append(f"  ~ {agent} prompt text differs:")
                        prompt_structure_diffs.append(f"      v928 length:  {len(p928_text)} chars")
                        prompt_structure_diffs.append(f"      v1346 length: {len(p1346_text)} chars")
        
        if prompt_structure_diffs:
            print("\n".join(prompt_structure_diffs))
        else:
            print("  ✅ agent_prompts structure is identical")
        
        # Detailed CmdlineExtract prompt comparison
        print(f"\n🔍 CMDLINEEXTRACT PROMPT DETAILED COMPARISON:")
        print("-" * 80)
        cmdline_prompt_928 = get_prompt_for_version("CmdlineExtract", 928, db_session)
        cmdline_prompt_1346 = get_prompt_for_version("CmdlineExtract", 1346, db_session)
        
        if cmdline_prompt_928 and cmdline_prompt_1346:
            print(f"\n  v928:")
            print(f"    Source: {cmdline_prompt_928['source']}")
            print(f"    Prompt Version: {cmdline_prompt_928.get('version', 'N/A')}")
            print(f"    Length: {len(cmdline_prompt_928['prompt'])} chars")
            if cmdline_prompt_928.get('change_description'):
                print(f"    Change Description: {cmdline_prompt_928['change_description']}")
            
            print(f"\n  v1346:")
            print(f"    Source: {cmdline_prompt_1346['source']}")
            print(f"    Prompt Version: {cmdline_prompt_1346.get('version', 'N/A')}")
            print(f"    Length: {len(cmdline_prompt_1346['prompt'])} chars")
            if cmdline_prompt_1346.get('change_description'):
                print(f"    Change Description: {cmdline_prompt_1346['change_description']}")
            
            if cmdline_prompt_928['prompt'] == cmdline_prompt_1346['prompt']:
                print(f"\n  ✅ Prompt text is IDENTICAL")
            else:
                print(f"\n  ❌ Prompt text is DIFFERENT")
                # Find first difference
                p928_text = cmdline_prompt_928['prompt']
                p1346_text = cmdline_prompt_1346['prompt']
                min_len = min(len(p928_text), len(p1346_text))
                for i in range(min_len):
                    if p928_text[i] != p1346_text[i]:
                        start = max(0, i - 100)
                        end = min(min_len, i + 100)
                        print(f"\n  First difference at position {i}:")
                        print(f"    v928:  ...{p928_text[start:end]}...")
                        print(f"    v1346: ...{p1346_text[start:end]}...")
                        break
                
                # Show instructions comparison
                inst_928 = cmdline_prompt_928.get('instructions', '')
                inst_1346 = cmdline_prompt_1346.get('instructions', '')
                if inst_928 != inst_1346:
                    print(f"\n  Instructions differ:")
                    print(f"    v928 length:  {len(inst_928)} chars")
                    print(f"    v1346 length: {len(inst_1346)} chars")
                else:
                    print(f"  ✅ Instructions are identical")
        else:
            if not cmdline_prompt_928:
                print("  ❌ CmdlineExtract prompt not found for v928")
            if not cmdline_prompt_1346:
                print("  ❌ CmdlineExtract prompt not found for v1346")
        
        # Deep diff for complete comparison
        print(f"\n🔍 DEEP DIFF ANALYSIS:")
        print("-" * 80)
        try:
            diff = DeepDiff(config_928, config_1346, ignore_order=True, verbose_level=2)
            if diff:
                print("  Differences found:")
                print(json.dumps(diff, indent=2, default=str))
            else:
                print("  ✅ Configs are completely identical (except metadata)")
        except Exception as e:
            print(f"  ⚠️ Deep diff failed: {e}")
        
    finally:
        db_session.close()

if __name__ == "__main__":
    main()
