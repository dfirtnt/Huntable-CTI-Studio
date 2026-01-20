"""Tests for huntable Windows service functionality."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from typing import Dict, Any

from src.services.huntable_windows_service import HuntableWindowsService

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestHuntableWindowsService:
    """Test HuntableWindowsService functionality."""

    @pytest.fixture
    def service(self):
        """Create HuntableWindowsService instance with mocked model loading."""
        with patch('src.services.huntable_windows_service.pickle.load') as mock_load, \
             patch('builtins.open', create=True), \
             patch('pathlib.Path.exists', return_value=True):
            mock_classifier = Mock()
            mock_scaler = Mock()
            mock_load.side_effect = [mock_classifier, mock_scaler]
            
            service = HuntableWindowsService()
            service.classifier = mock_classifier
            service.scaler = mock_scaler
            return service

    @pytest.fixture
    def service_no_model(self):
        """Create service without model (for testing fallback behavior)."""
        with patch('pathlib.Path.exists', return_value=False):
            return HuntableWindowsService()

    def test_detect_windows_huntable_success(self, service):
        """Test successful Windows huntable detection."""
        article_content = "powershell.exe -Command 'schtasks /create /tn test'"
        
        result = service.detect_windows_huntable(article_content)
        
        assert isinstance(result, dict)
        assert 'is_huntable' in result
        assert isinstance(result['is_huntable'], bool)

    def test_detect_windows_huntable_with_perfect_discriminators(self, service):
        """Test detection with perfect discriminators."""
        article_content = "rundll32.exe executed with suspicious parameters"
        
        result = service.detect_windows_huntable(article_content)
        
        assert result['is_huntable'] is True

    def test_detect_windows_huntable_no_model_fallback(self, service_no_model):
        """Test fallback behavior when model not available."""
        article_content = "powershell.exe -Command 'test'"
        
        result = service_no_model.detect_windows_huntable(article_content)
        
        # Should fall back to rule-based check
        assert isinstance(result, dict)
        assert 'is_huntable' in result

    def test_check_perfect_discriminators(self, service):
        """Test perfect discriminator checking."""
        content_with_discriminators = "powershell.exe -encodedcommand base64"
        
        has_discriminators = service._check_perfect_discriminators(content_with_discriminators)
        
        assert isinstance(has_discriminators, bool)

    def test_extract_lolbas_keywords(self, service):
        """Test LOLBAS keyword extraction."""
        content = "powershell.exe rundll32.exe wmic.exe"
        
        keywords = service._extract_lolbas_keywords(content)
        
        assert isinstance(keywords, list)
        assert len(keywords) > 0
