"""
LLM Service for Deepseek-R1 integration via LMStudio.

Provides LLM-based ranking and extraction for agentic workflow.
"""

import os
import logging
import httpx
import json
import re
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# LM Studio context limits (default to 4096 if not configured properly)
MAX_CONTEXT_TOKENS = int(os.getenv("LMSTUDIO_MAX_CONTEXT", "4096"))
PROMPT_OVERHEAD_TOKENS = 500  # Reserve for prompt templates, system messages, etc.


class LLMService:
    """Service for LLM API calls using Deepseek-R1 via LMStudio."""
    
    def __init__(self):
        """Initialize LLM service with LMStudio configuration."""
        self.lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        self.lmstudio_model = os.getenv("LMSTUDIO_MODEL", "deepseek-r1-qwen3-8b")
        
        # Recommended settings for Deepseek-R1
        self.temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.15"))
        self.top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
        self.seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None
        
        logger.info(f"Initialized LLMService with model: {self.lmstudio_model}")
    
    @staticmethod
    def _read_file_sync(file_path: str) -> str:
        """Synchronous file read helper (to be run in thread)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @staticmethod
    def _read_json_file_sync(file_path: str) -> dict:
        """Synchronous JSON file read helper (to be run in thread)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough estimate: ~4 characters per token."""
        return len(text) // 4

    @staticmethod
    def _truncate_content(content: str, max_context_tokens: int, max_output_tokens: int, prompt_overhead: int = PROMPT_OVERHEAD_TOKENS) -> str:
        """
        Truncate content to fit within LM Studio context limits.
        
        Args:
            content: Article content to truncate
            max_context_tokens: Maximum context window (default: 4096)
            max_output_tokens: Maximum output tokens requested
            prompt_overhead: Tokens reserved for prompt/system messages
        
        Returns:
            Truncated content with notice if truncated
        """
        # Calculate available tokens for content
        # Reserve: prompt overhead + output tokens + safety margin (10%)
        available_tokens = max_context_tokens - prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.9)  # 10% safety margin
        
        content_tokens = LLMService._estimate_tokens(content)
        
        if content_tokens <= available_tokens:
            return content
        
        # Truncate to fit
        max_chars = available_tokens * 4
        truncated = content[:max_chars]
        
        # Try to truncate at sentence boundary
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        last_boundary = max(last_period, last_newline)
        
        if last_boundary > max_chars * 0.8:
            truncated = truncated[:last_boundary + 1]
        
        return truncated + "\n\n[Content truncated to fit context window]"
    
    def _lmstudio_url_candidates(self) -> list:
        """Get list of LMStudio URL candidates for fallback."""
        candidates = [
            self.lmstudio_url,
            "http://localhost:1234/v1",
            "http://127.0.0.1:1234/v1",
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    async def _post_lmstudio_chat(
        self,
        payload: Dict[str, Any],
        *,
        model_name: str,
        timeout: float = 300.0,
        failure_context: str = "LLM API call failed",
    ) -> Dict[str, Any]:
        """
        Call LMStudio /chat/completions with automatic fallback handling.
        
        Args:
            payload: JSON payload to send to LMStudio
            model_name: Name of the LMStudio model (for logging)
            timeout: Request timeout in seconds
            failure_context: Contextual message for raised errors
        
        Returns:
            Parsed JSON response from LMStudio
        
        Raises:
            RuntimeError: If all LMStudio URL candidates fail
            httpx.TimeoutException: If request times out
        """
        lmstudio_urls = self._lmstudio_url_candidates()
        last_error_detail = ""
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                logger.info(
                    f"Attempting LMStudio at {lmstudio_url} with model {model_name} "
                    f"({failure_context}) attempt {idx + 1}/{len(lmstudio_urls)}"
                )
                try:
                    # Use shorter connect timeout to fail fast if service is down
                    response = await client.post(
                        f"{lmstudio_url}/chat/completions",
                        headers={"Content-Type": "application/json"},
                        json=payload,
                        timeout=httpx.Timeout(timeout, connect=10.0, read=timeout),
                    )
                    
                    if response.status_code == 200:
                        return response.json()
                    else:
                        last_error_detail = f"Status {response.status_code}: {response.text}"
                        logger.warning(f"LMStudio at {lmstudio_url} returned {response.status_code}")
                        
                except httpx.TimeoutException as e:
                    last_error_detail = f"Request timeout after {timeout}s"
                    logger.warning(f"LMStudio at {lmstudio_url} timed out: {e}")
                    # Don't retry if this is the last URL - fail fast
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Request timeout after {timeout}s - "
                            f"LMStudio service may be down, slow, or overloaded. "
                            f"Check if LMStudio is running at {lmstudio_url}"
                        )
                    # Continue to next URL candidate
                    continue
                    
                except httpx.ConnectError as e:
                    last_error_detail = f"Connection error: {str(e)}"
                    logger.warning(f"LMStudio at {lmstudio_url} connection failed: {e}")
                    # Don't retry on connection errors - try next URL immediately
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Cannot connect to LMStudio service. "
                            f"Verify LMStudio is running and accessible at {lmstudio_url}"
                        )
                    # Continue to next URL candidate
                    continue
                    
                except Exception as e:
                    last_error_detail = str(e)
                    logger.error(f"LMStudio API request failed at {lmstudio_url}: {e}")
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(f"{failure_context}: {str(e)}")
        
        raise RuntimeError(f"{failure_context}: All LMStudio URLs failed. Last error: {last_error_detail}")
    
    async def rank_article(
        self,
        title: str,
        content: str,
        source: str,
        url: str,
        prompt_template_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Rank an article using LLM (Step 1 of workflow).
        
        Args:
            title: Article title
            content: Article content (filtered)
            source: Article source name
            url: Article URL
            prompt_template_path: Optional path to ranking prompt template
        
        Returns:
            Dict with 'score' (1-10 float) and 'reasoning' (str)
        """
        # Load ranking prompt template (async file read)
        if prompt_template_path and Path(prompt_template_path).exists():
            prompt_template = await asyncio.to_thread(self._read_file_sync, prompt_template_path)
        else:
            # Use default ranking prompt (reuse from existing prompts)
            # Try multiple possible locations
            possible_paths = [
                Path(__file__).parent.parent / "prompts" / "gpt4o_sigma_ranking.txt",
                Path(__file__).parent.parent / "prompts" / "lmstudio_sigma_ranking.txt",
                Path("src/prompts/gpt4o_sigma_ranking.txt"),
                Path("src/prompts/lmstudio_sigma_ranking.txt"),
            ]
            
            prompt_template = None
            for prompt_file in possible_paths:
                if prompt_file.exists():
                    prompt_template = await asyncio.to_thread(self._read_file_sync, str(prompt_file))
                    logger.info(f"Loaded ranking prompt from: {prompt_file}")
                    break
            
            if not prompt_template:
                # Fallback to simple prompt if files not found
                logger.warning("No ranking prompt file found, using fallback prompt")
                prompt_template = """You are a cybersecurity detection engineer. Analyze this threat intelligence article and provide a SIGMA huntability score using telemetry-focused criteria.

Title: {title}
Source: {source}
URL: {url}

Content:
{content}

Score the article from 1-10 for SIGMA rule generation potential. Consider:
- Telemetry observables (command-line, process chains, Event IDs)
- Behavioral patterns (not atomic IOCs)
- Detection rule feasibility

**SIGMA HUNTABILITY SCORE: [1-10]**"""
        
        # Truncate content to fit within context limits
        # Reserve space for prompt, system message, and 200 token response
        truncated_content = self._truncate_content(
            content,
            max_context_tokens=MAX_CONTEXT_TOKENS,
            max_output_tokens=200,
            prompt_overhead=PROMPT_OVERHEAD_TOKENS
        )
        
        if truncated_content != content:
            logger.warning(
                f"Truncated article content from {self._estimate_tokens(content)} to "
                f"{self._estimate_tokens(truncated_content)} tokens to fit context window"
            )
        
        # Format prompt
        prompt_text = prompt_template.format(
            title=title,
            source=source,
            url=url,
            content=truncated_content
        )
        
        payload = {
            "model": self.lmstudio_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a cybersecurity detection engineer. Score threat intelligence articles 1-10 for SIGMA huntability. Output only a score and brief reasoning."
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ],
            "max_tokens": 200,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.seed is not None:
            payload["seed"] = self.seed
        
        try:
            result = await self._post_lmstudio_chat(
                payload,
                model_name=self.lmstudio_model,
                timeout=60.0,  # Reduced from 120s - fail faster if service is down
                failure_context="Failed to rank article"
            )
            
            response_text = result['choices'][0]['message']['content']
            
            # Parse score from response
            import re
            score_match = re.search(r'(\d+(?:\.\d+)?)', response_text)
            if score_match:
                score = float(score_match.group(1))
                score = max(1.0, min(10.0, score))  # Clamp to 1-10
            else:
                logger.warning(f"Could not parse score from LLM response: {response_text[:100]}")
                score = 5.0  # Default fallback
            
            return {
                'score': score,
                'reasoning': response_text.strip(),
                'raw_response': response_text
            }
            
        except Exception as e:
            logger.error(f"Error ranking article: {e}")
            raise
    
    async def extract_behaviors(
        self,
        content: str,
        title: str,
        url: str,
        prompt_file_path: str
    ) -> Dict[str, Any]:
        """
        Extract huntable behaviors using ExtractAgent prompt (Step 2 of workflow).
        
        Args:
            content: Filtered article content
            title: Article title
            url: Article URL
            prompt_file_path: Path to ExtractAgent prompt file
        
        Returns:
            Dict with extracted behaviors and count of discrete huntables
        """
        # Load ExtractAgent prompt (async file read)
        prompt_path = Path(prompt_file_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"ExtractAgent prompt file not found: {prompt_file_path}")
        
        prompt_config = await asyncio.to_thread(self._read_json_file_sync, str(prompt_path))
        
        # Truncate content to fit within context limits
        # Reserve space for prompt, system message, instructions, and 4000 token response
        truncated_content = self._truncate_content(
            content,
            max_context_tokens=MAX_CONTEXT_TOKENS,
            max_output_tokens=4000,
            prompt_overhead=PROMPT_OVERHEAD_TOKENS + 500  # Extra for instructions JSON
        )
        
        if truncated_content != content:
            logger.warning(
                f"Truncated article content from {self._estimate_tokens(content)} to "
                f"{self._estimate_tokens(truncated_content)} tokens to fit context window"
            )
        
        # Build user prompt from config
        user_prompt = f"""Title: {title}
URL: {url}

Content:
{truncated_content}

Instructions: {json.dumps(prompt_config, indent=2)}

Extract telemetry-aware attacker behaviors and observables. Return as JSON with:
- behavioral_observables: List of extracted patterns with tags
- detection_queries: Any detection snippets found
- url: Source URL
- content: Extracted raw text with observables only
- discrete_huntables_count: Count of discrete huntable behaviors"""
        
        payload = {
            "model": self.lmstudio_model,
            "messages": [
                {
                    "role": "system",
                    "content": prompt_config.get("role", "You are a detection engineer LLM.")
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "max_tokens": 4000,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.seed is not None:
            payload["seed"] = self.seed
        
        try:
            result = await self._post_lmstudio_chat(
                payload,
                model_name=self.lmstudio_model,
                timeout=180.0,  # Reduced from 300s - fail faster if service is down
                failure_context="Failed to extract behaviors"
            )
            
            response_text = result['choices'][0]['message']['content']
            
            # Try to parse JSON from response
            try:
                # Look for JSON block in response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    extracted = json.loads(json_match.group(0))
                else:
                    # Fallback: create structured response
                    extracted = {
                        "behavioral_observables": [],
                        "detection_queries": [],
                        "url": url,
                        "content": content[:1000],  # Truncate for safety
                        "discrete_huntables_count": 0,
                        "raw_response": response_text
                    }
            except json.JSONDecodeError:
                logger.warning(f"Could not parse JSON from extraction response, using fallback")
                extracted = {
                    "behavioral_observables": [],
                    "detection_queries": [],
                    "url": url,
                    "content": content[:1000],
                    "discrete_huntables_count": 0,
                    "raw_response": response_text
                }
            
            return extracted
            
        except Exception as e:
            logger.error(f"Error extracting behaviors: {e}")
            raise

