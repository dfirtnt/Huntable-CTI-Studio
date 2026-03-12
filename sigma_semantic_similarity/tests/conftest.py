"""Pytest fixtures: minimal valid Sigma YAML rules."""

import sys
from pathlib import Path

import pytest

# Ensure package root is on path when running tests from repo or package dir
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@pytest.fixture
def rule_windows_process_creation():
    """Minimal rule with windows.process_creation canonical class."""
    return {
        "title": "Test",
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"Image": "cmd.exe"},
            "condition": "selection",
        },
    }


@pytest.fixture
def rule_windows_process_creation_two():
    """Another rule same class, different atom."""
    return {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"Image": "powershell.exe"},
            "condition": "selection",
        },
    }


@pytest.fixture
def rule_with_and():
    """Rule with AND condition."""
    return {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"Image": "cmd.exe"},
            "selection2": {"CommandLine|contains": "net user"},
            "condition": "selection and selection2",
        },
    }


@pytest.fixture
def rule_with_or():
    """Rule with OR condition."""
    return {
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"Image": "a.exe"},
            "selection2": {"Image": "b.exe"},
            "condition": "selection or selection2",
        },
    }
