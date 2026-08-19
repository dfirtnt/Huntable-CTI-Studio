"""
LLM Service for Deepseek-R1 integration via LMStudio.

Provides LLM-based ranking and extraction for agentic workflow.
"""

import hashlib
import json
import logging
import math
import os
import re
import subprocess
from typing import Any

from src.database.manager import DatabaseManager
from src.services.llm_client import LLMClientMixin
from src.services.llm_prompting import (
    _TRACEABILITY_FIELDS,
    _TRACEABILITY_REQUIRED,
    MIN_USER_CONTENT_CHARS,
    ContextLengthExceededError,
    PreprocessInvariantError,
    PromptConfigValidationError,
    _parse_rank_prompt,
    _validate_extraction_prompt_config,
    _validate_preprocess_invariants,
)
from src.services.llm_routing import (
    LMSTUDIO_APPSETTING_KEYS,
    MAX_CONTEXT_TOKENS,
    MIN_CONTEXT_LENGTH_THRESHOLD,
    PROMPT_OVERHEAD_TOKENS,
    WORKFLOW_PROVIDER_APPSETTING_KEYS,
    LLMRoutingMixin,
)
from src.utils.langfuse_client import log_llm_completion, log_llm_error, trace_llm_call

logger = logging.getLogger(__name__)

__all__ = [
    "ContextLengthExceededError",
    "DatabaseManager",
    "LLMService",
    "LMSTUDIO_APPSETTING_KEYS",
    "MAX_CONTEXT_TOKENS",
    "MIN_CONTEXT_LENGTH_THRESHOLD",
    "MIN_USER_CONTENT_CHARS",
    "PROMPT_OVERHEAD_TOKENS",
    "PreprocessInvariantError",
    "PromptConfigValidationError",
    "WORKFLOW_PROVIDER_APPSETTING_KEYS",
    "_TRACEABILITY_FIELDS",
    "_TRACEABILITY_REQUIRED",
    "_parse_rank_prompt",
    "_validate_extraction_prompt_config",
    "_validate_preprocess_invariants",
    "subprocess",
]


