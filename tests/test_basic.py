"""
Basic test to verify testing infrastructure.
"""
import pytest

def test_basic_functionality():
    """Basic test to verify pytest is working."""
    assert True
    assert 1 + 1 == 2
    assert "hello" in "hello world"

@pytest.mark.smoke
def test_smoke_marker():
    """Test that smoke marker works."""
    assert True

@pytest.mark.api
def test_api_marker():
    """Test that api marker works."""
    assert True

@pytest.mark.ui
def test_ui_marker():
    """Test that ui marker works."""
    assert True

@pytest.mark.integration
def test_integration_marker():
    """Test that integration marker works."""
    assert True

@pytest.mark.slow
def test_slow_marker():
    """Test that slow marker works."""
    assert True
