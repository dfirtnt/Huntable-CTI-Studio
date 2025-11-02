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
            "max_tokens": 800,  # Increased for Deepseek-R1 reasoning format
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
            
            # Deepseek-R1 returns reasoning in 'reasoning_content', fallback to 'content'
            message = result['choices'][0]['message']
            response_text = message.get('content', '') or message.get('reasoning_content', '')
            
            # Fail if response is empty
            if not response_text or len(response_text.strip()) == 0:
                logger.error("LLM returned empty response for ranking")
                raise ValueError("LLM returned empty response for ranking. Check LMStudio is responding correctly.")
            
            logger.info(f"Ranking response received: {len(response_text)} chars")
            
            # Parse score from response
            import re
            score_match = re.search(r'(\d+(?:\.\d+)?)', response_text)
            if score_match:
                score = float(score_match.group(1))
                score = max(1.0, min(10.0, score))  # Clamp to 1-10
            else:
                logger.error(f"Could not parse score from LLM response: {response_text[:200]}")
                raise ValueError(f"LLM ranking response could not be parsed. Response: {response_text[:200]}")
            
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
        # Load ExtractAgent prompt config (async file read)
        prompt_path = Path(prompt_file_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"ExtractAgent prompt file not found: {prompt_file_path}")
        
        prompt_config = await asyncio.to_thread(self._read_json_file_sync, str(prompt_path))
        
        # Load instructions template from prompts folder
        prompts_dir = prompt_path.parent
        instructions_path = prompts_dir / "ExtractAgentInstructions.txt"
        if not instructions_path.exists():
            raise FileNotFoundError(f"ExtractAgent instructions file not found: {instructions_path}")
        
        instructions_template = await asyncio.to_thread(self._read_file_sync, str(instructions_path))
        
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
        
        # Build user prompt from instructions template
        prompt_config_json = json.dumps(prompt_config, indent=2)
        user_prompt = instructions_template.format(
            title=title,
            url=url,
            content=truncated_content,
            prompt_config=prompt_config_json
        )
        
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
            
            # Deepseek-R1: check both content and reasoning_content
            # Often the final answer is in 'content' while reasoning is in 'reasoning_content'
            message = result['choices'][0]['message']
            content_text = message.get('content', '')
            reasoning_text = message.get('reasoning_content', '')
            
            # Prefer content if it looks like JSON, otherwise check reasoning_content
            # Deepseek-R1 might put JSON in either field
            if content_text and (content_text.strip().startswith('{') or 'behavioral_observables' in content_text):
                response_text = content_text
                logger.info("Using 'content' field for extraction (looks like JSON)")
            elif reasoning_text and (reasoning_text.strip().startswith('{') or 'behavioral_observables' in reasoning_text):
                response_text = reasoning_text
                logger.info("Using 'reasoning_content' field for extraction (looks like JSON)")
            else:
                # Fallback: use content first, then reasoning
                response_text = content_text or reasoning_text
                logger.warning(f"Neither field looks like JSON. Using content ({len(content_text)} chars) or reasoning ({len(reasoning_text)} chars)")
            
            # Log response for debugging
            if not response_text or len(response_text.strip()) == 0:
                logger.error("LLM returned empty response for extraction")
                raise ValueError("LLM returned empty response. Check LMStudio is responding correctly.")
            
            logger.info(f"Extraction response received: {len(response_text)} chars")
            
            # Try to parse JSON from response
            try:
                # Deepseek-R1 may provide reasoning, then JSON at the end
                # Strategy: Look for JSON at the end of the response first, then fallback to anywhere
                
                json_text = None
                
                # First, try to extract JSON from markdown code fences (```json ... ``` or ``` ... ```)
                code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
                if code_fence_match:
                    json_text = code_fence_match.group(1).strip()
                    logger.info("Extracted JSON from markdown code fence")
                else:
                    # Look for JSON object at the END of response (most likely after reasoning)
                    # Strategy: Find ALL potential JSON objects, then take the largest/root one
                    # This handles cases where reasoning contains nested JSON examples
                    
                    # Find all potential JSON object start positions
                    json_candidates = []
                    search_pos = 0
                    while True:
                        open_pos = response_text.find('{', search_pos)
                        if open_pos == -1:
                            break
                        
                        # Try to find matching closing brace
                        brace_count = 0
                        json_end = -1
                        for i in range(open_pos, len(response_text)):
                            if response_text[i] == '{':
                                brace_count += 1
                            elif response_text[i] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        
                        if json_end != -1:
                            candidate_json = response_text[open_pos:json_end]
                            # Try to parse it to validate it's valid JSON
                            try:
                                candidate_data = json.loads(candidate_json)
                                # Check if it has expected root-level keys (not a nested object)
                                if any(key in candidate_data for key in ['behavioral_observables', 'detection_queries', 'url', 'content', 'discrete_huntables_count']):
                                    json_candidates.append((open_pos, json_end, len(candidate_json), candidate_data))
                            except json.JSONDecodeError:
                                pass
                        
                        search_pos = open_pos + 1
                    
                    if json_candidates:
                        # Prefer the one with expected keys, then largest, then last
                        root_candidates = [c for c in json_candidates if any(k in c[3] for k in ['behavioral_observables', 'url', 'content'])]
                        if root_candidates:
                            # Take the largest root-level candidate
                            _, _, _, root_data = max(root_candidates, key=lambda x: x[2])
                            json_text = json.dumps(root_data)  # Re-serialize to get clean JSON
                            logger.info("Extracted root JSON object from end of response")
                        else:
                            # Fallback to largest candidate
                            _, _, _, largest_data = max(json_candidates, key=lambda x: x[2])
                            json_text = json.dumps(largest_data)
                            logger.info("Extracted largest JSON object from response")
                    else:
                        raise ValueError("No valid JSON found in response")
                
                # Parse JSON
                extracted = json.loads(json_text)
                
                # Ensure required fields exist
                if 'raw_response' not in extracted:
                    extracted['raw_response'] = response_text
                    
                # Validate discrete_huntables_count is present and is a number
                if 'discrete_huntables_count' not in extracted:
                    logger.warning("discrete_huntables_count missing from extraction, defaulting to 0")
                    extracted['discrete_huntables_count'] = 0
                elif not isinstance(extracted['discrete_huntables_count'], (int, float)):
                    logger.warning(f"discrete_huntables_count is not a number: {extracted['discrete_huntables_count']}, defaulting to 0")
                    extracted['discrete_huntables_count'] = 0
                
                logger.info(f"Parsed extraction result: {len(extracted.get('behavioral_observables', []))} observables, {extracted.get('discrete_huntables_count', 0)} huntables")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Could not parse JSON from extraction response: {e}. Using fallback. Response preview: {response_text[:200]}")
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
    
    async def extract_observables(
        self,
        content: str,
        title: str,
        url: str,
        prompt_file_path: str
    ) -> Dict[str, Any]:
        """
        Extract observables (IOCs and behavioral indicators) using ExtractObservables prompt.
        
        Args:
            content: Filtered article content
            title: Article title
            url: Article URL
            prompt_file_path: Path to ExtractObservables prompt file
        
        Returns:
            Dict with extracted observables including atomic IOCs and behavioral patterns
        """
        # Load ExtractObservables prompt (async file read)
        prompt_path = Path(prompt_file_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"ExtractObservables prompt file not found: {prompt_file_path}")
        
        prompt_config = await asyncio.to_thread(self._read_json_file_sync, str(prompt_path))
        
        # Truncate content to fit within context limits
        truncated_content = self._truncate_content(
            content,
            max_context_tokens=MAX_CONTEXT_TOKENS,
            max_output_tokens=4000,
            prompt_overhead=PROMPT_OVERHEAD_TOKENS + 500
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

Extract all IOCs and observables (atomic indicators and behavioral patterns).

{json.dumps(prompt_config, indent=2)}

CRITICAL: Output your response as a valid JSON object only. Begin with {{ and end with }}. Do not include reasoning, explanations, or markdown outside the JSON object."""
        
        payload = {
            "model": self.lmstudio_model,
            "messages": [
                {
                    "role": "system",
                    "content": prompt_config.get("role", "You are a cybersecurity analyst specializing in IOC and observable extraction.")
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
                timeout=180.0,
                failure_context="Failed to extract observables"
            )
            
            message = result['choices'][0]['message']
            response_text = message.get('content', '') or message.get('reasoning_content', '')
            
            if not response_text or len(response_text.strip()) == 0:
                logger.error("LLM returned empty response for observable extraction")
                raise ValueError("LLM returned empty response. Check LMStudio is responding correctly.")
            
            logger.info(f"Observable extraction response received: {len(response_text)} chars")
            
            # Parse JSON from response (reuse same logic as extract_behaviors)
            try:
                json_text = None
                
                code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
                if code_fence_match:
                    json_text = code_fence_match.group(1).strip()
                else:
                    json_candidates = []
                    search_pos = 0
                    while True:
                        open_pos = response_text.find('{', search_pos)
                        if open_pos == -1:
                            break
                        
                        brace_count = 0
                        json_end = -1
                        for i in range(open_pos, len(response_text)):
                            if response_text[i] == '{':
                                brace_count += 1
                            elif response_text[i] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        
                        if json_end != -1:
                            candidate_json = response_text[open_pos:json_end]
                            try:
                                candidate_data = json.loads(candidate_json)
                                expected_keys = ['atomic_iocs', 'behavioral_observables', 'metadata']
                                if any(key in candidate_data for key in expected_keys):
                                    json_candidates.append((open_pos, json_end, len(candidate_json), candidate_data))
                            except json.JSONDecodeError:
                                pass
                        
                        search_pos = open_pos + 1
                    
                    if json_candidates:
                        root_candidates = [c for c in json_candidates if any(k in c[3] for k in ['atomic_iocs', 'behavioral_observables', 'metadata'])]
                        if root_candidates:
                            _, _, _, root_data = max(root_candidates, key=lambda x: x[2])
                            json_text = json.dumps(root_data)
                        else:
                            _, _, _, largest_data = max(json_candidates, key=lambda x: x[2])
                            json_text = json.dumps(largest_data)
                    else:
                        raise ValueError("No valid JSON found in response")
                
                extracted = json.loads(json_text)
                
                if 'raw_response' not in extracted:
                    extracted['raw_response'] = response_text
                
                # Calculate counts
                atomic_count = 0
                behavioral_count = 0
                
                if 'atomic_iocs' in extracted:
                    atomic_count = sum(len(v) if isinstance(v, list) else 0 for v in extracted['atomic_iocs'].values())
                
                if 'behavioral_observables' in extracted:
                    behavioral_count = sum(len(v) if isinstance(v, list) else 0 for v in extracted['behavioral_observables'].values())
                
                if 'metadata' not in extracted:
                    extracted['metadata'] = {}
                
                extracted['metadata']['observable_count'] = atomic_count + behavioral_count
                extracted['metadata']['atomic_count'] = atomic_count
                extracted['metadata']['behavioral_count'] = behavioral_count
                extracted['metadata']['url'] = url
                
                logger.info(f"Parsed observable extraction result: {atomic_count} atomic IOCs, {behavioral_count} behavioral observables")
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Could not parse JSON from observable extraction response: {e}. Using fallback.")
                extracted = {
                    "atomic_iocs": {
                        "ip_addresses": [], "domains": [], "urls": [], "file_hashes": [], "emails": []
                    },
                    "behavioral_observables": {
                        "command_line": [], "process_chains": [], "registry_keys": [], "file_paths": [],
                        "services": [], "mutexes": [], "named_pipes": [], "event_logs": [], "api_calls": []
                    },
                    "metadata": {
                        "url": url,
                        "observable_count": 0,
                        "atomic_count": 0,
                        "behavioral_count": 0
                    },
                    "raw_response": response_text
                }
            
            return extracted
            
        except Exception as e:
            logger.error(f"Error extracting observables: {e}")
            raise

