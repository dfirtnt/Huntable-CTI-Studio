"""Tests for GPT-4o content optimization functionality."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

from src.utils.gpt4o_optimizer import GPT4oContentOptimizer, optimize_article_content, estimate_gpt4o_cost, get_optimization_stats


class TestGPT4oContentOptimizer:
    """Test GPT4oContentOptimizer functionality."""

    @pytest.fixture
    def optimizer(self):
        """Create GPT4oContentOptimizer instance for testing."""
        return GPT4oContentOptimizer()

    @pytest.fixture
    def sample_content(self):
        """Create sample content for testing."""
        return """
        This is a threat intelligence article about advanced persistent threats.
        The article discusses PowerShell techniques including rundll32.exe and certutil.
        It covers command-line obfuscation and registry persistence mechanisms.
        The content includes specific IOCs and technical details for threat hunters.
        """

    @pytest.fixture
    def mock_filter_result(self):
        """Create mock filter result."""
        return Mock(
            filtered_content="Filtered content with threat hunting details",
            is_huntable=True,
            confidence=0.8,
            cost_savings=0.3,
            removed_chunks=["Marketing content", "Acknowledgments"]
        )

    def test_init(self, optimizer):
        """Test GPT4oContentOptimizer initialization."""
        assert optimizer is not None
        assert hasattr(optimizer, 'content_filter')
        assert hasattr(optimizer, 'filter_stats')
        assert optimizer.filter_stats['total_requests'] == 0

    def test_init_with_model_path(self):
        """Test initialization with model path."""
        model_path = "/path/to/model"
        optimizer = GPT4oContentOptimizer(model_path)
        assert optimizer.content_filter.model_path == model_path

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_success(self, optimizer, sample_content, mock_filter_result):
        """Test successful content optimization."""
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model') as mock_load:
                with patch.object(optimizer.content_filter, 'filter_content', return_value=mock_filter_result):
                    result = await optimizer.optimize_content_for_gpt4o(sample_content)
        
        assert result['success'] is True
        assert result['original_content'] == sample_content
        assert result['filtered_content'] == mock_filter_result.filtered_content
        assert result['is_huntable'] is True
        assert result['confidence'] == 0.8
        assert result['cost_savings'] > 0
        assert result['tokens_saved'] > 0
        assert 'optimization_stats' in result
        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_custom_parameters(self, optimizer, sample_content, mock_filter_result):
        """Test content optimization with custom parameters."""
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content', return_value=mock_filter_result) as mock_filter:
                    result = await optimizer.optimize_content_for_gpt4o(
                        sample_content, 
                        min_confidence=0.8, 
                        chunk_size=2000
                    )
        
        assert result['success'] is True
        mock_filter.assert_called_once_with(sample_content, 0.8, 2000)

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_filtering_failure(self, optimizer, sample_content):
        """Test content optimization when filtering fails."""
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content', side_effect=Exception("Filter error")):
                    result = await optimizer.optimize_content_for_gpt4o(sample_content)
        
        assert result['success'] is False
        assert 'error' in result
        assert result['original_content'] == sample_content
        assert result['filtered_content'] == sample_content  # Fallback to original
        assert result['cost_savings'] == 0.0
        assert result['tokens_saved'] == 0

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_model_not_loaded(self, optimizer, sample_content, mock_filter_result):
        """Test content optimization when model needs to be loaded."""
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model') as mock_load:
                with patch.object(optimizer.content_filter, 'filter_content', return_value=mock_filter_result):
                    result = await optimizer.optimize_content_for_gpt4o(sample_content)
        
        assert result['success'] is True
        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_model_already_loaded(self, optimizer, sample_content, mock_filter_result):
        """Test content optimization when model is already loaded."""
        with patch.object(optimizer.content_filter, 'model', Mock()):
            with patch.object(optimizer.content_filter, 'load_model') as mock_load:
                with patch.object(optimizer.content_filter, 'filter_content', return_value=mock_filter_result):
                    result = await optimizer.optimize_content_for_gpt4o(sample_content)
        
        assert result['success'] is True
        mock_load.assert_not_called()

    def test_get_cost_estimate_with_filtering(self, optimizer, sample_content):
        """Test cost estimation with filtering enabled."""
        with patch.object(optimizer, 'optimize_content_for_gpt4o') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_tokens': 1000,
                'cost_savings': 0.05
            }
            
            result = optimizer.get_cost_estimate(sample_content, use_filtering=True)
        
        assert result['filtering_enabled'] is True
        assert result['cost_savings'] == 0.05
        assert result['input_tokens'] > 0
        assert result['output_tokens'] == 2000
        assert result['total_cost'] > 0
        mock_optimize.assert_called_once()

    def test_get_cost_estimate_without_filtering(self, optimizer, sample_content):
        """Test cost estimation without filtering."""
        result = optimizer.get_cost_estimate(sample_content, use_filtering=False)
        
        assert result['filtering_enabled'] is False
        assert result['cost_savings'] == 0.0
        assert result['input_tokens'] > 0
        assert result['output_tokens'] == 2000
        assert result['total_cost'] > 0

    def test_get_cost_estimate_optimization_failure(self, optimizer, sample_content):
        """Test cost estimation when optimization fails."""
        with patch.object(optimizer, 'optimize_content_for_gpt4o') as mock_optimize:
            mock_optimize.return_value = {
                'success': False,
                'error': 'Optimization failed'
            }
            
            result = optimizer.get_cost_estimate(sample_content, use_filtering=True)
        
        assert result['filtering_enabled'] is True
        assert result['cost_savings'] == 0.0
        assert result['input_tokens'] > 0

    def test_get_cost_estimate_exception(self, optimizer, sample_content):
        """Test cost estimation with exception."""
        with patch.object(optimizer, 'optimize_content_for_gpt4o', side_effect=Exception("Test error")):
            result = optimizer.get_cost_estimate(sample_content, use_filtering=True)
        
        assert 'error' in result
        assert result['filtering_enabled'] is False
        assert result['cost_savings'] == 0.0

    def test_get_optimization_stats_empty(self, optimizer):
        """Test getting optimization stats when no requests made."""
        stats = optimizer.get_optimization_stats()
        
        assert stats['total_requests'] == 0
        assert stats['total_cost_savings'] == 0.0
        assert stats['total_tokens_saved'] == 0
        assert stats['avg_cost_reduction'] == 0.0

    def test_get_optimization_stats_with_data(self, optimizer):
        """Test getting optimization stats with data."""
        optimizer.filter_stats['total_requests'] = 10
        optimizer.filter_stats['total_cost_savings'] = 5.0
        optimizer.filter_stats['total_tokens_saved'] = 10000
        
        stats = optimizer.get_optimization_stats()
        
        assert stats['total_requests'] == 10
        assert stats['total_cost_savings'] == 5.0
        assert stats['total_tokens_saved'] == 10000
        assert stats['avg_cost_reduction'] == 0.5
        assert stats['avg_tokens_saved_per_request'] == 1000

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_stats_update(self, optimizer, sample_content, mock_filter_result):
        """Test that optimization updates statistics."""
        initial_requests = optimizer.filter_stats['total_requests']
        
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content', return_value=mock_filter_result):
                    await optimizer.optimize_content_for_gpt4o(sample_content)
        
        assert optimizer.filter_stats['total_requests'] == initial_requests + 1
        assert optimizer.filter_stats['total_cost_savings'] > 0
        assert optimizer.filter_stats['total_tokens_saved'] > 0

    def test_cost_calculation_accuracy(self, optimizer, sample_content):
        """Test cost calculation accuracy."""
        # Test with known content length
        test_content = "x" * 4000  # 4000 characters
        result = optimizer.get_cost_estimate(test_content, use_filtering=False)
        
        # GPT-4o pricing: $5.00 per 1M input tokens, $15.00 per 1M output tokens
        expected_input_tokens = 1000 + 1508  # content + prompt
        expected_output_tokens = 2000
        
        expected_input_cost = (expected_input_tokens / 1000000) * 5.00
        expected_output_cost = (expected_output_tokens / 1000000) * 15.00
        expected_total_cost = expected_input_cost + expected_output_cost
        
        assert abs(result['input_cost'] - expected_input_cost) < 0.001
        assert abs(result['output_cost'] - expected_output_cost) < 0.001
        assert abs(result['total_cost'] - expected_total_cost) < 0.001

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_large_content(self, optimizer):
        """Test content optimization with large content."""
        large_content = "x" * 100000  # 100KB content
        
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_result = Mock(
                        filtered_content="Filtered large content",
                        is_huntable=True,
                        confidence=0.9,
                        cost_savings=0.4,
                        removed_chunks=[]
                    )
                    mock_filter.return_value = mock_result
                    
                    result = await optimizer.optimize_content_for_gpt4o(large_content)
        
        assert result['success'] is True
        assert result['original_tokens'] > result['filtered_tokens']
        assert result['tokens_saved'] > 0
        assert result['cost_savings'] > 0

    @pytest.mark.asyncio
    async def test_optimize_content_for_gpt4o_empty_content(self, optimizer):
        """Test content optimization with empty content."""
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_result = Mock(
                        filtered_content="",
                        is_huntable=False,
                        confidence=0.0,
                        cost_savings=1.0,
                        removed_chunks=[]
                    )
                    mock_filter.return_value = mock_result
                    
                    result = await optimizer.optimize_content_for_gpt4o("")
        
        assert result['success'] is True
        assert result['original_tokens'] == 0
        assert result['filtered_tokens'] == 0
        assert result['tokens_saved'] == 0
        assert result['cost_savings'] == 0.0


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.asyncio
    async def test_optimize_article_content(self, sample_content):
        """Test optimize_article_content convenience function."""
        with patch('src.utils.gpt4o_optimizer.gpt4o_optimizer.optimize_content_for_gpt4o') as mock_optimize:
            mock_optimize.return_value = {'success': True, 'filtered_content': 'test'}
            
            result = await optimize_article_content(sample_content, min_confidence=0.8)
        
        assert result['success'] is True
        mock_optimize.assert_called_once_with(sample_content, 0.8)

    def test_estimate_gpt4o_cost(self, sample_content):
        """Test estimate_gpt4o_cost convenience function."""
        with patch('src.utils.gpt4o_optimizer.gpt4o_optimizer.get_cost_estimate') as mock_estimate:
            mock_estimate.return_value = {'total_cost': 0.05}
            
            result = estimate_gpt4o_cost(sample_content, use_filtering=True)
        
        assert result['total_cost'] == 0.05
        mock_estimate.assert_called_once_with(sample_content, True)

    def test_get_optimization_stats(self):
        """Test get_optimization_stats convenience function."""
        with patch('src.utils.gpt4o_optimizer.gpt4o_optimizer.get_optimization_stats') as mock_stats:
            mock_stats.return_value = {'total_requests': 5}
            
            result = get_optimization_stats()
        
        assert result['total_requests'] == 5
        mock_stats.assert_called_once()


class TestGPT4oContentOptimizerIntegration:
    """Integration tests for GPT4oContentOptimizer."""

    @pytest.fixture
    def sample_content(self):
        """Create sample content for testing."""
        return """
        This is a comprehensive threat intelligence article about APT campaigns.
        
        The article discusses various attack techniques including:
        - PowerShell execution with encoded commands
        - Registry persistence mechanisms
        - Command-line obfuscation techniques
        - Network communication patterns
        
        Technical details include:
        - rundll32.exe execution patterns
        - certutil usage for file operations
        - WMI command execution
        - Scheduled task creation
        
        This content is highly relevant for threat hunters and detection engineers.
        """

    @pytest.mark.asyncio
    async def test_end_to_end_optimization(self, sample_content):
        """Test end-to-end content optimization workflow."""
        optimizer = GPT4oContentOptimizer()
        
        # Mock the content filter to avoid actual ML model loading
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_result = Mock(
                        filtered_content="Filtered threat intelligence content with technical details",
                        is_huntable=True,
                        confidence=0.85,
                        cost_savings=0.25,
                        removed_chunks=["Introduction", "Conclusion"]
                    )
                    mock_filter.return_value = mock_result
                    
                    # Test optimization
                    result = await optimizer.optimize_content_for_gpt4o(sample_content)
                    
                    # Test cost estimation
                    cost_result = optimizer.get_cost_estimate(sample_content, use_filtering=True)
                    
                    # Test stats
                    stats = optimizer.get_optimization_stats()
        
        # Verify optimization results
        assert result['success'] is True
        assert result['is_huntable'] is True
        assert result['confidence'] == 0.85
        assert result['cost_savings'] > 0
        assert result['tokens_saved'] > 0
        
        # Verify cost estimation
        assert cost_result['filtering_enabled'] is True
        assert cost_result['total_cost'] > 0
        assert cost_result['cost_savings'] > 0
        
        # Verify stats update
        assert stats['total_requests'] == 1
        assert stats['total_cost_savings'] > 0
        assert stats['total_tokens_saved'] > 0

    @pytest.mark.asyncio
    async def test_multiple_optimizations(self, sample_content):
        """Test multiple content optimizations."""
        optimizer = GPT4oContentOptimizer()
        
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_result = Mock(
                        filtered_content="Filtered content",
                        is_huntable=True,
                        confidence=0.8,
                        cost_savings=0.2,
                        removed_chunks=[]
                    )
                    mock_filter.return_value = mock_result
                    
                    # Perform multiple optimizations
                    for i in range(3):
                        await optimizer.optimize_content_for_gpt4o(f"Content {i}")
                    
                    stats = optimizer.get_optimization_stats()
        
        assert stats['total_requests'] == 3
        assert stats['total_cost_savings'] > 0
        assert stats['total_tokens_saved'] > 0
        assert stats['avg_cost_reduction'] > 0
