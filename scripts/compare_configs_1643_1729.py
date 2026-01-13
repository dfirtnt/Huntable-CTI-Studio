#!/usr/bin/env python3
"""Compare workflow config versions 1643 and 1729 (Hunt Query eval focus)."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgentPromptVersionTable
import json
try:
    from deepdiff import DeepDiff
    HAS_DEEPDIFF = True
except ImportError:
    HAS_DEEPDIFF = False

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
        "rank_agent_enabled": getattr(config, 'rank_agent_enabled', True),
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

def compare_dicts(d1, d2, path="", v1_name="v1643", v2_name="v1729"):
    """Recursively compare two dictionaries and return differences."""
    differences = []
    
    all_keys = set(d1.keys()) | set(d2.keys())
    
    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        
        if key not in d1:
            differences.append(f"  + {current_path}: {d2[key]} (only in {v2_name})")
        elif key not in d2:
            differences.append(f"  - {current_path}: {d1[key]} (only in {v1_name})")
        elif d1[key] != d2[key]:
            if isinstance(d1[key], dict) and isinstance(d2[key], dict):
                differences.extend(compare_dicts(d1[key], d2[key], current_path, v1_name, v2_name))
            else:
                differences.append(f"  ~ {current_path}:")
                differences.append(f"      {v1_name}:  {d1[key]}")
                differences.append(f"      {v2_name}: {d2[key]}")
    
    return differences

def main():
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        print("=" * 80)
        print("WORKFLOW CONFIG COMPARISON: v1643 vs v1729 (Hunt Query Eval Focus)")
        print("=" * 80)
        
        # Get both configs
        config_1643 = get_config(1643, db_session)
        config_1729 = get_config(1729, db_session)
        
        if not config_1643:
            print("❌ Config 1643 not found")
            return
        
        if not config_1729:
            print("❌ Config 1729 not found")
            return
        
        print(f"\n📋 CONFIG 1643:")
        print(f"  ID: {config_1643['id']}")
        print(f"  Active: {config_1643['is_active']}")
        print(f"  Description: {config_1643['description']}")
        print(f"  Created: {config_1643['created_at']}")
        
        print(f"\n📋 CONFIG 1729:")
        print(f"  ID: {config_1729['id']}")
        print(f"  Active: {config_1729['is_active']}")
        print(f"  Description: {config_1729['description']}")
        print(f"  Created: {config_1729['created_at']}")
        
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
            "rank_agent_enabled",
            "qa_max_retries",
        ]
        
        scalar_diffs = []
        for field in scalar_fields:
            v1643_val = config_1643.get(field)
            v1729_val = config_1729.get(field)
            if v1643_val != v1729_val:
                scalar_diffs.append(f"  {field}:")
                scalar_diffs.append(f"    v1643:  {v1643_val}")
                scalar_diffs.append(f"    v1729: {v1729_val}")
        
        if scalar_diffs:
            print("\n".join(scalar_diffs))
        else:
            print("  ✅ All scalar fields are identical")
        
        # Compare qa_enabled
        print(f"\n🔍 QA_ENABLED COMPARISON:")
        print("-" * 80)
        qa_1643 = config_1643.get("qa_enabled") or {}
        qa_1729 = config_1729.get("qa_enabled") or {}
        if qa_1643 != qa_1729:
            print("  Differences found:")
            qa_diffs = compare_dicts(qa_1643, qa_1729, v1_name="v1643", v2_name="v1729")
            print("\n".join(qa_diffs))
        else:
            print("  ✅ qa_enabled is identical")
        
        # Compare agent_models
        print(f"\n🔍 AGENT_MODELS COMPARISON:")
        print("-" * 80)
        models_1643 = config_1643.get("agent_models") or {}
        models_1729 = config_1729.get("agent_models") or {}
        if models_1643 != models_1729:
            print("  Differences found:")
            model_diffs = compare_dicts(models_1643, models_1729, v1_name="v1643", v2_name="v1729")
            print("\n".join(model_diffs))
        else:
            print("  ✅ agent_models is identical")
        
        # Compare agent_prompts (structure only, not full text)
        print(f"\n🔍 AGENT_PROMPTS STRUCTURE COMPARISON:")
        print("-" * 80)
        prompts_1643 = config_1643.get("agent_prompts") or {}
        prompts_1729 = config_1729.get("agent_prompts") or {}
        
        all_agents = set(prompts_1643.keys()) | set(prompts_1729.keys())
        prompt_structure_diffs = []
        
        for agent in sorted(all_agents):
            if agent not in prompts_1643:
                prompt_structure_diffs.append(f"  + {agent}: (only in v1729)")
            elif agent not in prompts_1729:
                prompt_structure_diffs.append(f"  - {agent}: (only in v1643)")
            else:
                # Compare prompt keys
                p1643_keys = set(prompts_1643[agent].keys())
                p1729_keys = set(prompts_1729[agent].keys())
                if p1643_keys != p1729_keys:
                    prompt_structure_diffs.append(f"  ~ {agent} keys differ:")
                    prompt_structure_diffs.append(f"      v1643:  {sorted(p1643_keys)}")
                    prompt_structure_diffs.append(f"      v1729: {sorted(p1729_keys)}")
                else:
                    # Check if prompt text differs
                    p1643_text = prompts_1643[agent].get("prompt", "")
                    p1729_text = prompts_1729[agent].get("prompt", "")
                    if p1643_text != p1729_text:
                        prompt_structure_diffs.append(f"  ~ {agent} prompt text differs:")
                        prompt_structure_diffs.append(f"      v1643 length:  {len(p1643_text)} chars")
                        prompt_structure_diffs.append(f"      v1729 length: {len(p1729_text)} chars")
        
        if prompt_structure_diffs:
            print("\n".join(prompt_structure_diffs))
        else:
            print("  ✅ agent_prompts structure is identical")
        
        # Detailed HuntQueriesExtract prompt comparison (CRITICAL for Hunt Query evals)
        print(f"\n🔍 HUNTQUERIESEXTRACT PROMPT DETAILED COMPARISON:")
        print("-" * 80)
        hunt_prompt_1643 = get_prompt_for_version("HuntQueriesExtract", 1643, db_session)
        hunt_prompt_1729 = get_prompt_for_version("HuntQueriesExtract", 1729, db_session)
        
        if hunt_prompt_1643 and hunt_prompt_1729:
            print(f"\n  v1643:")
            print(f"    Source: {hunt_prompt_1643['source']}")
            print(f"    Prompt Version: {hunt_prompt_1643.get('version', 'N/A')}")
            print(f"    Length: {len(hunt_prompt_1643['prompt'])} chars")
            if hunt_prompt_1643.get('change_description'):
                print(f"    Change Description: {hunt_prompt_1643['change_description']}")
            
            print(f"\n  v1729:")
            print(f"    Source: {hunt_prompt_1729['source']}")
            print(f"    Prompt Version: {hunt_prompt_1729.get('version', 'N/A')}")
            print(f"    Length: {len(hunt_prompt_1729['prompt'])} chars")
            if hunt_prompt_1729.get('change_description'):
                print(f"    Change Description: {hunt_prompt_1729['change_description']}")
            
            if hunt_prompt_1643['prompt'] == hunt_prompt_1729['prompt']:
                print(f"\n  ✅ Prompt text is IDENTICAL")
            else:
                print(f"\n  ❌ Prompt text is DIFFERENT")
                # Find first difference
                p1643_text = hunt_prompt_1643['prompt']
                p1729_text = hunt_prompt_1729['prompt']
                min_len = min(len(p1643_text), len(p1729_text))
                for i in range(min_len):
                    if p1643_text[i] != p1729_text[i]:
                        start = max(0, i - 200)
                        end = min(min_len, i + 200)
                        print(f"\n  First difference at position {i}:")
                        print(f"    v1643:  ...{p1643_text[start:end]}...")
                        print(f"    v1729: ...{p1729_text[start:end]}...")
                        break
                
                # Show instructions comparison
                inst_1643 = hunt_prompt_1643.get('instructions', '')
                inst_1729 = hunt_prompt_1729.get('instructions', '')
                if inst_1643 != inst_1729:
                    print(f"\n  Instructions differ:")
                    print(f"    v1643 length:  {len(inst_1643)} chars")
                    print(f"    v1729 length: {len(inst_1729)} chars")
                else:
                    print(f"  ✅ Instructions are identical")
        else:
            if not hunt_prompt_1643:
                print("  ❌ HuntQueriesExtract prompt not found for v1643")
            if not hunt_prompt_1729:
                print("  ❌ HuntQueriesExtract prompt not found for v1729")
        
        # Check for HuntQueriesQA prompt
        print(f"\n🔍 HUNTQUERIESQA PROMPT COMPARISON:")
        print("-" * 80)
        qa_prompt_1643 = get_prompt_for_version("HuntQueriesQA", 1643, db_session)
        qa_prompt_1729 = get_prompt_for_version("HuntQueriesQA", 1729, db_session)
        
        if qa_prompt_1643 and qa_prompt_1729:
            if qa_prompt_1643['prompt'] == qa_prompt_1729['prompt']:
                print("  ✅ HuntQueriesQA prompt is IDENTICAL")
            else:
                print("  ❌ HuntQueriesQA prompt is DIFFERENT")
                print(f"    v1643 length:  {len(qa_prompt_1643['prompt'])} chars")
                print(f"    v1729 length: {len(qa_prompt_1729['prompt'])} chars")
        elif qa_prompt_1643 or qa_prompt_1729:
            if not qa_prompt_1643:
                print("  ⚠️ HuntQueriesQA prompt only in v1729")
            if not qa_prompt_1729:
                print("  ⚠️ HuntQueriesQA prompt only in v1643")
        else:
            print("  ℹ️ HuntQueriesQA prompt not found in either version")
        
        # Deep diff for complete comparison
        print(f"\n🔍 DEEP DIFF ANALYSIS:")
        print("-" * 80)
        if HAS_DEEPDIFF:
            try:
                diff = DeepDiff(config_1643, config_1729, ignore_order=True, verbose_level=2)
                if diff:
                    print("  Differences found:")
                    print(json.dumps(diff, indent=2, default=str))
                else:
                    print("  ✅ Configs are completely identical (except metadata)")
            except Exception as e:
                print(f"  ⚠️ Deep diff failed: {e}")
        else:
            print("  ℹ️ deepdiff module not available, skipping deep diff")
        
    finally:
        db_session.close()

if __name__ == "__main__":
    main()
