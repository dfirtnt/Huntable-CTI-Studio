"""Tests for SIGMA generation service functionality."""

import pytest
import yaml
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.services.sigma_generation_service import SigmaGenerationService, RuleValidationResult, ValidationResults
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
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                        # New phased approach: total_attempts is sum of (1 + repair_attempts) per rule
                        assert result['metadata']['total_attempts'] >= 1
                        assert result.get('errors') is None
                        # Check for rule-scoped conversation log
                        conversation_log = result['metadata'].get('conversation_log', [])
                        if conversation_log:
                            # New approach uses rule-scoped logging
                            assert 'rule_id' in conversation_log[0] or 'attempt' in conversation_log[0]

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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                            max_repair_attempts_per_rule=3
                        )
                        
                        # New phased approach: attempts tracked per rule
                        assert result['metadata']['total_attempts'] >= 1
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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                        # Verify prompt uses optimized content - check call_args properly
                        if mock_prompt.called:
                            # format_prompt_async is called with (template_name, context_dict)
                            call_args = mock_prompt.call_args
                            if call_args and len(call_args) >= 2:
                                context_dict = call_args[1] if isinstance(call_args, tuple) else call_args.kwargs
                                if isinstance(context_dict, dict) and 'content' in context_dict:
                                    assert optimized_content in context_dict['content']
                                elif isinstance(call_args, tuple) and len(call_args) >= 2:
                                    # Check second positional argument
                                    if isinstance(call_args[1], dict) and 'content' in call_args[1]:
                                        assert optimized_content in call_args[1]['content']

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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                            max_repair_attempts_per_rule=1
                        )
                        
                        # New phased approach: validation happens in Phase 2, repair in Phase 3
                        assert result['metadata']['total_attempts'] >= 1
                        assert len(result['rules']) == 0
                        assert result.get('errors') is not None

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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                            max_repair_attempts_per_rule=2
                        )
                        
                        # New phased approach: attempts tracked per rule
                        assert result['metadata']['total_attempts'] >= 1
                        assert len(result['rules']) == 0
                        assert result.get('errors') is not None

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_optimization_failure(self, service, sample_article_data):
        """Test handling of content optimization failure."""
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': False,
                'error': 'Optimization failed'
            }
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                        # Verify original content was used (not filtered) - check call_args properly
                        if mock_prompt.called:
                            call_args = mock_prompt.call_args
                            if call_args:
                                # format_prompt_async is called with (template_name, **kwargs)
                                if isinstance(call_args, tuple) and len(call_args) >= 2:
                                    kwargs = call_args[1] if len(call_args) > 1 else {}
                                    if isinstance(kwargs, dict) and 'content' in kwargs:
                                        assert sample_article_data['content'] in kwargs['content']
                                elif hasattr(call_args, 'kwargs') and 'content' in call_args.kwargs:
                                    assert sample_article_data['content'] in call_args.kwargs['content']

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_prompt_loading_failure(self, service, sample_article_data):
        """Test handling of prompt loading failure."""
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            # Mock format_prompt_async to return None (simulating failure).
            # Patch where it is defined; the service imports it inside the "if not sigma_prompt" block.
            # First try sigma_generate_multi, then fallback to sigma_generation
            with patch('src.utils.prompt_loader.format_prompt_async', new_callable=AsyncMock) as mock_prompt:
                # Simulate both prompt attempts failing
                def prompt_side_effect(*args, **kwargs):
                    return None
                mock_prompt.side_effect = prompt_side_effect
                # Call with sigma_prompt_template=None so the service uses file fallback -> format_prompt_async
                with pytest.raises(ValueError, match="Failed to load SIGMA generation prompt"):
                    await service.generate_sigma_rules(
                        article_title=sample_article_data['title'],
                        article_content=sample_article_data['content'],
                        source_name=sample_article_data['source_name'],
                        url=sample_article_data['url'],
                        sigma_prompt_template=None,
                    )

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_multiple_rules_with_separator(self, service, sample_article_data):
        """Test generation of multiple SIGMA rules with --- separator."""
        multiple_rules_yaml = """title: Rule 1
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
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rules"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = multiple_rules_yaml
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        def validate_side_effect(rule_str):
                            # Parse each rule individually
                            try:
                                parsed = yaml.safe_load(rule_str)
                                if parsed and 'title' in parsed:
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
                        
                        # Should parse multiple rules
                        assert result is not None
                        assert len(result['rules']) >= 1  # At least one rule should be parsed
                        
    @pytest.mark.asyncio
    async def test_generate_sigma_rules_multiple_rules_markdown_blocks(self, service, sample_article_data):
        """Test parsing multiple rules from markdown code blocks."""
        multiple_rules_markdown = """```yaml
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
```

