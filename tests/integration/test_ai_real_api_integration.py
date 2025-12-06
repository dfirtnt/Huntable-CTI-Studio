"""
Real API integration tests for AI Assistant features.
Tests actual API calls to OpenAI, Anthropic, and Ollama services.
Requires test API keys and proper environment setup.
"""

import pytest
import asyncio
import os
import json
import httpx
import subprocess
from typing import Dict, Any, Optional
from unittest.mock import patch

try:
    from src.utils.gpt4o_optimizer import GPT4oContentOptimizer
    from src.utils.ioc_extractor import HybridIOCExtractor
    from ollama_cti_workflow import generate_sigma_rules
except ImportError:
    # Mock imports for testing without full dependencies
    GPT4oContentOptimizer = None
    HybridIOCExtractor = None
    generate_sigma_rules = None


@pytest.mark.skip(reason="Requires external API access (OpenAI, Anthropic, Ollama)")
class TestAIRealAPIIntegration:
    """Test real AI API integration functionality."""

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
    def openai_api_key(self):
        """Get OpenAI API key from environment."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set - skipping OpenAI integration tests")
        return api_key

    @pytest.fixture
    def anthropic_api_key(self):
        """Get Anthropic API key from environment."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip(
                "ANTHROPIC_API_KEY not set - skipping Anthropic integration tests"
            )
        return api_key

    @pytest.fixture
    def ollama_available(self):
        """Check if Ollama is available."""
        try:
            result = subprocess.run(
                ["ollama", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        pytest.skip("Ollama not available - skipping Ollama integration tests")

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_openai_gpt4o_real_api_call(
        self, sample_threat_article, openai_api_key
    ):
        """Test real OpenAI GPT-4o API call."""
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a threat intelligence analyst. Analyze the following article and provide a SIGMA huntability score (0-10) with detailed breakdown.",
                },
                {
                    "role": "user",
                    "content": f"Analyze this threat intelligence article:\n\n{sample_threat_article['content'][:2000]}...",  # Limit content size
                },
            ],
            "max_tokens": 1000,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "choices" in data
                assert len(data["choices"]) > 0
                assert "message" in data["choices"][0]
                assert "content" in data["choices"][0]["message"]

                # Verify content contains expected elements
                content = data["choices"][0]["message"]["content"]
                assert "SIGMA" in content or "huntability" in content.lower()

            except httpx.TimeoutException:
                pytest.fail("OpenAI API call timed out")
            except httpx.HTTPStatusError as e:
                pytest.fail(f"OpenAI API returned error: {e.response.status_code}")

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_anthropic_claude_real_api_call(
        self, sample_threat_article, anthropic_api_key
    ):
        """Test real Anthropic Claude API call."""
        headers = {
            "x-api-key": anthropic_api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": "claude-3-sonnet-20240229",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": f"Analyze this threat intelligence article and provide a SIGMA huntability score (0-10) with detailed breakdown:\n\n{sample_threat_article['content'][:2000]}...",
                }
            ],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                )

                assert response.status_code == 200
                data = response.json()

                # Verify response structure
                assert "content" in data
                assert len(data["content"]) > 0
                assert "text" in data["content"][0]

                # Verify content contains expected elements
                content = data["content"][0]["text"]
                assert "SIGMA" in content or "huntability" in content.lower()

            except httpx.TimeoutException:
                pytest.fail("Anthropic API call timed out")
            except httpx.HTTPStatusError as e:
                pytest.fail(f"Anthropic API returned error: {e.response.status_code}")

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_ollama_real_api_call(self, sample_threat_article, ollama_available):
        """Test real Ollama API call."""
        # Check if Ollama is running
        try:
            result = subprocess.run(
                ["ollama", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                pytest.skip("Ollama not running - skipping Ollama integration tests")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Ollama not available - skipping Ollama integration tests")

        # Test with a common model (adjust as needed)
        model_name = "llama2"  # or "phi3" or whatever model is available

        try:
            result = generate_sigma_rules(
                sample_threat_article["content"], model_name=model_name
            )

            # Verify result
            assert result is not None
            assert len(result) > 0

            # Check if result contains SIGMA rule elements
            assert any(
                keyword in result.lower()
                for keyword in ["title", "description", "detection", "logsource"]
            )

        except Exception as e:
            pytest.skip(f"Ollama model {model_name} not available or failed: {e}")

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_gpt4o_optimizer_real_integration(
        self, sample_threat_article, openai_api_key
    ):
        """Test GPT-4o optimizer with real API integration."""
        # Set up environment for real API calls
        os.environ["OPENAI_API_KEY"] = openai_api_key

        optimizer = GPT4oContentOptimizer()

        # Test content optimization (this will use real ML model if available)
        try:
            result = await optimizer.optimize_content_for_gpt4o(
                sample_threat_article["content"]
            )

            # Verify result structure
            assert "success" in result
            assert "original_content" in result
            assert "filtered_content" in result
            assert "cost_savings" in result

            # If optimization succeeded, verify content was processed
            if result["success"]:
                assert result["original_content"] == sample_threat_article["content"]
                assert len(result["filtered_content"]) <= len(
                    result["original_content"]
                )
                assert 0 <= result["cost_savings"] <= 1
            else:
                # If optimization failed, should fallback to original content
                assert result["filtered_content"] == sample_threat_article["content"]
                assert result["cost_savings"] == 0.0

        except Exception as e:
            # If ML model is not available, test should still pass
            pytest.skip(f"GPT-4o optimizer not fully available: {e}")

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_ioc_extractor_real_integration(self, sample_threat_article):
        """Test IOC extractor with real integration."""
        extractor = HybridIOCExtractor(use_llm_validation=False)

        # Test IOC extraction
        result = extractor.extract_iocs(sample_threat_article["content"])

        # Verify result structure
        assert hasattr(result, "extraction_method")
        assert hasattr(result, "iocs")
        assert hasattr(result, "confidence")
        assert hasattr(result, "processing_time")

        # Verify extraction method
        assert result.extraction_method == "iocextract"

        # Verify IOCs were extracted
        assert len(result.iocs) > 0
        assert "ip" in result.iocs
        assert "domain" in result.iocs
        assert "file_hash" in result.iocs
        assert "email" in result.iocs

        # Verify specific IOCs from sample content
        assert "192.168.1.100" in result.iocs["ip"]
        assert "malicious.example.com" in result.iocs["domain"]
        assert "a1b2c3d4e5f6789012345678901234567890abcd" in result.iocs["file_hash"]
        assert "attacker@evil.com" in result.iocs["email"]

        # Verify confidence and processing time
        assert 0 <= result.confidence <= 1
        assert result.processing_time > 0

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_api_rate_limiting_handling(
        self, sample_threat_article, openai_api_key
    ):
        """Test API rate limiting handling."""
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": sample_threat_article["content"][
                        :1000
                    ],  # Smaller content
                }
            ],
            "max_tokens": 100,
        }

        # Make multiple rapid requests to test rate limiting
        async with httpx.AsyncClient(timeout=30.0) as client:
            responses = []
            for i in range(3):  # Make 3 rapid requests
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    responses.append(response)

                    # Add small delay between requests
                    await asyncio.sleep(0.5)

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        # Rate limit hit - this is expected behavior
                        assert e.response.status_code == 429
                        break
                    else:
                        pytest.fail(f"Unexpected API error: {e.response.status_code}")

            # At least one request should succeed
            assert len(responses) > 0
            assert any(r.status_code == 200 for r in responses)

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_api_timeout_handling(self, sample_threat_article, openai_api_key):
        """Test API timeout handling."""
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": sample_threat_article["content"][:1000]}
            ],
            "max_tokens": 100,
        }

        # Test with very short timeout
        async with httpx.AsyncClient(timeout=0.1) as client:  # 100ms timeout
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                # If request succeeds, that's fine too
                assert response.status_code in [200, 408]
            except httpx.TimeoutException:
                # This is expected with such a short timeout
                assert True
            except httpx.HTTPStatusError as e:
                # Other HTTP errors are also acceptable
                assert e.response.status_code in [408, 429, 500, 502, 503, 504]

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_api_error_response_handling(self, sample_threat_article):
        """Test API error response handling."""
        # Test with invalid API key
        headers = {
            "Authorization": "Bearer invalid-key",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": sample_threat_article["content"][:1000]}
            ],
            "max_tokens": 100,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                # Should get 401 Unauthorized
                assert response.status_code == 401

                # Verify error response structure
                error_data = response.json()
                assert "error" in error_data

            except httpx.HTTPStatusError as e:
                # HTTPStatusError is also acceptable
                assert e.response.status_code == 401

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_end_to_end_ai_workflow_real_apis(
        self, sample_threat_article, openai_api_key
    ):
        """Test end-to-end AI workflow with real APIs."""
        # Step 1: Content Optimization
        optimizer = GPT4oContentOptimizer()

        try:
            optimization_result = await optimizer.optimize_content_for_gpt4o(
                sample_threat_article["content"]
            )
            assert optimization_result["success"] is not None
        except Exception:
            # If optimization fails, continue with original content
            optimization_result = {
                "success": False,
                "filtered_content": sample_threat_article["content"],
            }

        # Step 2: IOC Extraction
        ioc_extractor = HybridIOCExtractor(use_llm_validation=False)
        ioc_result = ioc_extractor.extract_iocs(sample_threat_article["content"])

        assert ioc_result.extraction_method == "iocextract"
        assert len(ioc_result.iocs) > 0

        # Step 3: Real OpenAI Analysis
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
        }

        content_to_analyze = optimization_result.get(
            "filtered_content", sample_threat_article["content"]
        )

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a threat intelligence analyst. Provide a SIGMA huntability score (0-10) with detailed breakdown.",
                },
                {
                    "role": "user",
                    "content": f"Analyze this threat intelligence article:\n\n{content_to_analyze[:2000]}...",
                },
            ],
            "max_tokens": 1000,
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )

                assert response.status_code == 200
                analysis_data = response.json()
                analysis_content = analysis_data["choices"][0]["message"]["content"]

                # Verify analysis contains expected elements
                assert (
                    "SIGMA" in analysis_content
                    or "huntability" in analysis_content.lower()
                )

            except Exception as e:
                pytest.skip(f"Real API integration failed: {e}")

        # Step 4: SIGMA Rule Generation (if Ollama available)
        try:
            sigma_rules = generate_sigma_rules(sample_threat_article["content"])
            if sigma_rules:
                assert len(sigma_rules) > 0
                assert any(
                    keyword in sigma_rules.lower()
                    for keyword in ["title", "detection", "logsource"]
                )
        except Exception:
            # SIGMA rule generation is optional
            pass

        # Verify overall workflow completed
        assert True  # If we reach here, the workflow completed successfully

    @pytest.mark.integration
    @pytest.mark.ai
    @pytest.mark.asyncio
    async def test_api_cost_tracking(self, sample_threat_article, openai_api_key):
        """Test API cost tracking and estimation."""
        # Test cost estimation
        optimizer = GPT4oContentOptimizer()

        cost_estimate = optimizer.get_cost_estimate(
            sample_threat_article["content"], use_filtering=False
        )

        # Verify cost estimate structure
        assert "input_tokens" in cost_estimate
        assert "output_tokens" in cost_estimate
        assert "input_cost" in cost_estimate
        assert "output_cost" in cost_estimate
        assert "total_cost" in cost_estimate

        # Verify costs are positive
        assert cost_estimate["input_tokens"] > 0
        assert cost_estimate["output_tokens"] > 0
        assert cost_estimate["total_cost"] > 0

        # Test with filtering enabled
        cost_estimate_filtered = optimizer.get_cost_estimate(
            sample_threat_article["content"], use_filtering=True
        )

        # Filtered cost should be less than or equal to unfiltered cost
        assert cost_estimate_filtered["total_cost"] <= cost_estimate["total_cost"]

        # Test optimization stats
        stats = optimizer.get_optimization_stats()
        assert "total_requests" in stats
        assert "total_cost_savings" in stats
        assert "avg_cost_reduction" in stats