class LLMService(LLMRoutingMixin, LLMClientMixin):
    """Service for LLM API calls using Deepseek-R1 via LMStudio."""

    def __init__(self, config_models: dict[str, str] | None = None):
        """
        Initialize LLM service with LMStudio configuration.

        Args:
            config_models: Optional dict of agent models from workflow config.
                          Format: {"RankAgent": "model_name", "ExtractAgent": "...", "SigmaAgent": "..."}
                          If provided, these override environment variables.
        """
        from src.utils.lmstudio_url import get_lmstudio_base_url

        self.lmstudio_url = get_lmstudio_base_url("http://host.docker.internal:1234/v1")
        self.assumed_lmstudio_context_tokens = int(os.getenv("WORKFLOW_LMSTUDIO_CONTEXT_TOKENS", "16384"))
        self.assumed_cloud_context_tokens = int(os.getenv("WORKFLOW_CLOUD_CONTEXT_TOKENS", "80000"))

        # Per-operation model configuration
        # Priority: config_models > AppSettings DB > environment variables > default
        config_models = config_models or {}

        # Defensive: if a caller hands us the WorkflowConfigV2 nested form
        # ({"CmdlineExtract": {"provider": "openai", "model": "..."}}) instead of
        # the legacy flat keys ({"CmdlineExtract_model": "...", "CmdlineExtract_provider": "..."}),
        # unwrap it. Without this, every flat-key lookup below misses, every
        # provider canonicalizes to "lmstudio" via the empty-string fallback,
        # and the workflow silently runs against the wrong backend.
        from src.config.workflow_config_schema import agent_models_is_nested, normalize_agent_models_to_flat

        if agent_models_is_nested(config_models):
            logger.warning(
                "config_models arrived in nested WorkflowConfigV2 format; "
                "unwrapping to flat keys. Save path should normalize this -- "
                "see workflow_config.update_workflow_config."
            )
            config_models = normalize_agent_models_to_flat(config_models)

        workflow_settings = self._load_workflow_provider_settings()
        lmstudio_db = self._load_lmstudio_settings()

        # Default model: AppSettings DB > env > hardcoded default
        default_model = lmstudio_db.get("LMSTUDIO_MODEL") or os.getenv(
            "LMSTUDIO_MODEL", "mistralai/mistral-7b-instruct-v0.3"
        )
        self.lmstudio_model = default_model  # Keep for backward compatibility
        # Prefer AppSettings, fall back to env; if a key exists, default enable unless explicitly false
        self.openai_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_api_key"])
            or os.getenv("WORKFLOW_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if isinstance(self.openai_api_key, str):
            self.openai_api_key = self.openai_api_key.strip()
        self.anthropic_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["anthropic_api_key"])
            or os.getenv("WORKFLOW_ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )

        def _enabled(setting_key: str, env_key: str, default: bool) -> bool:
            # AppSettings override, then env flag, else default
            flag = workflow_settings.get(setting_key)
            if flag is None:
                flag = os.getenv(env_key)
            return self._bool_from_setting(flag, default)

        self.workflow_openai_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_enabled"],
            "WORKFLOW_OPENAI_ENABLED",
            bool(self.openai_api_key),
        )
        self.workflow_anthropic_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["anthropic_enabled"],
            "WORKFLOW_ANTHROPIC_ENABLED",
            bool(self.anthropic_api_key),
        )
        self.workflow_lmstudio_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["lmstudio_enabled"],
            "WORKFLOW_LMSTUDIO_ENABLED",
            False,
        )
        self.workflow_codex_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["codex_enabled"],
            "WORKFLOW_CODEX_ENABLED",
            False,
        )

        self.provider_defaults = {
            "lmstudio": default_model,
            "openai": os.getenv("WORKFLOW_OPENAI_MODEL", "gpt-4o-mini"),
            "codex": os.getenv("WORKFLOW_CODEX_MODEL", "gpt-5.6-luna"),
            "anthropic": os.getenv("WORKFLOW_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        }

        _rp = (config_models.get("RankAgent_provider") or "").strip()
        self.provider_rank = self._canonicalize_provider(_rp) if _rp else ""
        _ep = (config_models.get("ExtractAgent_provider") or "").strip()
        self.provider_extract = self._canonicalize_provider(_ep) if _ep else ""
        _sp = (config_models.get("SigmaAgent_provider") or "").strip()
        self.provider_sigma = self._canonicalize_provider(_sp) if _sp else ""

        rank_override = (config_models.get("RankAgent") or "").strip()
        rank_env = (lmstudio_db.get("LMSTUDIO_MODEL_RANK") or os.getenv("LMSTUDIO_MODEL_RANK", "")).strip()
        self.model_rank = self._resolve_agent_model(
            "RankAgent", rank_override, rank_env, self.provider_rank, default_model
        )
        self.model_extract = self._resolve_agent_model(
            "ExtractAgent",
            (config_models.get("ExtractAgent") or "").strip(),
            (lmstudio_db.get("LMSTUDIO_MODEL_EXTRACT") or os.getenv("LMSTUDIO_MODEL_EXTRACT", "")).strip(),
            self.provider_extract,
            default_model,
            require_specific_model=False,
        )
        self.model_sigma = self._resolve_agent_model(
            "SigmaAgent",
            (config_models.get("SigmaAgent") or "").strip(),
            (lmstudio_db.get("LMSTUDIO_MODEL_SIGMA") or os.getenv("LMSTUDIO_MODEL_SIGMA", "")).strip(),
            self.provider_sigma,
            default_model=default_model,
            require_specific_model=False,
        )

        # Detect if model requires system message conversion (Mistral models don't support system role)
        self._needs_system_conversion = self._model_needs_system_conversion(default_model)

        # Temperature: AppSettings DB > env > default 0.0
        _temp_str = lmstudio_db.get("LMSTUDIO_TEMPERATURE") or os.getenv("LMSTUDIO_TEMPERATURE", "0.0")
        self.temperature = float(_temp_str)
        self.temperature_rank = float(config_models.get("RankAgent_temperature") or _temp_str)
        self.temperature_sigma = float(config_models.get("SigmaAgent_temperature") or _temp_str)

        # Top-P: AppSettings DB > env > default 0.9
        _top_p_str = lmstudio_db.get("LMSTUDIO_TOP_P") or os.getenv("LMSTUDIO_TOP_P", "0.9")
        self.top_p = float(_top_p_str)
        rank_top_p_raw = config_models.get("RankAgent_top_p") if config_models else None
        self.top_p_rank = float(rank_top_p_raw) if rank_top_p_raw is not None else float(_top_p_str)
        sigma_top_p_raw = config_models.get("SigmaAgent_top_p") if config_models else None
        self.top_p_sigma = float(sigma_top_p_raw) if sigma_top_p_raw is not None else float(_top_p_str)

        # Store config_models for per-subagent top_p lookup
        self.config_models = config_models if config_models else {}

        # Seed: AppSettings DB > env > default None
        _seed_str = lmstudio_db.get("LMSTUDIO_SEED") or os.getenv("LMSTUDIO_SEED")
        self.seed = int(_seed_str) if _seed_str else None

        model_source = "config" if config_models else "environment"
        logger.info(
            f"Initialized LLMService ({model_source}) - Providers: "
            f"rank={self.provider_rank}, extract={self.provider_extract}, sigma={self.provider_sigma} "
            f"- Models: rank={self.model_rank}, extract={self.model_extract}, sigma={self.model_sigma}"
        )

    @staticmethod
    def compute_rank_ground_truth(hunt_score: Any | None, ml_score: Any | None) -> dict[str, float | None]:
        """
        Derive a 1-10 ground truth rank from hunt and ML scores (0-100 scale).
        Rounds the mean score to the nearest 10, then maps to 1-10.
        """

        def _to_float(value: Any) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        hunt = _to_float(hunt_score)
        ml = _to_float(ml_score)

        if hunt is None or ml is None:
            return {
                "ground_truth_rank": None,
                "ground_truth_mean": None,
                "rounded_to_nearest_10": None,
                "hunt_score": hunt,
                "ml_score": ml,
            }

        mean_score = (hunt + ml) / 2
        rounded_to_nearest_10 = math.floor((mean_score + 5) / 10) * 10
        ground_truth_rank = max(1.0, min(10.0, rounded_to_nearest_10 / 10))

        return {
            "ground_truth_rank": ground_truth_rank,
            "ground_truth_mean": mean_score,
            "rounded_to_nearest_10": rounded_to_nearest_10,
            "hunt_score": hunt,
            "ml_score": ml,
        }

    async def rank_article(
        self,
        title: str,
        content: str,
        source: str,
        url: str,
        _prompt_template_path: str | None = None,
        prompt_template: str | None = None,
        system_override: str | None = None,
        execution_id: int | None = None,
        article_id: int | None = None,
        ground_truth_rank: float | None = None,
        ground_truth_details: dict[str, float | None] | None = None,
    ) -> dict[str, Any]:
        """
        Rank an article using LLM (Step 1 of workflow).

        Args:
            title: Article title
            content: Article content (filtered)
            source: Article source name
            url: Article URL
            _prompt_template_path: Unused; prompt_template from workflow config is required
            prompt_template: Optional user-message template; falls back to
                src/prompts/rank_article.txt if None.
            system_override: Optional system persona; takes precedence over any
                system extracted from prompt_template's JSON wrapper.
            ground_truth_rank: Optional 1-10 ground truth rank to log to Langfuse
            ground_truth_details: Optional dict of source scores/rounding used for ground truth

        Returns:
            Dict with 'score' (1-10 float) and 'reasoning' (str)
        """
        # Resolve template: explicit > file fallback
        if prompt_template:
            prompt_template_str, embedded_system = _parse_rank_prompt(prompt_template)
        else:
            from src.utils.prompt_loader import load_prompt_async

            prompt_template_str = await load_prompt_async("rank_article")
            embedded_system = None

        # Caller-supplied system override takes precedence over any embedded one.
        system_override = system_override or embedded_system

        logger.info(f"Using RankAgent prompt from workflow config (length: {len(prompt_template_str)} chars)")

        # Get actual model context length to use for truncation
        # IMPORTANT: LM Studio's configured context may be much smaller than detected/theoretical max
        # Use very conservative fixed limits to ensure we never exceed actual configured context
        # Reasoning models: 8192 max, non-reasoning: 4096 max
        # These are conservative limits that should work with most LM Studio configurations

        # Determine model used for ranking
        model_name = self.model_rank
        if not model_name:
            raise ValueError("RankAgent model is not configured. Set agent_models.RankAgent or LMSTUDIO_MODEL_RANK.")

        # For reasoning models (deepseek-r1), need higher max_tokens
        # But keep conservative to avoid exceeding context
        # Reasoning can use 1000-2000 tokens, final answer needs ~100 tokens
        is_reasoning_model = "r1" in model_name.lower() or "reasoning" in model_name.lower()
        # Increase max_output_tokens to prevent truncation (non-reasoning models need more space for detailed analysis)
        max_output_tokens = 2000 if is_reasoning_model else 2000  # Increased from 600 to prevent truncation

        # Determine model-specific context limits based on model size
        model_max_context = self.estimate_model_max_context(model_name, is_reasoning_model)

        try:
            context_check = await self.check_model_context_length(model_name=model_name)
            detected_length = context_check["context_length"]
            detection_method = context_check.get("method", "unknown")
        except Exception as e:
            logger.warning(f"Could not get model context length: {e}")
            detected_length = model_max_context
            detection_method = "fallback"

        # If detection returned None (e.g., non-LMStudio provider skip), fall back to model_max_context
        if detected_length is None:
            detected_length = model_max_context
            detection_method = f"{detection_method}_fallback_none"

        # Trust detected context if it's reasonable (not too large, within model limits)
        # Only use very conservative caps if detection seems unreliable
        if detection_method == "environment_override":
            # Trust manual override completely
            actual_context_length = detected_length
        elif detection_method == "api_models_endpoint":
            # LMStudio reported a configured context window directly; trust it with a safety margin.
            actual_context_length = int(detected_length * 0.90)
            logger.info(f"Trusting LMStudio reported context {detected_length} for {model_name}")
        elif 4096 <= detected_length <= model_max_context:
            # Detected context is in reasonable range - trust it (with small safety margin)
            actual_context_length = int(detected_length * 0.90)  # 10% safety margin
            logger.info(f"Trusting detected context {detected_length} for {model_name} (method: {detection_method})")
        elif detected_length > model_max_context:
            # Detected context exceeds model's likely max - cap to model max
            actual_context_length = int(model_max_context * 0.90)
            logger.warning(
                f"Detected context {detected_length} exceeds model max {model_max_context}, "
                f"capping to {actual_context_length}"
            )
        else:
            # Detected context is very small or unreliable - use conservative model-specific cap
            conservative_cap = min(4096, model_max_context) if is_reasoning_model else min(2048, model_max_context)
            actual_context_length = int(conservative_cap * 0.75)  # 25% safety margin for unreliable detection
            logger.warning(
                f"Using conservative context {actual_context_length} for {model_name} "
                f"(detected: {detected_length}, method: {detection_method})"
            )

        logger.info(
            f"Using context length {actual_context_length} for truncation "
            f"(detected: {detected_length}, reasoning: {is_reasoning_model}, "
            f"model_max: {model_max_context}, method: {detection_method})"
        )

        # Estimate prompt overhead more accurately
        # Account for: template text + title + source + URL + system message + formatting
        base_prompt_tokens = self._estimate_tokens(
            prompt_template_str.format(
                title=title,
                source=source,
                url=url,
                content="",  # Estimate without content first
            )
        )
        # Add system message if present
        system_message_tokens = 50 if not self._model_needs_system_conversion(model_name) else 0
        # Add message formatting overhead (~100 tokens for JSON structure, role fields, etc.)
        message_formatting_overhead = 100
        # Total prompt overhead (not including content)
        total_prompt_overhead = base_prompt_tokens + system_message_tokens + message_formatting_overhead

        # Truncate content to fit within remaining context
        # Reserve: prompt overhead + output tokens + safety margin (15%)
        available_tokens = actual_context_length - total_prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.85)  # 15% safety margin

        if available_tokens <= 0:
            logger.error(f"Available tokens for content is {available_tokens} - prompt overhead too large")
            available_tokens = 1000  # Minimum fallback

        content_tokens = self._estimate_tokens(content)
        truncation_warning = None
        if content_tokens <= available_tokens:
            truncated_content = content
        else:
            # Truncate to fit
            max_chars = available_tokens * 4
            truncated = content[:max_chars]

            # Try to truncate at sentence boundary
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            last_boundary = max(last_period, last_newline)

            if last_boundary > max_chars * 0.8:
                truncated = truncated[: last_boundary + 1]

            truncated_content = truncated + "\n\n[Content truncated to fit context window]"

            truncation_warning = (
                f"Content truncated: {content_tokens} -> {self._estimate_tokens(truncated_content)} tokens "
                f"(available: {available_tokens}, context: {actual_context_length})"
            )
            logger.warning(
                f"Truncated article content from {content_tokens} to "
                f"{self._estimate_tokens(truncated_content)} tokens (available: {available_tokens}, "
                f"prompt overhead: {total_prompt_overhead}, max_output: {max_output_tokens}, "
                f"context: {actual_context_length})"
            )

        # Format prompt with truncated content
        prompt_text = prompt_template_str.format(title=title, source=source, url=url, content=truncated_content)

        # Final verification: estimate total prompt tokens
        total_prompt_tokens = self._estimate_tokens(prompt_text) + system_message_tokens + message_formatting_overhead
        total_tokens_needed = total_prompt_tokens + max_output_tokens
        if total_tokens_needed > actual_context_length:
            logger.error(
                f"WARNING: Total tokens needed ({total_tokens_needed}) "
                f"exceeds context length ({actual_context_length}). "
                f"This may cause context overflow errors."
            )

        # Use ranking-specific model
        model_name = self.model_rank

        # For Mistral, use direct instruction format without separate system message
        system_message = system_override or (
            "You are a cybersecurity detection engineer. "
            "Score threat intelligence articles 1-10 for SIGMA huntability. "
            "Output only a score and brief reasoning."
        )
        if self._model_needs_system_conversion(model_name):
            # Single user message with integrated instructions
            combined_prompt = f"{system_message}\n\n{prompt_text}" if system_message else prompt_text
            messages = [{"role": "user", "content": combined_prompt}]
        else:
            messages = [{"role": "system", "content": system_message}, {"role": "user", "content": prompt_text}]

        converted_messages = self._convert_messages_for_model(messages, model_name)
        logger.info(f"Ranking request: max_tokens={max_output_tokens} (reasoning_model={is_reasoning_model})")

        ranking_metadata = {
            "agent_name": "rank_article",
            "prompt_length": len(prompt_text),
            "max_tokens": max_output_tokens,
            "title": title,
            "source": source,
            "messages": messages,  # Include messages for input display
        }

        if ground_truth_rank is not None:
            ranking_metadata["ground_truth_rank"] = ground_truth_rank
        if ground_truth_details:
            ranking_metadata["ground_truth_details"] = ground_truth_details

        # Trace LLM call with Langfuse
        with trace_llm_call(
            name="rank_article",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata=ranking_metadata,
        ) as generation:
            try:
                # Reasoning models need longer timeouts - they generate extensive reasoning + answer
                ranking_timeout = 180.0 if is_reasoning_model else 60.0

                result = await self.request_chat(
                    provider=self.provider_rank,
                    model_name=model_name,
                    messages=converted_messages,
                    max_tokens=max_output_tokens,
                    temperature=self.temperature_rank,
                    timeout=ranking_timeout,
                    failure_context="Failed to rank article",
                    top_p=self.top_p_rank,
                    seed=self.seed,
                )

                # Deepseek-R1 returns reasoning in 'reasoning_content', fallback to 'content'
                message = result["choices"][0]["message"]
                response_text = message.get("content", "") or message.get("reasoning_content", "")

                # Check if response was truncated due to token limit
                finish_reason = result["choices"][0].get("finish_reason", "")
                response_truncation_warning = None
                if finish_reason == "length":
                    completion_tokens = result.get("usage", {}).get("completion_tokens", 0)
                    response_truncation_warning = (
                        f"Response truncated (finish_reason=length). "
                        f"Used {completion_tokens} tokens. "
                        f"max_tokens={max_output_tokens} may need to be increased."
                    )
                    logger.warning(
                        f"Ranking response was truncated (finish_reason=length). "
                        f"Used {completion_tokens} tokens. "
                        f"max_tokens={max_output_tokens} may need to be increased."
                    )

                # Fail if response is empty
                if not response_text or len(response_text.strip()) == 0:
                    logger.error("LLM returned empty response for ranking")
                    raise ValueError("LLM returned empty response for ranking. Check LMStudio is responding correctly.")

                logger.info(f"Ranking response received: {len(response_text)} chars (finish_reason={finish_reason})")

                # Parse score from response - look for "SIGMA HUNTABILITY SCORE: X" pattern first

                score = None

                # Try multiple patterns, searching entire response (not just first 200 chars)
                # Pattern 1: "SIGMA HUNTABILITY SCORE: X" (exact format)
                score_match = re.search(
                    r"SIGMA\s+HUNTABILITY\s+SCORE[:\s]+(\d+(?:\.\d+)?)", response_text, re.IGNORECASE
                )
                if score_match:
                    score = float(score_match.group(1))
                else:
                    # Pattern 2: "Score: X" or "**Score:** X"
                    score_match = re.search(
                        r"(?:^|\n|^|\*|#)\s*Score[:\s#*]+\s*(\d+(?:\.\d+)?)",
                        response_text,
                        re.IGNORECASE | re.MULTILINE,
                    )
                    if score_match:
                        score = float(score_match.group(1))
                    else:
                        # Pattern 2b: "Score: N/10" format
                        # Handles custom prompts that produce "Agent Value Score: 6/10" etc.
                        score_match = re.search(
                            r"Score[:\s]+(\d+(?:\.\d+)?)\s*/\s*10",
                            response_text,
                            re.IGNORECASE,
                        )
                        if score_match:
                            score = float(score_match.group(1))
                        else:
                            # Pattern 2c: Generic "N/10" anywhere in response
                            score_match = re.search(
                                r"\b(\d+(?:\.\d+)?)\s*/\s*10\b",
                                response_text,
                            )
                            if score_match:
                                score = float(score_match.group(1))
                            else:
                                # Pattern 3: Look for numbers 1-10 in the last 500 chars (where final answer usually is)
                                # Reasoning models often put the score at the end after reasoning
                                tail_text = response_text[-500:] if len(response_text) > 500 else response_text
                                score_match = re.search(r"\b([1-9]|10)(?:\.\d+)?\b", tail_text)
                                if score_match:
                                    score = float(score_match.group(1))

                if score is not None:
                    score = max(1.0, min(10.0, score))  # Clamp to 1-10
                    logger.info(f"Parsed ranking score: {score}/10")
                else:
                    # If truncated and no score found, provide helpful error
                    if finish_reason == "length":
                        error_msg = (
                            f"Ranking response was truncated and no score found. "
                            f"Response length: {len(response_text)} chars. "
                            f"Try increasing max_tokens (current: {max_output_tokens}). "
                            f"Response preview: {response_text[-300:]}"
                        )
                    else:
                        error_msg = f"Could not parse score from LLM response. Response: {response_text[:500]}"
                    logger.error(error_msg)
                    log_llm_error(generation, ValueError(error_msg))
                    raise ValueError(error_msg)

                # Log completion to Langfuse
                usage = result.get("usage", {})
                completion_metadata = {
                    "score": score,
                    "finish_reason": finish_reason,
                    "response_length": len(response_text),
                }
                if ground_truth_rank is not None:
                    completion_metadata["ground_truth_rank"] = ground_truth_rank
                if ground_truth_details:
                    completion_metadata["ground_truth_details"] = ground_truth_details

                log_llm_completion(
                    generation,
                    input_messages=messages,
                    output=response_text.strip(),
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    metadata=completion_metadata,
                    ground_truth=ground_truth_rank,
                )

                warnings = []
                if truncation_warning:
                    warnings.append(truncation_warning)
                if response_truncation_warning:
                    warnings.append(response_truncation_warning)

                return {
                    "score": score,
                    "reasoning": response_text.strip(),
                    "raw_response": response_text,
                    "warnings": warnings if warnings else None,
                }

            except Exception as e:
                logger.error(f"Error ranking article: {e}")
                if generation:
                    log_llm_error(generation, e)
                raise

    async def run_extraction_agent(
        self,
        agent_name: str,
        content: str,
        title: str,
        url: str,
        prompt_config: dict[str, Any],
        max_extraction_retries: int = 5,
        execution_id: int | None = None,
        article_id: int | None = None,
        model_name: str | None = None,
        temperature: float = 0.0,
        top_p: float | None = None,
        provider: str | None = None,
        attention_preprocessor_enabled: bool = True,
        proc_tree_attention_preprocessor_enabled: bool = True,
        langfuse_session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Run a generic extraction agent.

        Args:
            agent_name: Name of the sub-agent (e.g. "CmdlineExtract")
            content: Article content
            title: Article title
            url: Article URL
            prompt_config: Extraction prompt configuration
            max_extraction_retries: Max retries on extraction exceptions/timeouts
            provider: LLM provider to use (e.g. "lmstudio", "openai", "anthropic").
                     If None, uses self.provider_extract (from ExtractAgent_provider)

        Returns:
            Dict with extraction results
        """
        logger.info(f"Running extraction agent {agent_name} (provider={provider}, model_name={model_name})")

        # Validate content is not empty
        if not content or len(content.strip()) == 0:
            error_msg = f"Empty content provided to {agent_name}. Cannot run extraction."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate prompt_config
        if not prompt_config:
            error_msg = f"Empty prompt_config provided to {agent_name}. Cannot run extraction."
            logger.error(error_msg)
            raise ValueError(error_msg)
        _validate_extraction_prompt_config(agent_name, prompt_config)
        logger.debug(f"{agent_name} prompt_config keys: {list(prompt_config.keys())}")

        current_try = 0
        last_result = {"items": [], "count": 0}

        # Determine model to use
        # Priority: 1) provided model_name, 2) prompt_config.model, 3) ExtractAgent model, 4) error
        if not model_name:
            # Check if prompt_config has a model field (some prompts store model in config)
            model_name = prompt_config.get("model")
        if not model_name:
            model_name = self.model_extract
        if not model_name:
            raise ValueError(
                f"No model configured for {agent_name}. "
                f"Please set {agent_name}_model or ExtractAgent model in workflow config."
            )

        source = "parameter" if model_name == prompt_config.get("model") else "fallback"
        logger.info(f"{agent_name} resolved model: {model_name} (from: {source})")

        while current_try < max_extraction_retries:
            current_try += 1

            # 1. Run Extraction
            try:
                # Forensic instrumentation: track every orchestration-injected block so the
                # bundle can attribute "what came from the DB prompt" vs "what came from
                # run_extraction_agent". Reset per-attempt because retries re-render the prompt.
                orchestration_injected_sections: list[str] = []
                provider_payload_verbatim: dict[str, Any] | None = None
                provider_url: str | None = None
                post_augmentation_prompt_tokens: int = 0

                resolved_provider = (
                    provider if provider and isinstance(provider, str) and provider.strip() else self.provider_extract
                )
                if not (provider and isinstance(provider, str) and provider.strip()):
                    logger.warning(
                        f"{agent_name} provider was None/empty, "
                        f"falling back to ExtractAgent provider: {resolved_provider}. "
                        f"This may indicate the provider wasn't set in workflow config."
                    )
                effective_provider = self._canonicalize_provider(resolved_provider)
                if not effective_provider:
                    effective_provider = self._canonicalize_provider(self.provider_extract) or resolved_provider

                context_limit_tokens = self._get_context_limit(effective_provider, model_name=model_name)
                if effective_provider == "lmstudio" and model_name:
                    try:
                        context_check = await self.check_model_context_length(model_name=model_name)
                        detected_context_limit = context_check.get("context_length")
                        if isinstance(detected_context_limit, int) and detected_context_limit > 0:
                            context_limit_tokens = detected_context_limit
                            logger.info(
                                f"{agent_name} using detected LMStudio context limit "
                                f"{context_limit_tokens} for model {model_name} "
                                f"(method: {context_check.get('method', 'unknown')})"
                            )
                    except Exception as e:
                        logger.warning(
                            f"{agent_name} could not determine LMStudio context length for {model_name}: {e}"
                        )

                # Estimate actual static prompt overhead from the live prompt_config.
                # PROMPT_OVERHEAD_TOKENS (500) underestimates prompts with long instructions
                # (e.g. CmdlineExtract ~1500 tokens static overhead). Computing from the
                # actual config fields prevents context overflow on small LM Studio models.
                _static_prompt_overhead = (
                    self._estimate_tokens(prompt_config.get("system") or prompt_config.get("role", ""))
                    + self._estimate_tokens(prompt_config.get("instructions", ""))
                    + self._estimate_tokens(str(prompt_config.get("json_example") or ""))
                    + 200  # scaffold buffer: title, url, task line, format labels, traceability footer
                )

                # CmdlineExtract: optional attention preprocessor (snippets first, then full article)
                snippet_count: int | None = None
                if agent_name == "CmdlineExtract" and attention_preprocessor_enabled:
                    from src.services.cmdline_attention_preprocessor import process as preprocess_cmdline_attention

                    preprocess_result = preprocess_cmdline_attention(content, agent_name=agent_name)
                    snippets = preprocess_result.get("high_likelihood_snippets", [])
                    snippet_count = len(snippets)
                    full_article = preprocess_result.get("full_article", content)
                    logger.debug(f"Cmdline attention preprocessor enabled: True. Snippets found: {snippet_count}")

                    # Cheap mechanical invariant: byte-preserving preprocessor must not alter newline count
                    orig_nl = content.count("\n")
                    prep_nl = full_article.count("\n")
                    if abs(prep_nl - orig_nl) > 1:
                        raise PreprocessInvariantError(
                            f"{agent_name}: newline count mismatch (preprocessed={prep_nl}, original={orig_nl})",
                            debug_artifacts={
                                "agent_name": agent_name,
                                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                                "attention_preprocessor_enabled": True,
                                "execution_id": execution_id,
                                "orig_newline_count": orig_nl,
                                "prep_newline_count": prep_nl,
                            },
                        )

                    # Cap snippets to 25% of context budget (tokens) before joining.
                    # Dense articles can produce 300+ snippets; without a ceiling the
                    # snippet section crowds out the article itself (article_2068: 0/7
                    # extracted with preprocessor ON, 6/7 with it OFF).
                    # Trim from the end -- earlier snippets tend to be higher-signal.
                    if snippets:
                        max_snippet_tokens = int(context_limit_tokens * 0.25)
                        kept: list[str] = []
                        budget = max_snippet_tokens
                        for s in snippets:
                            cost = self._estimate_tokens(s) + 2  # +2 for separator
                            if cost > budget:
                                break
                            kept.append(s)
                            budget -= cost
                        snippets = kept or snippets[:1]  # always keep at least one
                        snippet_count = len(snippets)

                    snippets_section = "\n\n".join(snippets) if snippets else ""
                    snippets_header = "=== HIGH-LIKELIHOOD COMMAND SNIPPETS ===\n"
                    full_header = "\n\n=== FULL ARTICLE (REFERENCE ONLY) ===\n"
                    combined_prefix = snippets_header + snippets_section + full_header
                    orchestration_injected_sections.append("cmdline_attention_snippets_section")
                    orchestration_injected_sections.append("full_article_reference_marker")

                    # Reserve: snippets + static prompt overhead + output + buffer
                    snippet_tokens = self._estimate_tokens(combined_prefix)
                    overhead_tokens = _static_prompt_overhead + 1000 + 256  # 1000 output, 256 extra buffer
                    available_for_article = max(0, context_limit_tokens - snippet_tokens - overhead_tokens)
                    available_for_article = int(available_for_article * 0.9)  # safety margin

                    article_tokens = self._estimate_tokens(full_article)
                    if article_tokens <= available_for_article:
                        truncated_article = full_article
                    else:
                        max_chars = available_for_article * 4
                        truncated_article = full_article[:max_chars]
                        last_boundary = max(truncated_article.rfind("."), truncated_article.rfind("\n"))
                        if last_boundary > max_chars * 0.8:
                            truncated_article = truncated_article[: last_boundary + 1]
                        truncated_article = truncated_article + "\n\n[Content truncated to fit context window]"
                        orchestration_injected_sections.append("article_truncation_marker")

                    truncated_content = combined_prefix + truncated_article

                # ProcTreeExtract: optional attention preprocessor (process lineage snippets)
                elif agent_name == "ProcTreeExtract" and proc_tree_attention_preprocessor_enabled:
                    from src.services.proc_tree_attention_preprocessor import (
                        process as preprocess_proc_tree_attention,
                    )

                    preprocess_result = preprocess_proc_tree_attention(content, agent_name=agent_name)
                    snippets = preprocess_result.get("high_likelihood_snippets", [])
                    snippet_count = len(snippets)
                    full_article = preprocess_result.get("full_article", content)
                    logger.debug(f"ProcTree attention preprocessor enabled: True. Snippets found: {snippet_count}")

                    # Cheap mechanical invariant: byte-preserving preprocessor must not alter newline count
                    orig_nl = content.count("\n")
                    prep_nl = full_article.count("\n")
                    if abs(prep_nl - orig_nl) > 1:
                        raise PreprocessInvariantError(
                            f"{agent_name}: newline count mismatch (preprocessed={prep_nl}, original={orig_nl})",
                            debug_artifacts={
                                "agent_name": agent_name,
                                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                                "attention_preprocessor_enabled": True,
                                "execution_id": execution_id,
                                "orig_newline_count": orig_nl,
                                "prep_newline_count": prep_nl,
                            },
                        )

                    # Cap snippets to 25% of context budget (tokens) before joining.
                    if snippets:
                        max_snippet_tokens = int(context_limit_tokens * 0.25)
                        kept: list[str] = []
                        budget = max_snippet_tokens
                        for s in snippets:
                            cost = self._estimate_tokens(s) + 2  # +2 for separator
                            if cost > budget:
                                break
                            kept.append(s)
                            budget -= cost
                        snippets = kept or snippets[:1]  # always keep at least one
                        snippet_count = len(snippets)

                    snippets_section = "\n\n".join(snippets) if snippets else ""
                    snippets_header = "=== HIGH-LIKELIHOOD PROCESS LINEAGE SNIPPETS ===\n"
                    full_header = "\n\n=== FULL ARTICLE (REFERENCE ONLY) ===\n"
                    combined_prefix = snippets_header + snippets_section + full_header
                    orchestration_injected_sections.append("proc_tree_attention_snippets_section")
                    orchestration_injected_sections.append("full_article_reference_marker")

                    # Reserve: snippets + static prompt overhead + output + buffer
                    snippet_tokens = self._estimate_tokens(combined_prefix)
                    overhead_tokens = _static_prompt_overhead + 1000 + 256  # 1000 output, 256 extra buffer
                    available_for_article = max(0, context_limit_tokens - snippet_tokens - overhead_tokens)
                    available_for_article = int(available_for_article * 0.9)  # safety margin

                    article_tokens = self._estimate_tokens(full_article)
                    if article_tokens <= available_for_article:
                        truncated_article = full_article
                    else:
                        max_chars = available_for_article * 4
                        truncated_article = full_article[:max_chars]
                        last_boundary = max(truncated_article.rfind("."), truncated_article.rfind("\n"))
                        if last_boundary > max_chars * 0.8:
                            truncated_article = truncated_article[: last_boundary + 1]
                        truncated_article = truncated_article + "\n\n[Content truncated to fit context window]"
                        orchestration_injected_sections.append("article_truncation_marker")

                    truncated_content = combined_prefix + truncated_article
                else:
                    truncated_content = self._truncate_content(
                        content, context_limit_tokens, 1000, prompt_overhead=_static_prompt_overhead
                    )

                logger.info(
                    f"{agent_name} prompt construction: content_length={len(content)}, "
                    f"truncated_length={len(truncated_content)}, "
                    f"context_limit={context_limit_tokens}"
                )

                # Legacy format - build prompt from individual fields.
                # The extractor/QA scaffold is fixed in runtime; UI edits only affect
                # the editable prompt fields (role/objective, instructions, examples).
                # Check "objective" first (legacy key), then "task" (new envelope key).
                task = prompt_config.get("objective") or prompt_config.get("task", "Extract information.")
                instructions = prompt_config.get("instructions", "Output valid JSON.")
                output_format = json.dumps(prompt_config.get("output_format", {}), indent=2)
                json_example = prompt_config.get("json_example")
                json_example_str = ""
                if json_example:
                    json_format_instruction = (
                        "\n\nYou MUST output JSON in this exact format. "
                        "No markdown code fences, no prose, just the raw JSON object."
                    )
                    if isinstance(json_example, dict):
                        json_example_str = (
                            f"\n\nREQUIRED JSON STRUCTURE (example):\n"
                            f"{json.dumps(json_example, indent=2)}"
                            f"{json_format_instruction}"
                        )
                    else:
                        json_example_str = (
                            f"\n\nREQUIRED JSON STRUCTURE (example):\n{json_example}{json_format_instruction}"
                        )
                    orchestration_injected_sections.append("required_json_structure_example")
                    orchestration_injected_sections.append("json_format_instruction")

                user_prompt = f"""Title: {title}
URL: {url}

Content:
{truncated_content}

Task: {task}

Output Format Specification:
{output_format}{json_example_str}

CRITICAL INSTRUCTIONS: {instructions}

IMPORTANT: Your response must end with a valid JSON object matching the structure above.
If you include reasoning, place it BEFORE the JSON. The JSON must be parseable and complete.
"""
                # Forensic instrumentation: scaffold sections always present in the user message.
                # Listed in the order they appear above to mirror the wire order.
                orchestration_injected_sections.extend(
                    [
                        "title_url_header",
                        "content_block",
                        "task_line",
                        "output_format_specification",
                        "critical_instructions",
                        "important_json_reminder",
                    ]
                )

                # Append traceability requirements for observable traceability feature.
                # Simple extractors require a generic "value" identity field.
                # Structured extractors (ScheduledTasksExtract) use domain-specific identity
                # fields (task_name, task_path, trigger, etc.) in place of "value" -- the
                # injected reminder must match what the json_example schema actually specifies
                # so the LLM does not hallucinate a "value" field that is not in the contract.
                _SIMPLE_EXTRACTORS = (
                    "CmdlineExtract",
                    "ProcTreeExtract",
                    "HuntQueriesExtract",
                    "RegistryExtract",
                    "ServicesExtract",
                    "NetworkIndicatorExtract",
                )
                _STRUCTURED_EXTRACTORS = ("ScheduledTasksExtract",)
                _traceability_common = """

TRACEABILITY (REQUIRED): For each extracted item, the object MUST include these fields:
- source_evidence: The full paragraph from the article containing this observable (verbatim).
- extraction_justification: Which prompt rule or rubric triggered this extraction.
- confidence_score: A number between 0.0 and 1.0 for extraction confidence.
Every item in the output array MUST be an object (not a plain string)."""
                if user_prompt and agent_name in _SIMPLE_EXTRACTORS:
                    user_prompt = (
                        user_prompt.rstrip()
                        + _traceability_common
                        + ' The object MUST have a "value" field plus source_evidence, extraction_justification, and confidence_score.\n'
                    )
                    orchestration_injected_sections.append("traceability_common")
                    orchestration_injected_sections.append("traceability_simple_value_footer")
                elif user_prompt and agent_name in _STRUCTURED_EXTRACTORS:
                    user_prompt = (
                        user_prompt.rstrip()
                        + _traceability_common
                        + " The object MUST include the domain-specific identity fields defined in your json_example schema plus source_evidence, extraction_justification, and confidence_score.\n"
                    )
                    orchestration_injected_sections.append("traceability_common")
                    orchestration_injected_sections.append("traceability_structured_identity_footer")

                logger.debug(f"{agent_name} full user prompt length: {len(user_prompt)} chars")
                # Minimal user prefix when preset uses "user" (bulk in system, minimal in user)
                user_prefix = (prompt_config.get("user") or "").strip()
                if user_prefix:
                    user_prompt = f"{user_prefix}\n\n{user_prompt}"
                    orchestration_injected_sections.append("user_prefix")

                system_content = prompt_config.get("system") or prompt_config.get(
                    "role", "You are a detection engineer."
                )

                messages = [{"role": "system", "content": system_content}, {"role": "user", "content": user_prompt}]

                # Forensic instrumentation: count tokens in the post-augmentation payload.
                # Uses the existing heuristic estimator (chars/4); not as accurate as tiktoken/
                # anthropic.count_tokens but consistent with the rest of the budgeting code.
                post_augmentation_prompt_tokens = sum(
                    self._estimate_tokens(m.get("content", "")) for m in messages if isinstance(m, dict)
                )

                # Fail-fast: never call model with empty/malformed request
                content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
                _validate_preprocess_invariants(
                    messages,
                    agent_name=agent_name,
                    content_sha256=content_sha256,
                    attention_preprocessor_enabled=attention_preprocessor_enabled,
                    execution_id=execution_id,
                    user_prompt=user_prompt,
                )

                converted_messages = self._convert_messages_for_model(messages, model_name)

                # Reasoning models need longer timeouts - they generate extensive reasoning + answer
                is_reasoning_model = "r1" in model_name.lower() or "reasoning" in model_name.lower()
                extraction_timeout = 600.0 if is_reasoning_model else 180.0

                # Build Langfuse metadata. All extractors emit attention_preprocessor_enabled
                # (False for extractors without a preprocessor) so trace schemas line up in
                # Langfuse filters and dashboards.
                _preprocessor_flag_by_agent = {
                    "CmdlineExtract": attention_preprocessor_enabled,
                    "ProcTreeExtract": proc_tree_attention_preprocessor_enabled,
                }
                trace_metadata: dict[str, Any] = {
                    "agent_name": agent_name,
                    "attempt": current_try,
                    "prompt_length": len(user_prompt),
                    "title": title,
                    "messages": messages,  # Include messages for input display
                    "attention_preprocessor_enabled": _preprocessor_flag_by_agent.get(agent_name, False),
                }
                if agent_name in _preprocessor_flag_by_agent and snippet_count is not None:
                    trace_metadata["attention_preprocessor_snippet_count"] = snippet_count

                # Trace LLM call with Langfuse (each sub-agent gets its own trace)
                with trace_llm_call(
                    name=f"{agent_name.lower()}_extraction",
                    model=model_name,
                    execution_id=execution_id,
                    article_id=article_id,
                    session_id=langfuse_session_id,
                    metadata=trace_metadata,
                ) as generation:
                    logger.info(
                        f"{agent_name} provider resolution: provider={provider}, "
                        f"effective_provider={effective_provider}, "
                        f"self.provider_extract={self.provider_extract}"
                    )
                    # Extract subagents always use temperature=0 / top_p=None (deterministic).
                    # top_p is passed through as-is; callers that want a value provide it.
                    effective_top_p = top_p
                    logger.info(
                        f"{agent_name} extraction attempt {current_try}: "
                        f"using provider={effective_provider}, model={model_name}, "
                        f"temperature={temperature}, top_p={effective_top_p}"
                    )
                    try:
                        response = await self.request_chat(
                            provider=effective_provider,
                            model_name=model_name,
                            messages=converted_messages,
                            max_tokens=8192,
                            temperature=temperature,
                            top_p=effective_top_p,
                            timeout=extraction_timeout,
                            failure_context=f"{agent_name} extraction attempt {current_try}",
                            seed=self.seed,
                        )
                        # Forensic instrumentation: pop the wire-truth markers so they don't
                        # leak into Langfuse output or downstream response parsing.
                        if isinstance(response, dict):
                            provider_payload_verbatim = response.pop("_provider_payload", None)
                            provider_url = response.pop("_provider_url", None)
                    except Exception as e:
                        log_llm_error(
                            generation,
                            e,
                            metadata={
                                "agent_name": agent_name,
                                "attempt": current_try,
                                "model": model_name,
                            },
                        )
                        raise

                    # Parse response (moved inside with block so generation is still active)
                    response_text = response["choices"][0]["message"].get("content", "")
                    # Handle Deepseek reasoning
                    if not response_text:
                        response_text = response["choices"][0]["message"].get("reasoning_content", "")

                    # Log the actual response for debugging
                    finish_reason = response["choices"][0].get("finish_reason", "")
                    if finish_reason == "length":
                        logger.warning(
                            f"{agent_name} response truncated by max_tokens limit "
                            f"(finish_reason=length). Output JSON will be incomplete. "
                            f"Increase max_tokens in llm_service.py:extract_agent_data."
                        )
                    logger.info(f"{agent_name} raw response length: {len(response_text)} chars")
                    logger.info(f"{agent_name} response (first 1000 chars): {response_text[:1000]}")
                    logger.debug(f"{agent_name} full response: {response_text}")

                    # Log response metadata
                    if "usage" in response:
                        logger.info(f"{agent_name} token usage: {response['usage']}")

                    # Extract JSON with multiple strategies and escape sequence fixing
                    last_result = None
                    json_str = None

                    def fix_json_escapes(text: str) -> str:
                        """Fix common JSON escape sequence issues, especially Windows paths."""
                        # Pre-process: Fix patterns where models over-escape quotes

                        # Fix four backslashes + quote -> escaped quote (\\\\" -> \")
                        # In the raw text, four backslashes means: backslash + backslash + backslash + backslash
                        # We want to convert this to: backslash + quote (escaped quote)
                        text = re.sub(r'\\\\\\\\"', r'\\"', text)
                        # Fix triple backslash + quote -> escaped quote (\\\" -> \")
                        text = re.sub(r'\\\\\\"', r'\\"', text)
                        # Fix \\" patterns that are clearly wrong (two backslashes + quote -> escaped quote)
                        # This handles cases like: /tn \\"Task-... which should be /tn \"Task-...
                        # We match \\" (two backslashes + quote) and replace with \" (escaped quote)
                        # But be careful: we don't want to break Windows paths like C:\\ProgramData
                        # So we only fix \\" that appears in contexts suggesting quoted text
                        # Pattern: \\" followed by alphanumeric (opening quote)
                        # OR preceded by alphanumeric (closing quote)
                        # In regex: \\\\" means match two backslashes + quote
                        text = re.sub(r'\\\\"(?=[A-Za-z0-9])', r'\\"', text)  # Opening quotes: \\"Task -> \"Task
                        # For closing quotes, use a simpler pattern: match \\" that's not part of a path
                        # Look for \\" preceded by alphanumeric/dash/underscore and not followed by backslash
                        text = re.sub(r'([A-Za-z0-9_-])\\\\"(?!\\)', r'\1\\"', text)  # Closing quotes

                        # Strategy: Find all backslashes and check if they're properly escaped
                        # For Windows paths like C:\ProgramData, we need C:\\ProgramData in JSON
                        result = []
                        i = 0
                        while i < len(text):
                            if text[i] == "\\":
                                # Check if this is already part of a valid escape sequence
                                if i + 1 < len(text):
                                    next_char = text[i + 1]
                                    # Valid escape sequences: \\, \", \/, \b, \f, \n, \r, \t, \uXXXX
                                    if next_char == "\\":
                                        # Already escaped backslash - keep both characters and skip the next one
                                        result.append("\\\\")
                                        i += 2
                                        continue
                                    if next_char in ['"', "/", "b", "f", "n", "r", "t"]:
                                        # Valid escape sequence - keep as is
                                        result.append(text[i])
                                        i += 1
                                        continue
                                    if next_char == "u" and i + 5 < len(text):
                                        # Check if it's a valid unicode escape \uXXXX
                                        hex_chars = text[i + 2 : i + 6]
                                        if len(hex_chars) == 4 and all(
                                            c in "0123456789abcdefABCDEF" for c in hex_chars
                                        ):
                                            # Valid unicode escape - keep all 6 characters
                                            result.append(text[i : i + 6])
                                            i += 6
                                            continue
                                        # Invalid - looks like \u but not valid, double the backslash
                                        result.append("\\\\")
                                        i += 1
                                        continue
                                    # Invalid escape - double the backslash
                                    result.append("\\\\")
                                    i += 1
                                    continue
                                # Backslash at end of string - invalid, double it
                                result.append("\\\\")
                                i += 1
                                continue
                            result.append(text[i])
                            i += 1
                        return "".join(result)

                    def try_parse_json(text: str) -> tuple[dict, bool]:
                        """Try to parse JSON, return (result, success)."""
                        try:
                            return json.loads(text), True
                        except json.JSONDecodeError:
                            # Try fixing escape sequences
                            try:
                                fixed = fix_json_escapes(text)
                                return json.loads(fixed), True
                            except (json.JSONDecodeError, ValueError):
                                return None, False

                    try:
                        # Strategy 1: Try to extract from markdown code fences first

                        code_fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response_text, re.DOTALL)
                        if code_fence_match:
                            json_str = code_fence_match.group(1).strip()
                            logger.info(f"{agent_name}: Found JSON in markdown code fence")
                            parsed, success = try_parse_json(json_str)
                            if success:
                                last_result = parsed
                        else:
                            # Strategy 2: Find JSON object (first { to last })
                            start = response_text.find("{")
                            end = response_text.rfind("}")
                            if start != -1 and end != -1 and end > start:
                                json_str = response_text[start : end + 1]
                                parsed, success = try_parse_json(json_str)
                                if success:
                                    last_result = parsed
                                    logger.info(f"{agent_name}: Found JSON object from {start} to {end}")
                            else:
                                # Strategy 3: Try to find any valid JSON structure
                                # Look for all potential JSON objects and try the largest one
                                json_candidates = []
                                search_pos = 0
                                while search_pos <= len(response_text):
                                    open_pos = response_text.find("{", search_pos)
                                    if open_pos == -1:
                                        break

                                    brace_count = 0
                                    json_end = -1
                                    for i in range(open_pos, len(response_text)):
                                        if response_text[i] == "{":
                                            brace_count += 1
                                        elif response_text[i] == "}":
                                            brace_count -= 1
                                            if brace_count == 0:
                                                json_end = i + 1
                                                break

                                    if json_end != -1:
                                        candidate = response_text[open_pos:json_end]
                                        parsed, success = try_parse_json(candidate)
                                        expected_keys = [
                                            "cmdline_items",
                                            "items",
                                            "process_lineage",
                                            "sigma_queries",
                                            "registry_artifacts",
                                            "windows_services",
                                            "scheduled_tasks",
                                            "network_indicators",
                                            "count",
                                        ]
                                        if success and parsed and any(k in parsed for k in expected_keys):
                                            json_candidates.append((len(candidate), parsed))

                                    search_pos = open_pos + 1

                                if json_candidates:
                                    # Sort by length (largest first) and take the first valid one
                                    json_candidates.sort(key=lambda x: x[0], reverse=True)
                                    last_result = json_candidates[0][1]
                                    logger.info(f"{agent_name}: Found JSON from candidate search")

                        if last_result:
                            logger.info(f"{agent_name} parsed JSON keys: {list(last_result.keys())}")
                            # Check for agent-specific result keys
                            # IMPORTANT: Check for nested cmdline structure BEFORE checking cmdline_items
                            # because the LLM might return {"cmdline": {"items": []}} instead of {"cmdline_items": []}
                            if "cmdline" in last_result and isinstance(last_result["cmdline"], dict):
                                # Handle nested cmdline structure: {"cmdline": {"items": [], "count": 0}}
                                cmdline_data = last_result["cmdline"]
                                if "items" in cmdline_data:
                                    last_result["cmdline_items"] = cmdline_data["items"]
                                    if "count" in cmdline_data:
                                        last_result["count"] = cmdline_data["count"]
                                    # Remove the nested cmdline structure
                                    del last_result["cmdline"]
                                    count = len(last_result.get("cmdline_items", []))
                                    logger.info(
                                        f"{agent_name} normalized nested cmdline structure: found {count} cmdline_items"
                                    )
                                    if count == 0:
                                        logger.warning(
                                            f"{agent_name}: cmdline_items array is empty after normalization!"
                                        )
                            elif "cmdline_items" in last_result:
                                count = len(last_result.get("cmdline_items", []))
                                logger.info(f"{agent_name} found {count} cmdline_items")
                                if count == 0:
                                    logger.warning(f"{agent_name}: cmdline_items array is empty!")
                            elif "process_lineage" in last_result:
                                count = len(last_result.get("process_lineage", []))
                                logger.info(f"{agent_name} found {count} process_lineage items")
                                # Normalize to 'items' for consistency with frontend
                                last_result["items"] = last_result.pop("process_lineage")
                            elif "sigma_queries" in last_result:
                                count = len(last_result.get("sigma_queries", []))
                                logger.info(f"{agent_name} found {count} sigma_queries")
                                last_result["items"] = last_result.pop("sigma_queries")
                            elif "registry_artifacts" in last_result:
                                count = len(last_result.get("registry_artifacts", []))
                                logger.info(f"{agent_name} found {count} registry_artifacts")
                                last_result["items"] = last_result.pop("registry_artifacts")
                            elif "windows_services" in last_result:
                                count = len(last_result.get("windows_services", []))
                                logger.info(f"{agent_name} found {count} windows_services")
                                last_result["items"] = last_result.pop("windows_services")
                            elif "scheduled_tasks" in last_result:
                                count = len(last_result.get("scheduled_tasks", []))
                                logger.info(f"{agent_name} found {count} scheduled_tasks")
                                last_result["items"] = last_result.pop("scheduled_tasks")
                            elif "network_indicators" in last_result:
                                count = len(last_result.get("network_indicators", []))
                                logger.info(f"{agent_name} found {count} network_indicators")
                                last_result["items"] = last_result.pop("network_indicators")
                            elif "items" in last_result:
                                count = len(last_result.get("items", []))
                                logger.info(f"{agent_name} found {count} items")
                            else:
                                logger.warning(
                                    f"{agent_name}: No recognized items key found. Keys: {list(last_result.keys())}"
                                )
                        else:
                            # Fallback if no JSON found
                            logger.warning(
                                f"{agent_name}: No JSON found in response. Response length: {len(response_text)}"
                            )
                            logger.warning(f"{agent_name}: Response preview: {response_text[:500]}")
                            last_result = {"items": [], "count": 0, "error": "No JSON found"}

                    except Exception as e:
                        logger.warning(f"{agent_name}: Exception during JSON parsing: {e}")
                        logger.warning(f"{agent_name}: JSON string attempted: {json_str[:200] if json_str else 'None'}")
                        logger.warning(f"{agent_name}: Full response: {response_text[:1000]}")
                        last_result = {"items": [], "count": 0, "error": f"JSON parse exception: {str(e)}"}

                    # Ensure we have a result
                    if not last_result:
                        last_result = {"items": [], "count": 0, "error": "Failed to parse response"}

                    # Normalize and validate traceability on items (observable traceability feature)
                    _CONFIDENCE_LEVEL_MAP = {"high": 0.95, "medium": 0.7, "low": 0.4}

                    def _normalize_traceability_item(
                        item: Any, agent_name: str, _level_map: dict = _CONFIDENCE_LEVEL_MAP
                    ) -> Any:
                        if isinstance(item, str):
                            # Wrap plain strings into objects so confidence can be surfaced
                            return {"value": item, "confidence_score": None}
                        if not isinstance(item, dict):
                            return item
                        out = dict(item)
                        if "value" not in out and ("source_evidence" in out or "extraction_justification" in out):
                            out["value"] = (
                                out.get("command_line") or out.get("cmdline") or out.get("query") or str(item)
                            )
                        conf = out.get("confidence_score")
                        if conf is not None:
                            try:
                                f = float(conf)
                                if not (0.0 <= f <= 1.0):
                                    out["confidence_score"] = None
                            except (TypeError, ValueError):
                                out["confidence_score"] = None
                        # Fallback: map confidence_level (high/medium/low) to confidence_score
                        if out.get("confidence_score") is None and out.get("confidence_level"):
                            mapped = _level_map.get(str(out["confidence_level"]).lower())
                            if mapped is not None:
                                out["confidence_score"] = mapped
                        return out

                    for key in (
                        "cmdline_items",
                        "items",
                        "registry_artifacts",
                        "windows_services",
                        "scheduled_tasks",
                        "queries",
                        "process_lineage",
                    ):
                        if key not in last_result or not isinstance(last_result[key], list):
                            continue
                        last_result[key] = [_normalize_traceability_item(it, agent_name) for it in last_result[key]]

                    # Log completion to Langfuse with parsed result (inside with block so generation is still active)
                    if generation:
                        # Include full result for dataset/eval support - Langfuse needs complete output
                        # Use the full last_result so datasets can access all extracted items
                        output_for_langfuse = {
                            "parsed_items_count": last_result.get("count", len(last_result.get("items", []))),
                            "has_error": "error" in last_result,
                        }
                        # Include all items (not just preview) for dataset/eval support
                        if "items" in last_result:
                            output_for_langfuse["items"] = last_result["items"]
                        if "cmdline_items" in last_result:
                            output_for_langfuse["cmdline_items"] = last_result["cmdline_items"]
                        # Include any other result fields that might be useful
                        for key in [
                            "process_lineage",
                            "sigma_queries",
                            "registry_artifacts",
                            "windows_services",
                            "scheduled_tasks",
                            "network_indicators",
                        ]:
                            if key in last_result:
                                output_for_langfuse[key] = last_result[key]
                        # Include error if present
                        if "error" in last_result:
                            output_for_langfuse["error"] = last_result["error"]

                        # Create dataset-compatible input format
                        # Schema only allows article_text (additionalProperties: false)
                        dataset_input = {
                            "article_text": content[:10000]
                            if len(content) > 10000
                            else content,  # Truncate for dataset
                        }

                        log_llm_completion(
                            generation=generation,
                            input_messages=messages,
                            output=json.dumps(output_for_langfuse, indent=2),
                            usage=response.get("usage", {}),
                            metadata={
                                "agent_name": agent_name,
                                "attempt": current_try,
                                "parsed_result_keys": list(last_result.keys()),
                                "item_count": output_for_langfuse["parsed_items_count"],
                            },
                            input_object=dataset_input,  # Use dataset-compatible format
                        )

                    # Store messages and response in result for eval bundle export
                    # These are needed when Langfuse is disabled
                    last_result["_llm_messages"] = messages
                    last_result["_llm_response"] = response_text
                    last_result["_llm_attempt"] = current_try
                    # Forensic instrumentation: surface wire-truth so bundles do not
                    # require code archaeology to reconstruct what the provider saw.
                    # Field names mirror the bundle-side names (no leading underscore at
                    # bundle level); leading underscores here mark them as internal
                    # transport state on the agent_result dict.
                    last_result["_provider_payload_verbatim"] = provider_payload_verbatim
                    last_result["_provider_url"] = provider_url
                    last_result["_post_augmentation_prompt_tokens"] = post_augmentation_prompt_tokens
                    last_result["_orchestration_injected_sections"] = orchestration_injected_sections
                    # CmdlineExtract / ProcTreeExtract: surface preprocessor info for trace UI / Langfuse
                    if agent_name == "CmdlineExtract":
                        last_result["_attention_preprocessor"] = {
                            "enabled": attention_preprocessor_enabled,
                            "snippet_count": snippet_count if snippet_count is not None else 0,
                        }
                    if agent_name == "ProcTreeExtract":
                        last_result["_attention_preprocessor"] = {
                            "enabled": proc_tree_attention_preprocessor_enabled,
                            "snippet_count": snippet_count if snippet_count is not None else 0,
                        }

                return last_result

            except PreprocessInvariantError:
                raise  # Fail-fast: do not retry infra invariants
            except PromptConfigValidationError:
                raise  # Fail-fast: contract violations must surface immediately
            except ContextLengthExceededError:
                raise  # Fail-fast: context overflow is unrecoverable, retrying will not help
            except Exception as e:
                if "context_length_exceeded" in str(e):
                    raise ContextLengthExceededError(str(e)) from e
                logger.error(f"{agent_name} error on attempt {current_try}: {e}", exc_info=True)
                # On last attempt, store all API errors in result (not just connection errors)
                if current_try >= max_extraction_retries:
                    last_result = {
                        "items": [],
                        "count": 0,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "error_details": {
                            "message": str(e),
                            "exception_type": type(e).__name__,
                            "attempt": current_try,
                            "agent_name": agent_name,
                        },
                        "connection_error": "connection" in str(e).lower() or "cannot connect" in str(e).lower(),
                    }
                # Continue loop with a fresh attempt; we deliberately do not inject the
                # raw exception text into the next prompt -- transport errors (timeouts,
                # 5xx, connection drops) are not signal the LLM can act on, and seeding
                # them as "PREVIOUS FEEDBACK" misleads extraction on the retry.

        logger.warning(f"{agent_name} failed all {max_extraction_retries} attempts. Returning last result.")
        return last_result
