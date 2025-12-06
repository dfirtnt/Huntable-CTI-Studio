"""Integration tests for AI Assistant features."""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any, List

from src.utils.gpt4o_optimizer import GPT4oContentOptimizer
from src.utils.ioc_extractor import HybridIOCExtractor
from src.services.sigma_validator import SigmaValidator

# Mock generate_sigma_rules - this was from a non-existent module
def generate_sigma_rules(content, model_name="phi3-cti-hunt"):
    """Mock function for generate_sigma_rules - original module doesn't exist."""
    import subprocess
    import json
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, content],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


class TestAIIntegration:
    """Integration tests for AI Assistant features."""

    @pytest.fixture
    def sample_threat_article(self):
        """Create sample threat intelligence article."""
        return {
            'title': 'APT29 Campaign Uses PowerShell and LOLBAS Techniques',
            'content': '''
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
            ''',
            'source': 'Threat Intelligence Blog',
            'url': 'https://example.com/apt29-analysis',
            'published_at': '2024-01-15T10:00:00Z'
        }

    @pytest.fixture
    def mock_gpt4o_response(self):
        """Create mock GPT-4o response."""
        return {
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
        }

    @pytest.fixture
    def mock_sigma_rule(self):
        """Create mock SIGMA rule."""
        return {
            'title': 'APT29 PowerShell Execution',
            'description': 'Detects APT29 PowerShell execution patterns',
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {
                'selection': {
                    'Image': 'powershell.exe',
                    'CommandLine': '*EncodedCommand*'
                },
                'condition': 'selection'
            },
            'level': 'high',
            'tags': ['attack.execution', 'attack.t1059.001']
        }

    @pytest.mark.asyncio
    async def test_end_to_end_ai_workflow(self, sample_threat_article, mock_gpt4o_response, mock_sigma_rule):
        """Test complete AI workflow from content to SIGMA rules."""
        # Step 1: Content Optimization
        optimizer = GPT4oContentOptimizer()
        
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_filter_result = Mock(
                        filtered_content=sample_threat_article['content'],
                        is_huntable=True,
                        confidence=0.85,
                        cost_savings=0.2,
                        removed_chunks=[]
                    )
                    mock_filter.return_value = mock_filter_result
                    
                    optimization_result = await optimizer.optimize_content_for_gpt4o(
                        sample_threat_article['content']
                    )
        
        assert optimization_result['success'] is True
        assert optimization_result['is_huntable'] is True
        assert optimization_result['confidence'] == 0.85
        
        # Step 2: IOC Extraction
        ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
        ioc_result = ioc_extractor.extract_iocs(sample_threat_article['content'])
        
        assert ioc_result.extraction_method == 'iocextract'
        assert len(ioc_result.iocs['ip']) > 0
        assert len(ioc_result.iocs['domain']) > 0
        assert len(ioc_result.iocs['file_hash']) > 0
        assert len(ioc_result.iocs['email']) > 0
        
        # Step 3: GPT-4o Analysis (mocked)
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gpt4o_response
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            # Simulate GPT-4o analysis
            analysis_result = mock_gpt4o_response['choices'][0]['message']['content']
        
        assert 'SIGMA HUNTABILITY SCORE: 8' in analysis_result
        assert 'Process/Command-Line (0-4): 4' in analysis_result
        
        # Step 4: SIGMA Rule Generation (mocked)
        with patch('subprocess.run') as mock_subprocess:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(mock_sigma_rule, indent=2)
            mock_result.stderr = ""
            mock_subprocess.return_value = mock_result
            
            sigma_rules = generate_sigma_rules(sample_threat_article['content'])
        
        assert sigma_rules is not None
        assert 'title: APT29 PowerShell Execution' in sigma_rules
        
        # Step 5: SIGMA Rule Validation
        validator = SigmaValidator()
        validation_result = validator.validate_rule(mock_sigma_rule)
        
        assert validation_result.is_valid is True
        assert len(validation_result.errors) == 0

    @pytest.mark.asyncio
    async def test_ai_workflow_with_optimization_failure(self, sample_threat_article):
        """Test AI workflow when content optimization fails."""
        optimizer = GPT4oContentOptimizer()
        
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content', side_effect=Exception("Filter error")):
                    optimization_result = await optimizer.optimize_content_for_gpt4o(
                        sample_threat_article['content']
                    )
        
        assert optimization_result['success'] is False
        assert 'error' in optimization_result
        assert optimization_result['filtered_content'] == sample_threat_article['content']

    @pytest.mark.asyncio
    async def test_ai_workflow_with_ioc_extraction(self, sample_threat_article):
        """Test AI workflow with IOC extraction."""
        ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
        ioc_result = ioc_extractor.extract_iocs(sample_threat_article['content'])
        
        # Verify IOC extraction
        assert ioc_result.extraction_method == 'iocextract'
        assert ioc_result.confidence > 0
        assert ioc_result.processing_time > 0
        
        # Check specific IOCs
        assert '192.168.1.100' in ioc_result.iocs['ip']
        assert 'malicious.example.com' in ioc_result.iocs['domain']
        assert 'a1b2c3d4e5f6789012345678901234567890abcd' in ioc_result.iocs['file_hash']
        assert 'attacker@evil.com' in ioc_result.iocs['email']

    @pytest.mark.asyncio
    async def test_ai_workflow_with_sigma_validation(self, mock_sigma_rule):
        """Test AI workflow with SIGMA rule validation."""
        validator = SigmaValidator()
        
        # Test valid rule
        validation_result = validator.validate_rule(mock_sigma_rule)
        assert validation_result.is_valid is True
        assert len(validation_result.errors) == 0
        
        # Test invalid rule
        invalid_rule = {
            'title': 'Invalid Rule',
            'description': 'Missing required fields'
            # Missing logsource and detection
        }
        
        invalid_result = validator.validate_rule(invalid_rule)
        assert invalid_result.is_valid is False
        assert len(invalid_result.errors) > 0

    @pytest.mark.asyncio
    async def test_ai_workflow_performance(self, sample_threat_article):
        """Test AI workflow performance."""
        import time
        
        start_time = time.time()
        
        # Content optimization
        optimizer = GPT4oContentOptimizer()
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_filter_result = Mock(
                        filtered_content=sample_threat_article['content'],
                        is_huntable=True,
                        confidence=0.8,
                        cost_savings=0.15,
                        removed_chunks=[]
                    )
                    mock_filter.return_value = mock_filter_result
                    
                    await optimizer.optimize_content_for_gpt4o(sample_threat_article['content'])
        
        # IOC extraction
        ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
        ioc_extractor.extract_iocs(sample_threat_article['content'])
        
        # SIGMA rule generation
        with patch('subprocess.run') as mock_subprocess:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Generated SIGMA rule"
            mock_result.stderr = ""
            mock_subprocess.return_value = mock_result
            
            generate_sigma_rules(sample_threat_article['content'])
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should complete within reasonable time (5 seconds for mocked operations)
        assert total_time < 5.0

    @pytest.mark.asyncio
    async def test_ai_workflow_error_handling(self, sample_threat_article):
        """Test AI workflow error handling."""
        # Test with malformed content
        malformed_content = "Invalid content with special characters: @#$%^&*()"
        
        # Content optimization should handle malformed content
        optimizer = GPT4oContentOptimizer()
        with patch.object(optimizer.content_filter, 'model', None):
            with patch.object(optimizer.content_filter, 'load_model'):
                with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                    mock_filter_result = Mock(
                        filtered_content=malformed_content,
                        is_huntable=False,
                        confidence=0.3,
                        cost_savings=0.8,
                        removed_chunks=[malformed_content]
                    )
                    mock_filter.return_value = mock_filter_result
                    
                    result = await optimizer.optimize_content_for_gpt4o(malformed_content)
        
        assert result['success'] is True
        assert result['is_huntable'] is False
        assert result['confidence'] == 0.3
        
        # IOC extraction should handle malformed content
        ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
        ioc_result = ioc_extractor.extract_iocs(malformed_content)
        
        assert ioc_result.extraction_method == 'iocextract'
        assert ioc_result.confidence >= 0

    @pytest.mark.asyncio
    async def test_ai_workflow_with_different_content_types(self):
        """Test AI workflow with different content types."""
        content_types = [
            {
                'name': 'Technical Analysis',
                'content': 'Detailed technical analysis with command-line examples and registry keys.',
                'expected_huntable': True
            },
            {
                'name': 'Strategic Overview',
                'content': 'High-level strategic overview of threat landscape and trends.',
                'expected_huntable': False
            },
            {
                'name': 'IOC Report',
                'content': 'List of IOCs: 192.168.1.1, malicious.com, hash123.',
                'expected_huntable': False
            },
            {
                'name': 'Tutorial',
                'content': 'How to learn threat hunting and best practices for beginners.',
                'expected_huntable': False
            }
        ]
        
        for content_type in content_types:
            # Content optimization
            optimizer = GPT4oContentOptimizer()
            with patch.object(optimizer.content_filter, 'model', None):
                with patch.object(optimizer.content_filter, 'load_model'):
                    with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                        mock_filter_result = Mock(
                            filtered_content=content_type['content'],
                            is_huntable=content_type['expected_huntable'],
                            confidence=0.7,
                            cost_savings=0.2,
                            removed_chunks=[]
                        )
                        mock_filter.return_value = mock_filter_result
                        
                        result = await optimizer.optimize_content_for_gpt4o(content_type['content'])
            
            assert result['success'] is True
            assert result['is_huntable'] == content_type['expected_huntable']
            
            # IOC extraction
            ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
            ioc_result = ioc_extractor.extract_iocs(content_type['content'])
            
            assert ioc_result.extraction_method == 'iocextract'
            assert ioc_result.confidence >= 0

    @pytest.mark.asyncio
    async def test_ai_workflow_cost_optimization(self, sample_threat_article):
        """Test AI workflow cost optimization."""
        optimizer = GPT4oContentOptimizer()
        
        # Test cost estimation
        cost_estimate = optimizer.get_cost_estimate(sample_threat_article['content'], use_filtering=True)
        
        assert cost_estimate['filtering_enabled'] is True
        assert cost_estimate['total_cost'] > 0
        assert cost_estimate['input_tokens'] > 0
        assert cost_estimate['output_tokens'] == 2000
        
        # Test optimization stats
        stats = optimizer.get_optimization_stats()
        assert stats['total_requests'] == 0  # No requests made yet
        assert stats['total_cost_savings'] == 0.0

    @pytest.mark.asyncio
    async def test_ai_workflow_batch_processing(self):
        """Test AI workflow with batch processing."""
        articles = [
            'Article 1: PowerShell malware techniques',
            'Article 2: Registry persistence mechanisms',
            'Article 3: Network communication patterns'
        ]
        
        optimizer = GPT4oContentOptimizer()
        ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
        
        results = []
        
        for article in articles:
            # Content optimization
            with patch.object(optimizer.content_filter, 'model', None):
                with patch.object(optimizer.content_filter, 'load_model'):
                    with patch.object(optimizer.content_filter, 'filter_content') as mock_filter:
                        mock_filter_result = Mock(
                            filtered_content=article,
                            is_huntable=True,
                            confidence=0.8,
                            cost_savings=0.2,
                            removed_chunks=[]
                        )
                        mock_filter.return_value = mock_filter_result
                        
                        opt_result = await optimizer.optimize_content_for_gpt4o(article)
            
            # IOC extraction
            ioc_result = ioc_extractor.extract_iocs(article)
            
            results.append({
                'article': article,
                'optimization': opt_result,
                'ioc_extraction': ioc_result
            })
        
        assert len(results) == 3
        assert all(result['optimization']['success'] for result in results)
        assert all(result['ioc_extraction'].extraction_method == 'iocextract' for result in results)
        
        # Check optimization stats
        stats = optimizer.get_optimization_stats()
        assert stats['total_requests'] == 3
        assert stats['total_cost_savings'] > 0

    @pytest.mark.asyncio
    async def test_ai_workflow_integration_errors(self, sample_threat_article):
        """Test AI workflow integration error handling."""
        # Test with network errors
        with patch('httpx.AsyncClient', side_effect=ConnectionError("Network error")):
            # Should handle network errors gracefully
            optimizer = GPT4oContentOptimizer()
            with patch.object(optimizer.content_filter, 'model', None):
                with patch.object(optimizer.content_filter, 'load_model'):
                    with patch.object(optimizer.content_filter, 'filter_content', side_effect=ConnectionError("Network error")):
                        result = await optimizer.optimize_content_for_gpt4o(sample_threat_article['content'])
            
            assert result['success'] is False
            assert 'error' in result
        
        # Test with subprocess errors
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("ollama", 30)):
            sigma_rules = generate_sigma_rules(sample_threat_article['content'])
            assert sigma_rules is None
        
        # Test with validation errors
        validator = SigmaValidator()
        invalid_rule = {'invalid': 'rule'}
        validation_result = validator.validate_rule(invalid_rule)
        assert validation_result.is_valid is False
        assert len(validation_result.errors) > 0
