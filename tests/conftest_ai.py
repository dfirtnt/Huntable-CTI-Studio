"""
Pytest configuration for AI Assistant tests.
Provides fixtures and configuration specific to AI testing.
"""

import pytest
import os
import asyncio
from typing import AsyncGenerator


# Removed event_loop fixture - pytest-asyncio handles event loops automatically
# with asyncio_mode = auto in pytest.ini


@pytest.fixture
def ai_test_config():
    """Configuration for AI tests."""
    import getpass

    # Check for API keys in environment
    openai_key_env = os.getenv("OPENAI_API_KEY")
    anthropic_key_env = os.getenv("ANTHROPIC_API_KEY")

    # Always prompt for explicit authorization
    print("\n" + "=" * 70)
    print("AI API Key Authorization for Tests")
    print("=" * 70)
    print("These tests may use external AI APIs (OpenAI, Anthropic) which incur costs.")
    print("=" * 70)

    # Prompt for OpenAI API key authorization
    if openai_key_env:
        print(f"\n✓ OPENAI_API_KEY found in environment ({openai_key_env[:10]}...)")
        response = (
            input("Authorize use of OpenAI API key for these tests? [y/N]: ")
            .strip()
            .lower()
        )
        openai_key = openai_key_env if response == "y" else None
    else:
        print("\n⚠️  OPENAI_API_KEY not found in environment.")
        response = input("Enter OpenAI API key (or press Enter to skip): ").strip()
        openai_key = response if response else None

    # Prompt for Anthropic API key authorization
    if anthropic_key_env:
        print(
            f"\n✓ ANTHROPIC_API_KEY found in environment ({anthropic_key_env[:10]}...)"
        )
        response = (
            input("Authorize use of Anthropic API key for these tests? [y/N]: ")
            .strip()
            .lower()
        )
        anthropic_key = anthropic_key_env if response == "y" else None
    else:
        print("\n⚠️  ANTHROPIC_API_KEY not found in environment.")
        response = input("Enter Anthropic API key (or press Enter to skip): ").strip()
        anthropic_key = response if response else None

    # Summary
    if openai_key or anthropic_key:
        print("\n✓ API keys authorized for this test session.")
    else:
        print("\n⚠️  No API keys authorized. Tests will use mocked responses.")

    print("=" * 70 + "\n")

    return {
        "openai_api_key": openai_key,
        "anthropic_api_key": anthropic_key,
        "test_timeout": 30.0,
        "max_retries": 3,
    }


@pytest.fixture
def sample_threat_content():
    """Sample threat intelligence content for testing."""
    return """
    This article describes an APT29 campaign that uses PowerShell techniques
    including rundll32.exe and certutil for persistence. The threat actors
    use comspec environment variables and wmic commands to evade detection.
    
    The campaign targets Event ID 4624 and uses parent-child process relationships
    to maintain persistence. Hunters should look for svchost.exe spawning
    unusual child processes.
    
    IOCs identified:
    - IP: 192.168.1.100
    - Domain: malicious.example.com
    - Hash: a1b2c3d4e5f6789012345678901234567890abcd
    - Email: attacker@evil.com
    
    Registry keys modified:
    - HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    - HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run
    
    File paths:
    - C:\\Windows\\Temp\\malware.exe
    - %TEMP%\\suspicious.dll
    """


@pytest.fixture
def sample_large_content():
    """Sample large content for testing size limits."""
    return "x" * 100000  # 100KB content


@pytest.fixture
def mock_ai_responses():
    """Mock AI responses for testing."""
    return {
        "openai": {
            "choices": [
                {
                    "message": {
                        "content": """
                    SIGMA HUNTABILITY SCORE: 8
                    
                    CATEGORY BREAKDOWN:
                    - Process/Command-Line (0-4): 4 - Detailed PowerShell and LOLBAS techniques
                    - Persistence/System Mods (0-3): 3 - Registry persistence mechanisms
                    - Log Correlation (0-2): 1 - Event ID correlation mentioned
                    - Structured Patterns (0-1): 1 - Clear file path patterns
                    
                    SIGMA-READY OBSERVABLES:
                    - PowerShell execution with encoded commands
                    - rundll32.exe and certutil usage
                    - Registry key modifications
                    - Process creation patterns
                    
                    REQUIRED LOG SOURCES:
                    - Windows Event Logs (4688, 4624)
                    - Sysmon Event ID 1
                    - Registry monitoring
                    
                    RULE FEASIBILITY:
                    High - Multiple detection rules can be created immediately
                    """
                    }
                }
            ]
        },
        "anthropic": {
            "content": [
                {
                    "text": """
                SIGMA HUNTABILITY SCORE: 9
                
                CATEGORY BREAKDOWN:
                - Process/Command-Line (0-4): 4 - Excellent PowerShell and LOLBAS coverage
                - Persistence/System Mods (0-3): 3 - Comprehensive registry persistence
                - Log Correlation (0-2): 2 - Strong Event ID correlation
                - Structured Patterns (0-1): 1 - Clear file path and process patterns
                
                SIGMA-READY OBSERVABLES:
                - PowerShell execution with encoded commands
                - rundll32.exe and certutil usage
                - Registry key modifications
                - Process creation patterns
                - WMI command execution
                
                REQUIRED LOG SOURCES:
                - Windows Event Logs (4688, 4624)
                - Sysmon Event ID 1, 13
                - Registry monitoring
                - WMI event logs
                
                RULE FEASIBILITY:
                Very High - Multiple high-quality detection rules can be created
                """
                }
            ]
        },
    }


# Pytest markers for AI tests
def pytest_configure(config):
    """Configure pytest markers for AI tests."""
    config.addinivalue_line("markers", "ai: mark test as AI-related")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "ui: mark test as UI test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names."""
    for item in items:
        # Add markers based on test file names
        if "ai" in item.nodeid.lower():
            item.add_marker(pytest.mark.ai)
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)
        if "ui" in item.nodeid.lower():
            item.add_marker(pytest.mark.ui)

        # Add slow marker for real API tests
        if "real_api" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)
