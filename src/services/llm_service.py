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

# LM Studio context limits (default to 32768 for reasoning models, 4096 for others)
# Reasoning models need large context windows for both reasoning and output
MAX_CONTEXT_TOKENS = int(os.getenv("LMSTUDIO_MAX_CONTEXT", "32768"))
PROMPT_OVERHEAD_TOKENS = 500  # Reserve for prompt templates, system messages, etc.


class LLMService:
    """Service for LLM API calls using Deepseek-R1 via LMStudio."""
    
    def __init__(self):
        """Initialize LLM service with LMStudio configuration."""
        self.lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        
        # Default model (fallback for backward compatibility)
        default_model = os.getenv("LMSTUDIO_MODEL", "mistralai/mistral-7b-instruct-v0.3")
        
        # Per-operation model configuration
        # Falls back to LMSTUDIO_MODEL if not specified, then to default
        # Handle empty strings from docker-compose (empty string means "not set")
        self.lmstudio_model = default_model  # Keep for backward compatibility
        rank_model = os.getenv("LMSTUDIO_MODEL_RANK", "").strip()
        extract_model = os.getenv("LMSTUDIO_MODEL_EXTRACT", "").strip()
        sigma_model = os.getenv("LMSTUDIO_MODEL_SIGMA", "").strip()
        
        self.model_rank = rank_model if rank_model else default_model
        self.model_extract = extract_model if extract_model else default_model
        self.model_sigma = sigma_model if sigma_model else default_model
        
        # Detect if model requires system message conversion (Mistral models don't support system role)
        self._needs_system_conversion = self._model_needs_system_conversion(default_model)
        
        # Recommended settings for reasoning models (temperature/top_p work well for structured output)
        self.temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.2"))
        self.top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
        self.seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None
        
        logger.info(f"Initialized LLMService - Models: rank={self.model_rank}, extract={self.model_extract}, sigma={self.model_sigma}")
    
    def _model_needs_system_conversion(self, model_name: str) -> bool:
        """Check if model requires system message conversion (e.g., Mistral models)."""
        model_lower = model_name.lower()
        # Mistral models and some others don't support system role in LM Studio
        # Qwen models support system role, so no conversion needed
        return any(x in model_lower for x in ['mistral', 'mixtral']) and 'qwen' not in model_lower
    
    def _convert_messages_for_model(self, messages: list, model_name: str) -> list:
        """Convert system messages to user messages for models that don't support system role."""
        if not self._model_needs_system_conversion(model_name):
            return messages
        
        # For Mistral, convert system to user message using instruction format
        converted = []
        system_content = None
        
        # Collect system message
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg['content']
                break
        
        # Get user messages (should only be one)
        user_messages = [msg for msg in messages if msg.get("role") != "system"]
        
        if system_content and user_messages:
            # For Mistral, use direct instruction format without system role wrapper
            # Merge into a single user message with clear task separation
            user_content = user_messages[0]['content']
            # Only prepend system if it's not already integrated into the prompt
            if not user_content.startswith("Task:") and not user_content.startswith("You are"):
                # For ranking/extraction prompts that already have structure, just use user content
                # System role instructions are usually redundant
                converted = user_messages
            else:
                # Combine with clear separator
                converted = [{
                    "role": "user",
                    "content": f"{system_content}\n\n{user_content}"
                }]
        else:
            converted = messages if not any(m.get("role") == "system" for m in messages) else user_messages
        
        return converted
    
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
        cancellation_event: Optional[asyncio.Event] = None,
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
        
        logger.info(f"LMStudio URL candidates for {failure_context}: {lmstudio_urls}")
        
        # Check for cancellation before starting
        if cancellation_event and cancellation_event.is_set():
            raise asyncio.CancelledError("Request cancelled by client")
        
        async def make_request(client: httpx.AsyncClient, url: str) -> httpx.Response:
            """Make the HTTP request as a cancellable task."""
            return await client.post(
                f"{url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=httpx.Timeout(timeout, connect=30.0, read=timeout),
            )
        
        # Use longer connect timeout to allow DNS resolution and connection establishment
        connect_timeout = 30.0  # Increased from 10.0 to handle Docker networking
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=connect_timeout))
        try:
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                # Check for cancellation before each attempt
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError("Request cancelled by client")
                
                logger.info(
                    f"Attempting LMStudio at {lmstudio_url} with model {model_name} "
                    f"({failure_context}) attempt {idx + 1}/{len(lmstudio_urls)}"
                )
                logger.debug(f"Request payload preview: model={payload.get('model')}, messages_count={len(payload.get('messages', []))}, max_tokens={payload.get('max_tokens')}")
                try:
                    # Make request
                    request_task = asyncio.create_task(make_request(client, lmstudio_url))
                    
                    # Monitor for cancellation while waiting for response
                    if cancellation_event:
                        # Create a task that waits for cancellation
                        async def wait_for_cancellation():
                            if cancellation_event:
                                await cancellation_event.wait()
                        
                        cancellation_task = asyncio.create_task(wait_for_cancellation())
                        
                        # Wait for either request completion or cancellation
                        done, pending = await asyncio.wait(
                            [request_task, cancellation_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        
                        # Check if cancellation occurred
                        if cancellation_event.is_set():
                            # Cancel the request task and close the client to stop the HTTP request
                            if not request_task.done():
                                request_task.cancel()
                                # Explicitly close the client connection to stop the underlying HTTP request
                                try:
                                    await client.aclose()
                                except Exception:
                                    pass
                                try:
                                    await request_task
                                except (asyncio.CancelledError, httpx.RequestError, httpx.ConnectError):
                                    pass
                            raise asyncio.CancelledError("Request cancelled by client")
                        
                        # Get the response
                        response = await request_task
                    else:
                        # No cancellation support, just await the request
                        response = await request_task
                    
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
                    logger.error(f"LMStudio at {lmstudio_url} connection failed: {type(e).__name__}: {e}")
                    # Don't retry on connection errors - try next URL immediately
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Cannot connect to LMStudio service. "
                            f"Tried URLs: {lmstudio_urls}. Last error: {str(e)}. "
                            f"Verify LMStudio is running and accessible at {lmstudio_url}"
                        )
                    # Continue to next URL candidate
                    continue
                    
                except asyncio.CancelledError:
                    # Re-raise cancellation errors
                    raise
                except Exception as e:
                    last_error_detail = str(e)
                    logger.error(f"LMStudio API request failed at {lmstudio_url}: {e}")
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(f"{failure_context}: {str(e)}")
        finally:
            # Ensure client is closed
            try:
                await client.aclose()
            except Exception:
                pass
        
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
        
        # Use ranking-specific model
        model_name = self.model_rank
        
        # For Mistral, use direct instruction format without separate system message
        if self._model_needs_system_conversion(model_name):
            # Single user message with integrated instructions
            messages = [
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]
        else:
            messages = [
                {
                    "role": "system",
                    "content": "You are a cybersecurity detection engineer. Score threat intelligence articles 1-10 for SIGMA huntability. Output only a score and brief reasoning."
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]
        
        # For reasoning models (deepseek-r1), need much higher max_tokens
        # Reasoning can use 1000-2000 tokens, final answer needs ~100 tokens
        is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
        max_output_tokens = 2500 if is_reasoning_model else 800
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.seed is not None:
            payload["seed"] = self.seed
        
        logger.info(f"Ranking request: max_tokens={max_output_tokens} (reasoning_model={is_reasoning_model})")
        
        try:
            # Reasoning models need longer timeouts - they generate extensive reasoning + answer
            ranking_timeout = 180.0 if is_reasoning_model else 60.0
            
            result = await self._post_lmstudio_chat(
                payload,
                model_name=model_name,
                timeout=ranking_timeout,
                failure_context="Failed to rank article"
            )
            
            # Deepseek-R1 returns reasoning in 'reasoning_content', fallback to 'content'
            message = result['choices'][0]['message']
            response_text = message.get('content', '') or message.get('reasoning_content', '')
            
            # Check if response was truncated due to token limit
            finish_reason = result['choices'][0].get('finish_reason', '')
            if finish_reason == 'length':
                logger.warning(f"Ranking response was truncated (finish_reason=length). Used {result.get('usage', {}).get('completion_tokens', 0)} tokens. max_tokens={max_output_tokens} may need to be increased.")
            
            # Fail if response is empty
            if not response_text or len(response_text.strip()) == 0:
                logger.error("LLM returned empty response for ranking")
                raise ValueError("LLM returned empty response for ranking. Check LMStudio is responding correctly.")
            
            logger.info(f"Ranking response received: {len(response_text)} chars (finish_reason={finish_reason})")
            
            # Parse score from response - look for "SIGMA HUNTABILITY SCORE: X" pattern first
            import re
            score = None
            
            # Try multiple patterns, searching entire response (not just first 200 chars)
            # Pattern 1: "SIGMA HUNTABILITY SCORE: X" (exact format)
            score_match = re.search(r'SIGMA\s+HUNTABILITY\s+SCORE[:\s]+(\d+(?:\.\d+)?)', response_text, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
            else:
                # Pattern 2: "Score: X" or "**Score:** X"
                score_match = re.search(r'(?:^|\n|^|\*|#)\s*Score[:\s#*]+\s*(\d+(?:\.\d+)?)', response_text, re.IGNORECASE | re.MULTILINE)
                if score_match:
                    score = float(score_match.group(1))
                else:
                    # Pattern 3: Look for numbers 1-10 in the last 500 chars (where final answer usually is)
                    # Reasoning models often put the score at the end after reasoning
                    tail_text = response_text[-500:] if len(response_text) > 500 else response_text
                    score_match = re.search(r'\b([1-9]|10)(?:\.\d+)?\b', tail_text)
                    if score_match:
                        score = float(score_match.group(1))
            
            if score is not None:
                score = max(1.0, min(10.0, score))  # Clamp to 1-10
                logger.info(f"Parsed ranking score: {score}/10")
            else:
                # If truncated and no score found, provide helpful error
                if finish_reason == 'length':
                    error_msg = f"Ranking response was truncated and no score found. Response length: {len(response_text)} chars. Try increasing max_tokens (current: {max_output_tokens}). Response preview: {response_text[-300:]}"
                else:
                    error_msg = f"Could not parse score from LLM response. Response: {response_text[:500]}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
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
        
        # Use extraction-specific model
        model_name = self.model_extract
        
        # Truncate content to fit within context limits
        # For reasoning models (deepseek-r1), need much higher max_tokens (reasoning + JSON)
        # Reasoning can use 3000-4000 tokens, JSON needs 2000-3000 tokens
        is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
        max_output_tokens = 10000 if is_reasoning_model else 4000
        
        truncated_content = self._truncate_content(
            content,
            max_context_tokens=MAX_CONTEXT_TOKENS,
            max_output_tokens=max_output_tokens,
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
        
        messages = [
                {
                    "role": "system",
                    "content": prompt_config.get("role", "You are a detection engineer LLM.")
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
        ]
        
        # Convert system messages for models that don't support them
        messages = self._convert_messages_for_model(messages, model_name)
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.seed is not None:
            payload["seed"] = self.seed
        
        logger.info(f"Extract behaviors request: max_tokens={max_output_tokens} (reasoning_model={is_reasoning_model})")
        
        try:
            # Reasoning models need much longer timeouts - they generate extensive reasoning + JSON
            # With 10000 max_tokens and reasoning, can take 5-10 minutes
            extraction_timeout = 600.0 if is_reasoning_model else 180.0
            
            result = await self._post_lmstudio_chat(
                payload,
                model_name=model_name,
                timeout=extraction_timeout,
                failure_context="Failed to extract behaviors"
            )
            
            # Deepseek-R1: check both content and reasoning_content
            # Often the final answer is in 'content' while reasoning is in 'reasoning_content'
            message = result['choices'][0]['message']
            content_text = message.get('content', '')
            reasoning_text = message.get('reasoning_content', '')
            
            # Check for token limit hit
            finish_reason = result['choices'][0].get('finish_reason', '')
            if finish_reason == 'length':
                logger.error(f"Token limit hit! Used {result.get('usage', {}).get('completion_tokens', 0)} completion tokens. "
                           f"Content: {len(content_text)} chars, Reasoning: {len(reasoning_text)} chars. "
                           f"max_tokens={max_output_tokens} may be too low for reasoning model.")
            
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
                if finish_reason == 'length':
                    logger.error(f"Token limit hit and no JSON found. Check max_tokens setting (current: {max_output_tokens})")
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
        prompt_file_path: str,
        cancellation_event: Optional[asyncio.Event] = None
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

CRITICAL: If you are a reasoning model, you may include reasoning text, but you MUST end your response with a valid JSON object. The JSON object must contain the extracted observables following the output_format structure exactly (with atomic_iocs, behavioral_observables, and metadata fields). Begin the JSON object with {{ and end with }}. If no observables are found, still output the complete JSON structure with empty arrays."""
        
        # Use extract model for observable extraction (backward compatible with extract_behaviors)
        model_name = self.model_extract
        
        messages = [
                {
                    "role": "system",
                    "content": prompt_config.get("role", "You are a cybersecurity analyst specializing in IOC and observable extraction.")
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
        ]
        
        # Convert system messages for models that don't support them
        messages = self._convert_messages_for_model(messages, model_name)
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": 4000,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        
        if self.seed is not None:
            payload["seed"] = self.seed
        
        try:
            # Check for cancellation before making the request
            if cancellation_event and cancellation_event.is_set():
                raise asyncio.CancelledError("Extraction cancelled by client")
            
            result = await self._post_lmstudio_chat(
                payload,
                model_name=model_name,
                timeout=180.0,
                failure_context="Failed to extract observables",
                cancellation_event=cancellation_event
            )
            
            # Check for cancellation after the request
            if cancellation_event and cancellation_event.is_set():
                raise asyncio.CancelledError("Extraction cancelled by client")
            
            # Deepseek-R1: check both content and reasoning_content
            # Often the final answer is in 'content' while reasoning is in 'reasoning_content'
            message = result['choices'][0]['message']
            content_text = message.get('content', '')
            reasoning_text = message.get('reasoning_content', '')
            
            # Prefer content if it looks like JSON, otherwise check reasoning_content
            # Deepseek-R1 might put JSON in either field
            if content_text and (content_text.strip().startswith('{') or 'atomic_iocs' in content_text or 'behavioral_observables' in content_text):
                response_text = content_text
                logger.info("Using 'content' field for observable extraction (looks like JSON)")
            elif reasoning_text and (reasoning_text.strip().startswith('{') or 'atomic_iocs' in reasoning_text or 'behavioral_observables' in reasoning_text):
                response_text = reasoning_text
                logger.info("Using 'reasoning_content' field for observable extraction (looks like JSON)")
            else:
                # Fallback: combine both or use whichever is available
                # Reasoning models may put reasoning in reasoning_content and JSON in content, or combine them
                response_text = content_text + '\n\n' + reasoning_text if (content_text and reasoning_text) else (content_text or reasoning_text)
                logger.info(f"Combining or using available fields. Content: {len(content_text)} chars, Reasoning: {len(reasoning_text)} chars")
            
            if not response_text or len(response_text.strip()) == 0:
                logger.error("LLM returned empty response for observable extraction")
                raise ValueError("LLM returned empty response. Check LMStudio is responding correctly.")
            
            logger.info(f"Observable extraction response received: {len(response_text)} chars")
            
            # Parse JSON from response (reuse same logic as extract_behaviors)
            # Deepseek-R1 may provide reasoning, then JSON at the end
            # Strategy: Look for JSON at the end of the response first, then fallback to anywhere
            try:
                json_text = None
                
                # First, try to extract JSON from markdown code fences (```json ... ``` or ``` ... ```)
                code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
                if code_fence_match:
                    json_text = code_fence_match.group(1).strip()
                    logger.info("Extracted JSON from markdown code fence")
                else:
                    # Look for JSON object at the END of response (most likely after reasoning)
                    # Strategy: Find ALL potential JSON objects, then take the one with expected keys from the end
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
                                expected_keys = ['atomic_iocs', 'behavioral_observables', 'metadata']
                                if any(key in candidate_data for key in expected_keys):
                                    json_candidates.append((open_pos, json_end, len(candidate_json), candidate_data))
                            except json.JSONDecodeError:
                                pass
                        
                        search_pos = open_pos + 1
                    
                    if json_candidates:
                        # Prefer candidates with expected keys, and prefer those from the end of the response
                        # (reasoning models typically output JSON after reasoning)
                        root_candidates = [c for c in json_candidates if any(k in c[3] for k in ['atomic_iocs', 'behavioral_observables', 'metadata'])]
                        if root_candidates:
                            # Prefer the one closest to the end (highest open_pos), but also consider size
                            # Sort by position (descending) first, then by size (descending)
                            root_candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
                            _, _, _, root_data = root_candidates[0]
                            json_text = json.dumps(root_data)
                            logger.info(f"Extracted root JSON object from position {root_candidates[0][0]} (near end of response)")
                        else:
                            # Fallback to largest candidate, preferring later in response
                            json_candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
                            _, _, _, largest_data = json_candidates[0]
                            json_text = json.dumps(largest_data)
                            logger.info(f"Extracted largest JSON object from position {json_candidates[0][0]} (fallback)")
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
                
                if atomic_count == 0 and behavioral_count == 0:
                    logger.warning(f"No observables extracted from article. Raw response length: {len(response_text)} chars. First 500 chars: {response_text[:500]}")
                else:
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

