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
        
        result = service.detect_windows_huntables(article_content)
        
        assert isinstance(result, dict)
        assert 'has_windows_huntables' in result
        assert isinstance(result['has_windows_huntables'], bool)

    def test_detect_windows_huntable_with_perfect_discriminators(self, service):
        """Test detection with perfect discriminators."""
        article_content = "rundll32.exe executed with suspicious parameters"
        
        result = service.detect_windows_huntables(article_content)
        
        assert result['has_windows_huntables'] is True

    def test_detect_windows_huntable_no_model_fallback(self, service_no_model):
        """Test fallback behavior when model not available."""
        article_content = "powershell.exe -Command 'test'"
        
        result = service_no_model.detect_windows_huntables(article_content)
        
        # Should fall back to rule-based check
        assert isinstance(result, dict)
        assert 'has_windows_huntables' in result

    def test_check_perfect_discriminators(self, service):
        """Test perfect discriminator checking."""
        content_with_discriminators = "powershell.exe -encodedcommand base64"
        
        result = service.check_perfect_discriminators(content_with_discriminators)
        
        assert isinstance(result, dict)
        assert 'has_windows_huntables' in result
        assert isinstance(result['has_windows_huntables'], bool)

    def test_extract_keyword_features(self, service):
        """Test keyword feature extraction."""
        article_metadata = {
            'content': 'powershell.exe rundll32.exe wmic.exe',
            'lolbas_matches': ['powershell.exe', 'rundll32.exe'],
            'perfect_keyword_matches': ['powershell.exe'],
            'good_keyword_matches': ['wmic.exe']
        }
        
        features = service._extract_keyword_features(article_metadata)
        
        import numpy as np
        assert isinstance(features, np.ndarray)
        assert len(features) > 0
