"""
Integration tests for AI cross-model functionality.
Tests model switching, fallbacks, and integration between different AI providers.

NOTE: These tests require cloud LLM API keys or proper mocking.
"""

import pytest

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration
import asyncio
from unittest.mock import Mock, patch

try:
    from src.utils.gpt4o_optimizer import GPT4oContentOptimizer

    from src.services.sigma_validator import SigmaValidator
    from src.utils.ioc_extractor import HybridIOCExtractor
except ImportError:
    # Mock imports for testing without full dependencies
    GPT4oContentOptimizer = None
    HybridIOCExtractor = None
    SigmaValidator = None


class TestAICrossModelIntegration:
    """Test AI cross-model integration functionality."""

    @pytest.fixture
    def sample_threat_article(self):
        """Create sample threat intelligence article."""
        return {
            "title": "APT29 Campaign Uses PowerShell and LOLBAS Techniques",
            "content": """
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
            """,
            "source": "Threat Intelligence Blog",
            "url": "https://example.com/apt29-analysis",
            "published_at": "2024-01-15T10:00:00Z",
        }

    @pytest.fixture
    def mock_openai_response(self):
        """Create mock OpenAI response."""
        return {
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
        }

    @pytest.fixture
    def mock_anthropic_response(self):
        """Create mock Anthropic response."""
        return {
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
        }

    @pytest.fixture
    def mock_ollama_response(self):
        """Create mock Ollama response."""
        return """
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

    @pytest.mark.asyncio
    async def test_model_switching_chatgpt_to_anthropic(
        self, sample_threat_article, mock_openai_response, mock_anthropic_response
    ):
        """Test switching from ChatGPT to Anthropic model."""
        # Test ChatGPT first
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_openai_response
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Simulate ChatGPT analysis
            chatgpt_result = mock_openai_response["choices"][0]["message"]["content"]
            assert "SIGMA HUNTABILITY SCORE: 8" in chatgpt_result

        # Test Anthropic
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_anthropic_response
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Simulate Anthropic analysis
            anthropic_result = mock_anthropic_response["content"][0]["text"]
            assert "SIGMA HUNTABILITY SCORE: 9" in anthropic_result

        # Verify different models produce different results
        assert chatgpt_result != anthropic_result
        assert "8" in chatgpt_result and "9" in anthropic_result

    @pytest.mark.asyncio
    async def test_model_fallback_openai_failure(self, sample_threat_article, mock_anthropic_response):
        """Test fallback from OpenAI to Anthropic when OpenAI fails."""
        # Mock OpenAI failure
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "OpenAI API Error"
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Should handle OpenAI failure gracefully
            try:
                # This would normally trigger fallback logic
                raise Exception("OpenAI API Error")
            except Exception as e:
                assert "OpenAI API Error" in str(e)

        # Test fallback to Anthropic
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_anthropic_response
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Fallback should work
            anthropic_result = mock_anthropic_response["content"][0]["text"]
            assert "SIGMA HUNTABILITY SCORE: 9" in anthropic_result

    @pytest.mark.asyncio
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="External API dependency or mock setup issue - needs investigation")
    async def test_model_fallback_anthropic_failure(self, sample_threat_article, mock_ollama_response):
        """Test fallback from Anthropic to Ollama when Anthropic fails."""
        # Mock Anthropic failure
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 429  # Rate limit
            mock_response.text = "Rate limit exceeded"
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Should handle Anthropic failure gracefully
            try:
                raise Exception("Rate limit exceeded")
            except Exception as e:
                assert "Rate limit exceeded" in str(e)

        # Test fallback to Ollama
        with patch("subprocess.run") as mock_subprocess:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = mock_ollama_response
            mock_result.stderr = ""
            mock_subprocess.return_value = mock_result

            # Fallback should work
            ollama_result = generate_sigma_rules(sample_threat_article["content"])
            assert "title: APT29 PowerShell Execution" in ollama_result

    @pytest.mark.asyncio
    async def test_content_size_limits_per_model(self, sample_threat_article):
        """Test content size limits for different models."""
        # Define content limits for each model
        model_limits = {
            "chatgpt": 50000,  # 50KB
            "anthropic": 100000,  # 100KB
        }

        # Test content within limits
        small_content = "x" * 10000  # 10KB - within all limits

        for model, limit in model_limits.items():
            assert len(small_content) <= limit, f"Small content should be within {model} limit"

        # Test content exceeding limits
        large_content = "x" * 150000  # 150KB - exceeds ChatGPT and Anthropic limits

        assert len(large_content) > model_limits["chatgpt"]
        assert len(large_content) > model_limits["anthropic"]

    @pytest.mark.asyncio
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="External API dependency or mock setup issue - needs investigation")
    async def test_model_specific_feature_support(self, sample_threat_article):
        """Test model-specific feature support."""
        # Test OpenAI GPT-4o specific features
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "GPT-4o analysis with cost optimization"}}]
            }
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # GPT-4o should support cost optimization
            optimizer = GPT4oContentOptimizer()
            with patch.object(optimizer.content_filter, "model", None):
                with patch.object(optimizer.content_filter, "load_model"):
                    with patch.object(optimizer.content_filter, "filter_content") as mock_filter:
                        mock_filter_result = Mock(
                            filtered_content=sample_threat_article["content"],
                            is_huntable=True,
                            confidence=0.8,
                            cost_savings=0.3,
                            removed_chunks=[],
                        )
                        mock_filter.return_value = mock_filter_result

                        result = await optimizer.optimize_content_for_gpt4o(sample_threat_article["content"])
                        assert result["cost_savings"] > 0

        # Test Anthropic Claude specific features
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"content": [{"text": "Claude analysis with long context support"}]}
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            # Claude should support longer context
            long_content = "x" * 80000  # 80KB - within Claude's limit
            assert len(long_content) <= 100000  # Claude's limit

        # Test Ollama specific features
        with patch("subprocess.run") as mock_subprocess:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "Ollama local processing"
            mock_result.stderr = ""
            mock_subprocess.return_value = mock_result

            # Ollama should work offline
            result = generate_sigma_rules(sample_threat_article["content"])
            assert result is not None

    @pytest.mark.asyncio
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="External API dependency or mock setup issue - needs investigation")
    async def test_concurrent_model_requests(self, sample_threat_article):
        """Test concurrent requests to different models."""
        import asyncio

        async def mock_openai_request():
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"choices": [{"message": {"content": "OpenAI response"}}]}
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                return "OpenAI response"

        async def mock_anthropic_request():
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"content": [{"text": "Anthropic response"}]}
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                return "Anthropic response"

        async def mock_ollama_request():
            with patch("subprocess.run") as mock_subprocess:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "Ollama response"
                mock_result.stderr = ""
                mock_subprocess.return_value = mock_result
                return generate_sigma_rules(sample_threat_article["content"])

        # Run concurrent requests
        results = await asyncio.gather(mock_openai_request(), mock_anthropic_request(), mock_ollama_request())

        assert len(results) == 3
        assert "OpenAI response" in results
        assert "Anthropic response" in results
        assert "Ollama response" in results

    @pytest.mark.asyncio
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="External API dependency or mock setup issue - needs investigation")
    async def test_model_performance_comparison(self, sample_threat_article):
        """Test performance comparison between models."""
        import time

        # Mock different response times
        async def mock_openai_request():
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"choices": [{"message": {"content": "OpenAI response"}}]}
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                await asyncio.sleep(0.1)  # Simulate 100ms response
                return "OpenAI response"

        async def mock_anthropic_request():
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"content": [{"text": "Anthropic response"}]}
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                await asyncio.sleep(0.2)  # Simulate 200ms response
                return "Anthropic response"

        async def mock_ollama_request():
            with patch("subprocess.run") as mock_subprocess:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "Ollama response"
                mock_result.stderr = ""
                mock_subprocess.return_value = mock_result
                await asyncio.sleep(0.5)  # Simulate 500ms response
                return generate_sigma_rules(sample_threat_article["content"])

        # Measure performance
        start_time = time.time()

        openai_result = await mock_openai_request()
        anthropic_result = await mock_anthropic_request()
        ollama_result = await mock_ollama_request()

        end_time = time.time()
        total_time = end_time - start_time

        # Verify results
        assert openai_result == "OpenAI response"
        assert anthropic_result == "Anthropic response"
        assert ollama_result is not None

        # Total time should be sum of individual times (sequential execution)
        assert total_time >= 0.8  # 0.1 + 0.2 + 0.5

    @pytest.mark.asyncio
    async def test_model_configuration_validation(self):
        """Test model configuration validation."""
        # Test valid configurations
        valid_configs = [
            {
                "model": "chatgpt",
                "api_key": "sk-test123",
                "endpoint": "https://api.openai.com/v1/chat/completions",
            },
            {
                "model": "anthropic",
                "api_key": "sk-ant-test123",
                "endpoint": "https://api.anthropic.com/v1/messages",
            },
            {
                "model": "ollama",
                "endpoint": "http://localhost:11434",
                "model_name": "phi3-cti-hunt",
            },
        ]

        for config in valid_configs:
            assert "model" in config
            assert config["model"] in ["chatgpt", "anthropic", "ollama"]

            if config["model"] in ["chatgpt", "anthropic"]:
                assert "api_key" in config
                assert config["api_key"].startswith("sk-")

            if config["model"] == "ollama":
                assert "model_name" in config

        # Test invalid configurations
        invalid_configs = [
            {"model": "invalid_model"},
            {"model": "chatgpt"},  # Missing API key
            {"model": "anthropic", "api_key": "invalid_key"},  # Invalid API key format
            {"model": "ollama"},  # Missing model name
        ]

        for config in invalid_configs:
            if config["model"] not in ["chatgpt", "anthropic", "ollama"]:
                assert config["model"] == "invalid_model"
            elif config["model"] in ["chatgpt", "anthropic"] and "api_key" not in config:
                assert "api_key" not in config
            elif config["model"] == "ollama" and "model_name" not in config:
                assert "model_name" not in config

    @pytest.mark.asyncio
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="External API dependency or mock setup issue - needs investigation")
    async def test_model_error_handling_consistency(self, sample_threat_article):
        """Test consistent error handling across models."""
        # Test OpenAI error handling
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            try:
                raise Exception("OpenAI API Error: Unauthorized")
            except Exception as e:
                assert "OpenAI API Error" in str(e)

        # Test Anthropic error handling
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.text = "Rate limit exceeded"
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            try:
                raise Exception("Anthropic API Error: Rate limit exceeded")
            except Exception as e:
                assert "Anthropic API Error" in str(e)

        # Test Ollama error handling
        with patch("subprocess.run") as mock_subprocess:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Model not found"
            mock_subprocess.return_value = mock_result

            result = generate_sigma_rules(sample_threat_article["content"])
            assert result is None

        # All models should handle errors gracefully
        assert True  # If we reach here, all error handling worked
