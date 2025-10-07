"""
Pytest configuration for AI Assistant tests.
Provides fixtures and configuration specific to AI testing.
"""
import pytest
import os
import asyncio
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def ai_test_config():
    """Configuration for AI tests."""
    return {
        'openai_api_key': os.getenv('OPENAI_API_KEY'),
        'anthropic_api_key': os.getenv('ANTHROPIC_API_KEY'),
        'ollama_endpoint': os.getenv('OLLAMA_ENDPOINT', 'http://localhost:11434'),
        'test_timeout': 30.0,
        'max_retries': 3
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
        'openai': {
            'choices': [{
                'message': {
                    'content': '''
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
                    '''
                }
            }]
        },
        'anthropic': {
            'content': [{
                'text': '''
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
                '''
            }]
        },
        'ollama': """
        title: APT29 PowerShell Execution
        description: Detects APT29 PowerShell execution patterns
        logsource:
          category: process_creation
          product: windows
        detection:
          selection:
            Image: powershell.exe
            CommandLine: '*EncodedCommand*'
          condition: selection
        level: high
        tags:
          - attack.execution
          - attack.t1059.001
        """
    }


# Pytest markers for AI tests
def pytest_configure(config):
    """Configure pytest markers for AI tests."""
    config.addinivalue_line(
        "markers", "ai: mark test as AI-related"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "ui: mark test as UI test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


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
