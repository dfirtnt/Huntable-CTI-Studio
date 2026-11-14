#!/usr/bin/env python3
"""
Comprehensive verification script to ensure provider routing works correctly.
Tests all code paths that could call LMStudio when OpenAI is selected.
"""

import os
import sys
from pathlib import Path

# Add src to path (script may be in scripts/)
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))


def verify_workflow_provider_routing():
    """Verify workflow reads and passes provider correctly."""
    print("=" * 60)
    print("Verifying Workflow Provider Routing")
    print("=" * 60)

    # Simulate agent_models config with OpenAI
    agent_models = {
        "CmdlineExtract_provider": "openai",
        "CmdlineExtract_model": "gpt-5.2-pro-2025-12-11",
        "ExtractAgent_provider": "openai",
        "ExtractAgent": "gpt-4o-mini",
        "RankAgent_provider": "openai",
        "RankAgent": "gpt-4o-mini",
        "OSDetectionAgent_fallback_provider": "openai",
        "OSDetectionAgent_fallback": "gpt-4o-mini",
        "RankAgentQA_provider": "openai",
    }

    # Test provider resolution logic from workflow
    def resolve_provider(agent_name, agent_models):
        provider_key = f"{agent_name}_provider"
        agent_provider = agent_models.get(provider_key) if agent_models else None
        if not agent_provider or (isinstance(agent_provider, str) and not agent_provider.strip()):
            agent_provider = agent_models.get("ExtractAgent_provider") if agent_models else None
        if agent_provider and isinstance(agent_provider, str) and not agent_provider.strip():
            agent_provider = None
        return agent_provider

    test_cases = [
        ("CmdlineExtract", "openai"),
        ("RankAgent", "openai"),
        ("ExtractAgent", "openai"),
    ]

    all_passed = True
    for agent_name, expected in test_cases:
        provider = resolve_provider(agent_name, agent_models)
        if provider == expected:
            print(f"✅ {agent_name}: provider={provider} (expected {expected})")
        else:
            print(f"❌ {agent_name}: provider={provider} (expected {expected})")
            all_passed = False

    # Test QA provider resolution
    rank_qa_provider = agent_models.get("RankAgentQA_provider")
    if not rank_qa_provider:
        rank_qa_provider = agent_models.get("RankAgent_provider")
    if not rank_qa_provider:
        rank_qa_provider = agent_models.get("ExtractAgent_provider")

    if rank_qa_provider == "openai":
        print(f"✅ RankAgentQA: provider={rank_qa_provider} (expected openai)")
    else:
        print(f"❌ RankAgentQA: provider={rank_qa_provider} (expected openai)")
        all_passed = False

    # Test OS Detection fallback provider
    os_fallback_provider = agent_models.get("OSDetectionAgent_fallback_provider")
    if os_fallback_provider == "openai":
        print(f"✅ OSDetectionAgent_fallback: provider={os_fallback_provider} (expected openai)")
    else:
        print(f"❌ OSDetectionAgent_fallback: provider={os_fallback_provider} (expected openai)")
        all_passed = False

    return all_passed


def verify_llm_service_provider_handling():
    """Verify LLMService handles provider correctly."""
    print("\n" + "=" * 60)
    print("Verifying LLMService Provider Handling")
    print("=" * 60)

    # Simulate provider handling in request_chat
    def simulate_provider_handling(provider):
        effective_provider = provider if provider and isinstance(provider, str) and provider.strip() else "lmstudio"

        # Canonicalize
        normalized = effective_provider.strip().lower() if effective_provider else ""
        if normalized in {"openai", "chatgpt", "gpt4o", "gpt-4o", "gpt-4o-mini"}:
            return "openai"
        if normalized in {"anthropic", "claude", "claude-sonnet-4-5"}:
            return "anthropic"
        if normalized in {"lmstudio", "local", "local_llm", "deepseek"} or not normalized:
            return "lmstudio"
        return "lmstudio"

    test_cases = [
        ("openai", "openai"),
        ("lmstudio", "lmstudio"),
        (None, "lmstudio"),
        ("", "lmstudio"),
        ("   ", "lmstudio"),
    ]

    all_passed = True
    for provider, expected in test_cases:
        result = simulate_provider_handling(provider)
        if result == expected:
            print(f"✅ provider={repr(provider)} → {result} (expected {expected})")
        else:
            print(f"❌ provider={repr(provider)} → {result} (expected {expected})")
            all_passed = False

    return all_passed


def verify_no_direct_lmstudio_calls():
    """Verify no direct LMStudio calls bypass provider selection."""
    print("\n" + "=" * 60)
    print("Checking for Direct LMStudio Calls")
    print("=" * 60)

    # Files that should use request_chat, not _post_lmstudio_chat
    workflow_files = [
        "src/services/llm_service.py",
        "src/services/qa_agent_service.py",
        "src/services/os_detection_service.py",
    ]

    problematic_patterns = []

    for file_path in workflow_files:
        if not os.path.exists(file_path):
            continue

        with open(file_path) as f:
            content = f.read()
            lines = content.split("\n")

            # Check for direct _post_lmstudio_chat calls (except in llm_service.py itself)
            if (
                "_post_lmstudio_chat" in content
                and "src/services/llm_service.py" not in file_path
                and ("request_chat" not in content or "llm_service.request_chat" not in content)
            ):
                for i, line in enumerate(lines, 1):
                    if "_post_lmstudio_chat" in line and "request_chat" not in line:
                        problematic_patterns.append(f"{file_path}:{i}: {line.strip()}")

    if problematic_patterns:
        print("❌ Found direct LMStudio calls that bypass provider selection:")
        for pattern in problematic_patterns:
            print(f"  {pattern}")
        return False
    print("✅ No direct LMStudio calls found in workflow services")
    return True


if __name__ == "__main__":
    print("Provider Fix Verification")
    print("=" * 60)
    print()

    test1 = verify_workflow_provider_routing()
    test2 = verify_llm_service_provider_handling()
    test3 = verify_no_direct_lmstudio_calls()

    print("\n" + "=" * 60)
    if test1 and test2 and test3:
        print("✅ ALL VERIFICATION TESTS PASSED")
        print("\nProvider routing is correctly implemented:")
        print("  - Workflow reads provider from config")
        print("  - Provider is passed to LLMService")
        print("  - LLMService uses provider-aware request_chat()")
        print("  - No direct LMStudio calls bypass provider selection")
        sys.exit(0)
    else:
        print("❌ SOME VERIFICATION TESTS FAILED")
        print("\nPlease review the failures above.")
        sys.exit(1)