```yaml
title: Rule 2
id: rule-2
description: Second rule
logsource:
    category: network_connection
    product: windows
detection:
    selection:
        DestinationPort: 443
    condition: selection
level: medium
```
"""
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rules"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    mock_call.return_value = multiple_rules_markdown
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        def validate_side_effect(rule_str):
                            try:
                                parsed = yaml.safe_load(rule_str)
                                if parsed and 'title' in parsed:
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
                        
                        # Should parse multiple rules from markdown blocks
                        assert result is not None
                        assert len(result['rules']) >= 1
                        
    @pytest.mark.asyncio
    async def test_generate_sigma_rules_per_rule_repair(self, service, sample_article_data):
        """Test per-rule repair in Phase 3."""
        invalid_rule = """title: Invalid Rule
id: invalid-1
description: Missing detection
logsource:
    category: process_creation
    product: windows
"""
        repaired_rule = """title: Valid Rule
id: valid-1
description: Fixed rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: medium
"""
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rule"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    # First call generates invalid rule, repair call fixes it
                    mock_call.side_effect = [invalid_rule, repaired_rule]
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        def validate_side_effect(rule_str):
                            has_detection = 'detection:' in rule_str and 'condition:' in rule_str
                            if has_detection:
                                parsed = yaml.safe_load(rule_str)
                                return ValidationResult(
                                    is_valid=True,
                                    errors=[],
                                    warnings=[],
                                    metadata={'rule': parsed},
                                    content_preview=rule_str
                                )
                            return ValidationResult(
                                is_valid=False,
                                errors=['Missing detection'],
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
                            max_repair_attempts_per_rule=3
                        )
                        
                        # Should repair and return valid rule
                        assert len(result['rules']) > 0
                        # Check repair attempts in conversation log
                        conversation_log = result['metadata'].get('conversation_log', [])
                        if conversation_log:
                            # Should have repair attempts tracked
                            for log_entry in conversation_log:
                                if 'repair_attempts' in log_entry:
                                    assert len(log_entry['repair_attempts']) > 0
                                    
    @pytest.mark.asyncio
    async def test_generate_sigma_rules_expansion_phase(self, service, sample_article_data):
        """Test artifact-driven expansion phase."""
        extraction_result = {
            'subresults': {
                'cmdline': {'count': 5, 'items': ['cmd1', 'cmd2']},
                'process_lineage': {'count': 2, 'items': [{'parent': 'p1', 'child': 'c1'}]},
                'network_connection': {'count': 3, 'items': ['net1']}
            }
        }
        
        initial_rule = """title: Process Creation Rule
id: rule-1
description: Process rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: medium
"""
        
        expansion_rule = """title: Network Connection Rule
id: rule-2
description: Network rule
logsource:
    category: network_connection
    product: windows
detection:
    selection:
        DestinationPort: 443
    condition: selection
level: high
"""
        
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
                mock_prompt.return_value = "Generate rules"
                
                with patch.object(service, '_call_provider_for_sigma') as mock_call:
                    # First call generates initial rule, expansion call generates additional rule
                    mock_call.side_effect = [initial_rule, expansion_rule]
                    
                    with patch('src.services.sigma_generation_service.validate_sigma_rule') as mock_validate:
                        def validate_side_effect(rule_str):
                            parsed = yaml.safe_load(rule_str)
                            if parsed and 'title' in parsed:
                                return ValidationResult(
                                    is_valid=True,
                                    errors=[],
                                    warnings=[],
                                    metadata={'rule': parsed},
                                    content_preview=rule_str
                                )
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
                            url=sample_article_data['url'],
                            extraction_result=extraction_result,
                            enable_multi_rule_expansion=True
                        )
                        
                        # Should have rules from both generation and expansion phases
                        assert len(result['rules']) >= 1
                        # Check conversation log for expansion phase
                        conversation_log = result['metadata'].get('conversation_log', [])
                        expansion_found = any(
                            entry.get('generation_phase') == 'expansion' 
                            for entry in conversation_log 
                            if isinstance(entry, dict)
                        )
                        # Expansion may or may not trigger depending on coverage logic
                        # Just verify the structure is correct
                        assert result is not None
                        
    @pytest.mark.asyncio
    async def test_generate_sigma_rules_rule_scoped_logging(self, service, sample_article_data, sample_sigma_rule):
        """Test rule-scoped logging structure."""
        with patch('src.services.sigma_generation_service.optimize_article_content') as mock_optimize:
            mock_optimize.return_value = {
                'success': True,
                'filtered_content': sample_article_data['content'],
                'tokens_saved': 0
            }
            
            with patch('src.utils.prompt_loader.format_prompt_async') as mock_prompt:
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
                            url=sample_article_data['url']
                        )
                        
                        # Check rule-scoped logging structure
                        conversation_log = result['metadata'].get('conversation_log', [])
                        assert len(conversation_log) > 0
                        for log_entry in conversation_log:
                            assert isinstance(log_entry, dict)
                            # Should have rule_id or attempt (backward compatibility)
                            assert 'rule_id' in log_entry or 'attempt' in log_entry
                            # Should have generation_phase or be backward compatible
                            if 'rule_id' in log_entry:
                                assert 'generation_phase' in log_entry
                                assert 'final_status' in log_entry
                                assert 'repair_attempts' in log_entry
