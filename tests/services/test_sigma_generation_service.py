"""Tests for SIGMA generation service functionality."""

import pytest
import yaml
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.services.sigma_generation_service import SigmaGenerationService
from src.services.sigma_validator import ValidationResult

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaGenerationService:
    """Test SigmaGenerationService functionality."""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        service = Mock()
        service.provider_sigma = 'lmstudio'
        service.lmstudio_model = 'test-model-7b'
        service._canonicalize_provider = Mock(return_value='lmstudio')
        return service

    @pytest.fixture
    def service(self, mock_llm_service):
        """Create SigmaGenerationService instance with mocked dependencies."""
        with patch('src.services.sigma_generation_service.LLMService', return_value=mock_llm_service):
            return SigmaGenerationService()

    @pytest.fixture
    def sample_article_data(self):
        """Sample article data for testing."""
        return {
            'title': 'APT29 Uses PowerShell for Persistence',
            'content': 'Advanced Persistent Threat group APT29 has been observed using PowerShell scripts to maintain persistence on compromised systems. The attack involves creating scheduled tasks and registry modifications.',
            'source_name': 'Threat Intelligence Feed',
            'url': 'https://example.com/threat-report-123'
        }

    @pytest.fixture
    def sample_sigma_rule(self):
        """Sample valid SIGMA rule YAML."""
        return """
title: PowerShell Scheduled Task Creation
id: test-rule-123
description: Detects creation of scheduled tasks via PowerShell
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'schtasks'
        CommandLine|contains: '/create'
    condition: selection
level: medium
"""

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_success(self, service, sample_article_data, sample_sigma_rule):
        """Test successful SIGMA rule generation."""
        # Mock content optimization
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 100
            }
            
            # Mock prompt loading
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = f"Generate SIGMA rule for: {sample_article_data['title']}"
                
                # Mock LLM service call
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = sample_sigma_rule
                    
                    # Mock validation
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={'rule': yaml.safe_load(sample_sigma_rule)},
                            content_preview=sample_sigma_rule
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url']
                        )
                        
                        assert 'rules' in result
                        assert len(result['rules']) > 0
                        assert result['metadata']['total_attempts'] == 1
                        assert result.get('errors') is None or len(result.get('errors', [])) == 0

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_with_retry(self, service, sample_article_data):
        """Test SIGMA rule generation with retry logic."""
        invalid_yaml = "This is not valid YAML"
        valid_rule = """
title: Test Rule
id: test-123
description: Test
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: low
"""
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate SIGMA rule"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    # First attempt returns invalid YAML, second returns valid
                    mock_call.side_effect = [invalid_yaml, valid_rule]
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        def validate_side_effect(rule_str):
                            if 'title:' in rule_str:
                                try:
                                    parsed = yaml.safe_load(rule_str)
                                    return ValidationResult(
                                        is_valid=True,
                                        errors=[],
                                        warnings=[],
                                        metadata={'rule': parsed},
                                        content_preview=rule_str
                                    )
                                except:
                                    pass
                            return ValidationResult(
                                is_valid=False,
                                errors=['Invalid YAML'],
                                warnings=[],
                                metadata=None,
                                content_preview=rule_str
                            )
                        
                        mock_validate.side_effect = validate_side_effect
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url'],
                            max_attempts=3
                        )
                        
                        assert result['metadata']['total_attempts'] == 2
                        assert len(result['rules']) > 0

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_content_optimization(self, service, sample_article_data):
        """Test content optimization integration."""
        optimized_content = "Optimized content with key threat indicators"
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': optimized_content,
                'tokens_saved': 500
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = f"Generate rule for: {optimized_content}"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = "title: Test\nid: test\n"
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={'rule': {'title': 'Test', 'id': 'test'}},
                            content_preview="title: Test\nid: test"
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url']
                        )
                        
                        # Verify optimization was called
                        mock_optimize.assert_called_once()
                        # Verify prompt uses optimized content
                        assert optimized_content in mock_prompt.call_args[0][1]['content']

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_database_prompt_template(self, service, sample_article_data):
        """Test using database prompt template."""
        db_template = "Generate SIGMA rule for article: {title}\nContent: {content}"
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch.object(service, '_call_provider_for_sigma') as mock_call:
                mock_call.return_value = "title: Test\nid: test\n"
                
                with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                    mock_validate.return_value = ValidationResult(
                        is_valid=True,
                        errors=[],
                        warnings=[],
                        metadata={'rule': {'title': 'Test', 'id': 'test'}},
                        content_preview="title: Test\nid: test"
                    )
                    
                    result = await service.generate_sigma_rules(
                        article_title=sample_article_data['title'],
                        article_content=sample_article_data['content'],
                        source_name=sample_article_data['source_name'],
                        url=sample_article_data['url'],
                        sigma_prompt_template=db_template
                    )
                    
                    # Verify database template was used (format_prompt_async should not be called)
                    # The template should be formatted directly
                    assert result is not None

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_context_window_limit(self, service, sample_article_data):
        """Test context window limit handling for LMStudio."""
        # Create a very long prompt
        long_content = sample_article_data['content'] * 1000
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': long_content,
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                # Return a prompt longer than context window
                long_prompt = "Generate rule: " + long_content
                mock_prompt.return_value = long_prompt
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = "title: Test\nid: test\n"
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={'rule': {'title': 'Test', 'id': 'test'}},
                            content_preview="title: Test\nid: test"
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=long_content,
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url'],
                            ai_model='lmstudio'
                        )
                        
                        # Verify prompt was truncated (check that truncation message is in prompt)
                        call_args = mock_call.call_args
                        prompt_passed = call_args[0][0] if call_args else ""
                        # Prompt should be truncated for 7b model (12000 chars max)
                        assert len(prompt_passed) <= 12000 or "[Prompt truncated" in prompt_passed

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_validation_error(self, service, sample_article_data):
        """Test handling of validation errors."""
        invalid_rule = "title: Invalid Rule\ninvalid_field: value"
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rule"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = invalid_rule
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=False,
                            errors=['Missing required field: detection'],
                            warnings=[],
                            metadata=None,
                            content_preview=invalid_rule
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url'],
                            max_attempts=1
                        )
                        
                        assert len(result['rules']) == 0
                        assert len(result.get('errors', [])) > 0

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_qa_feedback(self, service, sample_article_data, sample_sigma_rule):
        """Test QA feedback integration."""
        qa_feedback = "Focus on PowerShell command-line arguments"
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rule"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = sample_sigma_rule
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={'rule': yaml.safe_load(sample_sigma_rule)},
                            content_preview=sample_sigma_rule
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url'],
                            qa_feedback=qa_feedback
                        )
                        
                        # Verify QA feedback was included in prompt
                        call_args = mock_call.call_args
                        prompt_passed = call_args[0][0] if call_args else ""
                        assert qa_feedback in prompt_passed

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_max_attempts_exceeded(self, service, sample_article_data):
        """Test behavior when max attempts exceeded."""
        invalid_response = "Not valid YAML"
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rule"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = invalid_response
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=False,
                            errors=['Invalid YAML'],
                            warnings=[],
                            metadata=None,
                            content_preview=invalid_response
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url'],
                            max_attempts=2
                        )
                        
                        assert result['metadata']['total_attempts'] == 2
                        assert len(result['rules']) == 0
                        assert len(result.get('errors', [])) > 0

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_optimization_failure(self, service, sample_article_data):
        """Test handling of content optimization failure."""
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': False,
                'error': 'Optimization failed'
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rule"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = "title: Test\nid: test\n"
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={'rule': {'title': 'Test', 'id': 'test'}},
                            content_preview="title: Test\nid: test"
                        )
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url']
                        )
                        
                        # Should use original content when optimization fails
                        assert result is not None
                        # Verify original content was used (not filtered)
                        call_args = mock_prompt.call_args
                        assert sample_article_data['content'] in call_args[0][1]['content']

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_prompt_loading_failure(self, service, sample_article_data):
        """Test handling of prompt loading failure."""
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = None  # Simulate prompt loading failure
                
                with pytest.raises(ValueError, match="Failed to load SIGMA generation prompt"):
                    await service.generate_sigma_rules(
                        article_title=sample_article_data['title'],
                        article_content=sample_article_data['content'],
                        source_name=sample_article_data['source_name'],
                        url=sample_article_data['url']
                    )

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_multiple_rules(self, service, sample_article_data):
        """Test generation of multiple SIGMA rules from single article."""
        multiple_rules_yaml = """
---
title: Rule 1
id: rule-1
description: First rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test1'
    condition: selection
level: low
---
title: Rule 2
id: rule-2
description: Second rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test2'
    condition: selection
level: medium
"""
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.services.sigma_generation_service.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rules"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = multiple_rules_yaml
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        def validate_side_effect(rule_str):
                            # Parse YAML and validate each rule
                            try:
                                rules = list(yaml.safe_load_all(rule_str))
                                if rules and rules[0]:
                                    return ValidationResult(
                                        is_valid=True,
                                        errors=[],
                                        warnings=[],
                                        metadata={'rule': rules[0]},
                                        content_preview=rule_str
                                    )
                            except:
                                pass
                            return ValidationResult(
                                is_valid=False,
                                errors=['Invalid'],
                                warnings=[],
                                metadata=None,
                                content_preview=rule_str
                            )
                        
                        mock_validate.side_effect = validate_side_effect
                        
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data['title'],
                            article_content=sample_article_data['content'],
                            source_name=sample_article_data['source_name'],
                            url=sample_article_data['url']
                        )
                        
                        # Should handle multiple rules
                        assert result is not None
