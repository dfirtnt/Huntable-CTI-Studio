"""
LLM Generation Service for RAG

Provides LLM-based response generation for RAG queries using multiple providers.
Supports OpenAI, Ollama, and Anthropic Claude.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Keys used in AppSettings (Settings page) for provider API keys
_WORKFLOW_OPENAI_API_KEY = "WORKFLOW_OPENAI_API_KEY"
_WORKFLOW_ANTHROPIC_API_KEY = "WORKFLOW_ANTHROPIC_API_KEY"


def _load_app_settings_keys() -> dict[str, str | None]:
    """Load API keys from AppSettings (database). Matches llm_service behavior."""
    out: dict[str, str | None] = {}
    try:
        from src.database.manager import DatabaseManager
        from src.database.models import AppSettingsTable

        db = DatabaseManager()
        session = db.get_session()
        try:
            rows = (
                session.query(AppSettingsTable)
                .filter(AppSettingsTable.key.in_([_WORKFLOW_OPENAI_API_KEY, _WORKFLOW_ANTHROPIC_API_KEY]))
                .all()
            )
            for row in rows:
                out[row.key] = row.value
        finally:
            session.close()
    except Exception as exc:
        logger.debug("Could not load AppSettings for RAG LLM keys: %s", exc)
    return out


class LLMGenerationService:
    """Service for generating synthesized responses using various LLM providers."""

    def __init__(self):
        """Initialize the LLM generation service."""
        self._refresh_api_keys()

        # LMStudio configuration
        self.lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        self.lmstudio_model = os.getenv("LMSTUDIO_MODEL", "deepseek-r1-qwen3-8b")
        self.last_lmstudio_model: str | None = None

        logger.info("Initialized LLM Generation Service")

    def _refresh_api_keys(self) -> None:
        """Reload API keys from AppSettings + env. Call before each RAG request so Settings changes apply."""
        app = _load_app_settings_keys()
        self.openai_api_key = (
            app.get(_WORKFLOW_OPENAI_API_KEY)
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("WORKFLOW_OPENAI_API_KEY")
            or os.getenv("CHATGPT_API_KEY")
        )
        if isinstance(self.openai_api_key, str):
            self.openai_api_key = self.openai_api_key.strip() or None
        self.anthropic_api_key = (
            app.get(_WORKFLOW_ANTHROPIC_API_KEY)
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("WORKFLOW_ANTHROPIC_API_KEY")
        )
        if isinstance(self.anthropic_api_key, str):
            self.anthropic_api_key = self.anthropic_api_key.strip() or None

    async def generate_rag_response(
        self,
        query: str,
        retrieved_chunks: list[dict[str, Any]],
        conversation_history: list[dict[str, Any]] | None = None,
        provider: str = "auto",
        retrieved_rules: list[dict[str, Any]] | None = None,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a synthesized response using retrieved chunks.

        Args:
            query: User's original query
            retrieved_chunks: List of retrieved article chunks
            conversation_history: Previous conversation context
            provider: LLM provider ("openai", "anthropic", "ollama", "auto")
            retrieved_rules: List of retrieved Sigma rules

        Returns:
            Dictionary with generated response and metadata
        """
        try:
            self._refresh_api_keys()

            # Build context from retrieved chunks and rules
            context = self._build_context(retrieved_chunks, retrieved_rules)

            # Create conversation context
            conversation_context = self._build_conversation_context(conversation_history)

            # Generate prompt
            system_prompt, user_prompt = self._create_rag_prompt(query, context, conversation_context)

            requested_provider = self._canonicalize_requested_provider(provider)

            # Select provider after applying fallbacks
            selected_provider = self._select_provider(provider)

            # Get model metadata
            model_name = self._get_model_name(selected_provider)
            model_display_name = self._build_model_display(
                selected_provider,
                model_name,
                requested_provider,
            )

            # Generate response
            response = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=selected_provider,
                model_override=model_override,
            )

            # If LMStudio returned a specific model name, prefer it for display
            if selected_provider == "lmstudio" and self.last_lmstudio_model:
                model_name = self.last_lmstudio_model
                model_display_name = self._build_model_display(
                    selected_provider,
                    model_name,
                    requested_provider,
                )

            return {
                "response": response,
                "provider": selected_provider,
                "model_name": model_name,
                "model_display_name": model_display_name,
                "chunks_used": len(retrieved_chunks),
                "rules_used": len(retrieved_rules) if retrieved_rules else 0,
                "context_length": len(context),
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to generate RAG response: {e}")
            raise

    def _build_context(
        self,
        retrieved_chunks: list[dict[str, Any]],
        retrieved_rules: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build context string from retrieved chunks and Sigma rules."""
        context_parts = []

        # Add article sources
        for i, chunk in enumerate(retrieved_chunks, 1):
            title = chunk.get("title", "Unknown Title")
            source = chunk.get("source_name", "Unknown Source")
            content = chunk.get("content", "")
            url = chunk.get("canonical_url", "")
            similarity = chunk.get("similarity", 0.0)

            context_parts.append(
                f"Source {i}: {title} (from {source})\nRelevance: {similarity:.1%}\nContent: {content}\nURL: {url}\n"
            )

        # Add Sigma rule sources
        if retrieved_rules:
            context_parts.append("\n--- SIGMA DETECTION RULES ---\n")
            for i, rule in enumerate(retrieved_rules, 1):
                rule_id = rule.get("rule_id", rule.get("id", "Unknown"))
                title = rule.get("title", "Unknown Rule")
                description = rule.get("description", "")
                level = rule.get("level", "unknown")
                status = rule.get("status", "unknown")
                tags = rule.get("tags", [])
                similarity = rule.get("similarity", 0.0)

                # Build URL to view rule details
                rule_url = f"/sigma-rules/{rule_id}"

                context_parts.append(
                    f"SIGMA Rule {i}: {title}\n"
                    f"ID: {rule_id}\n"
                    f"Relevance: {similarity:.1%}\n"
                    f"Level: {level} | Status: {status}\n"
                    f"Tags: {', '.join(tags) if tags else 'None'}\n"
                    f"Description: {description}\n"
                    f"View Rule: {rule_url}\n"
                )

        return "\n".join(context_parts)

    def _build_conversation_context(self, conversation_history: list[dict[str, Any]] | None) -> str:
        """Build conversation context from history."""
        if not conversation_history:
            return ""

        context_parts = []
        recent_turns = conversation_history[-4:]  # Last 4 turns

        for turn in recent_turns:
            role = turn.get("role", "")
            content = turn.get("content", "")

            if role == "user":
                context_parts.append(f"User: {content}")
            elif role == "assistant":
                # Truncate long responses
                truncated_content = content[:200] + "..." if len(content) > 200 else content
                context_parts.append(f"Assistant: {truncated_content}")

        return "\n".join(context_parts)

    def _create_rag_prompt(self, query: str, context: str, conversation_context: str) -> tuple[str, str]:
        """Create system and user prompts for RAG generation."""

        system_prompt = """SYSTEM PROMPT — Huntable Analyst (RAG Chat Completion)

You are **Huntable Analyst**, a Retrieval-Augmented Cyber Threat Intelligence assistant.
You analyze retrieved CTI article content and Sigma detection rules to answer user questions about threat behavior, TTPs, and detection engineering.

== Core Behavior ==
1. Extract technical signals: process names, command lines, registry paths, API calls, network indicators, telemetry types.
2. Provide detection insight: relevant Sysmon EventIDs, Windows Security events, or Sigma rule elements.
3. Rate confidence as **High / Medium / Low** based on textual support.
4. **IMPORTANT**: When referencing Sigma rules, ALWAYS include clickable links using the format provided in the context.

== Output Template ==
**Answer:** factual synthesis from retrieved sources.
**Evidence:** article titles or source IDs with one-line justification.
**Detection Notes:** Sigma-style cues (EventIDs, keywords, log sources).
**Relevant Sigma Rules:** When Sigma rules are provided in context, list them with their clickable links (e.g., "[Rule Title](/sigma-rules/rule_id)").
**Confidence:** High / Medium / Low.
**If context insufficient:** say so and suggest refined query terms.

== Referencing Sources ==
- For articles: Include the article title and URL provided in context
- For Sigma rules: Include the rule title as a clickable link using the "/sigma-rules/{rule_id}" format shown in context
- Always provide links to allow users to explore the full source material

== Conversation Memory ==
- Modern models (GPT-4o-mini: 128k, Claude Haiku: 200k) retain extensive dialogue history
- Reference prior context naturally when relevant
- Maintain conversation continuity across many turns
- Only summarize when explicitly requested or context approaches limits"""

        user_prompt_parts = [f"Question: {query}\n"]

        if conversation_context:
            user_prompt_parts.append(f"Previous conversation:\n{conversation_context}\n")

        user_prompt_parts.append(f"Relevant threat intelligence sources:\n{context}")

        user_prompt = "\n".join(user_prompt_parts)

        return system_prompt, user_prompt

    def _get_model_name(self, provider: str) -> str:
        """Get the actual model name for the provider."""
        if provider == "openai":
            return "gpt-4o-mini"
        if provider == "anthropic":
            return "claude-sonnet-4-5"
        if provider == "tinyllama":
            return "tinyllama"
        if provider == "lmstudio":
            # Try to get from database settings first, fallback to env var
            try:
                from sqlalchemy import select

                from src.database.manager import DatabaseManager
                from src.database.models import AppSettingsTable

                db_manager = DatabaseManager()
                db_session = db_manager.get_session()
                try:
                    setting = db_session.execute(
                        select(AppSettingsTable).where(AppSettingsTable.key == "lmstudio_model")
                    ).scalar_one_or_none()
                    if setting and setting.value:
                        return setting.value
                finally:
                    db_session.close()
            except Exception as e:
                logger.debug(f"Could not fetch lmstudio_model from database: {e}, using env var")
            # Fallback to environment variable or default
            return self.lmstudio_model
        return "template"

    def _canonicalize_requested_provider(self, provider: str | None) -> str:
        """Normalize requested provider aliases without applying fallbacks."""
        normalized = (provider or "").lower().strip()
        alias_map = {
            "chatgpt": "openai",
            "openai": "openai",
            "gpt4o": "openai",
            "gpt-4o": "openai",
            "gpt-4o-mini": "openai",
            "claude": "anthropic",
            "claude-haiku": "anthropic",
            "claude3": "anthropic",
            "anthropic": "anthropic",
            "tinyllama": "tinyllama",
            "lmstudio": "lmstudio",
            "template": "template",
            "disabled": "template",
            "none": "template",
        }
        if normalized in alias_map:
            return alias_map[normalized]
        if normalized == "":
            return "auto"
        return normalized

    def _format_provider_name(self, provider: str) -> str:
        """Return human-friendly provider label."""
        mapping = {
            "openai": "OpenAI",
            "anthropic": "Claude",
            "tinyllama": "Ollama",
            "lmstudio": "LM Studio",
            "template": "Template",
            "auto": "Auto",
        }
        return mapping.get(provider, provider.title())

    def _build_model_display(
        self,
        provider: str,
        model_name: str | None,
        requested_provider: str | None = None,
    ) -> str:
        """Build a user-facing display label for the resolved model."""
        base_provider = provider
        detail = model_name or ""

        if provider == "tinyllama":
            base_provider = "lmstudio"
            detail = "tinyllama"
        elif provider == "lmstudio":
            detail = model_name or self.lmstudio_model or "local-model"
        elif provider == "template":
            base_provider = "template"
            detail = ""
        elif provider == "openai":
            detail = model_name or "gpt-4o-mini"
        elif provider == "anthropic":
            detail = model_name or "claude-sonnet-4-5"

        provider_label = self._format_provider_name(base_provider)
        detail = detail.strip()
        display = f"{provider_label} • {detail}" if detail else provider_label

        normalized_requested = None if requested_provider in {None, "", "auto"} else requested_provider
        if normalized_requested and normalized_requested != provider:
            display = f"{display} (fallback from {self._format_provider_name(normalized_requested)})"

        return display

    def _select_provider(self, provider: str) -> str:
        """Select the effective LLM provider with graceful fallbacks."""
        normalized = self._canonicalize_requested_provider(provider)

        if normalized in {"template", "disabled", "none"}:
            return "template"

        if normalized == "openai":
            if self.openai_api_key:
                return "openai"
            raise ValueError("OpenAI provider requested but API key is missing")

        if normalized == "anthropic":
            if self.anthropic_api_key:
                return "anthropic"
            raise ValueError("Anthropic provider requested but API key is missing")

        if normalized == "tinyllama":
            return "tinyllama"

        if normalized == "ollama":
            return "ollama"

        if normalized == "lmstudio":
            return "lmstudio"

        if normalized == "auto":
            return self._fallback_provider(set())

        logger.warning("Unknown provider '%s'; falling back to default", provider)
        return self._fallback_provider(set())

    def _fallback_provider(self, excluded: set[str]) -> str:
        """Choose best available provider excluding the given set."""
        if self.openai_api_key and "openai" not in excluded:
            return "openai"

        if self.anthropic_api_key and "anthropic" not in excluded:
            return "anthropic"

        if self.lmstudio_model and self.lmstudio_model != "local-model" and "lmstudio" not in excluded:
            return "lmstudio"

        return "lmstudio"

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: str,
        model_override: str | None = None,
    ) -> str:
        """Call the specified LLM provider."""
        model = (model_override or "").strip() or None

        if provider == "openai":
            return await self._call_openai(system_prompt, user_prompt, model=model)
        if provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt, model=model)
        if provider == "lmstudio":
            return await self._call_lmstudio(system_prompt, user_prompt, model=model)
        raise ValueError(f"Unknown provider: {provider}")

    async def _call_openai(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call OpenAI API via shared openai_chat_client (RAG, Enrichment, etc.)."""
        from src.services.openai_chat_client import openai_chat_completions

        if not self.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        model_name = (model or "").strip() or "gpt-4o-mini"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await openai_chat_completions(
            api_key=self.openai_api_key,
            model_name=model_name,
            messages=messages,
            max_tokens=2000,
            temperature=0.3,
            timeout=60.0,
        )

    async def _call_anthropic(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call Anthropic Claude API with rate limit handling and exponential backoff."""
        return await self._call_anthropic_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=5,
            base_delay=1.0,
            max_delay=60.0,
            model_override=model,
        )

    async def _call_anthropic_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        model_override: str | None = None,
    ) -> str:
        """
        Call Anthropic Claude API with exponential backoff rate limit handling.

        Args:
            system_prompt: System prompt for Claude
            user_prompt: User prompt/messages
            max_retries: Maximum retry attempts
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay cap (seconds)
            headers: Optional custom headers (defaults to standard Anthropic headers)
            payload: Optional custom payload (defaults to standard Anthropic payload)

        Returns:
            Response text from Claude

        Raises:
            ValueError: If API key not configured
            RuntimeError: If all retries exhausted or non-retryable error
        """
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        # Default headers
        if headers is None:
            headers = {
                "x-api-key": self.anthropic_api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }

        # Default payload
        if payload is None:
            model_name = (model_override or "").strip() or "claude-sonnet-4-5"
            payload = {
                "model": model_name,
                "max_tokens": 2000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }

        last_exception = None

        for attempt in range(max_retries):
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload,
                        timeout=60.0,
                    )

                    # Success
                    if response.status_code == 200:
                        result = response.json()
                        return result["content"][0]["text"]

                    # Rate limit (429) - retry with exponential backoff
                    if response.status_code == 429:
                        retry_after = self._parse_retry_after(response.headers.get("retry-after"))

                        # Use exponential backoff with retry-after as minimum
                        delay = max(retry_after, base_delay * (2**attempt))
                        delay = min(delay, max_delay)

                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API rate limited (429). "
                                f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s. "
                                f"Retry-After header: {retry_after}s"
                            )
                            await asyncio.sleep(delay)
                            continue
                        error_detail = response.text
                        logger.error(f"Anthropic API rate limit exceeded after {max_retries} attempts: {error_detail}")
                        raise RuntimeError(f"Anthropic API rate limit exceeded: {error_detail}")

                    # Other errors - retry with exponential backoff for 5xx, fail fast for 4xx
                    if 500 <= response.status_code < 600:
                        delay = min(base_delay * (2**attempt), max_delay)
                        if attempt < max_retries - 1:
                            error_detail = response.text
                            logger.warning(
                                f"Anthropic API server error ({response.status_code}). "
                                f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {error_detail}"
                            )
                            await asyncio.sleep(delay)
                            continue

                    # Client errors (4xx) - don't retry
                    error_detail = response.text
                    logger.error(f"Anthropic API client error ({response.status_code}): {error_detail}")
                    raise RuntimeError(f"Anthropic API error ({response.status_code}): {error_detail}")

                except httpx.TimeoutException as e:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(f"Anthropic API timeout. Retry {attempt + 1}/{max_retries} after {delay:.1f}s")
                        await asyncio.sleep(delay)
                        last_exception = e
                        continue
                    raise RuntimeError(f"Anthropic API timeout after {max_retries} attempts") from e

                except Exception as e:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Anthropic API error: {e}. Retry {attempt + 1}/{max_retries} after {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)
                        last_exception = e
                        continue
                    raise RuntimeError(f"Anthropic API error after {max_retries} attempts: {e}") from e

        # Should not reach here, but handle edge case
        if last_exception:
            raise RuntimeError(f"Anthropic API failed after {max_retries} attempts") from last_exception
        raise RuntimeError(f"Anthropic API failed after {max_retries} attempts")

    def _parse_retry_after(self, retry_after_header: str | None) -> float:
        """
        Parse retry-after header value.

        Handles:
        - Integer seconds: "30"
        - HTTP date format: "Wed, 21 Oct 2015 07:28:00 GMT"

        Args:
            retry_after_header: Value from retry-after header

        Returns:
            Seconds to wait (default: 30.0 if parsing fails)
        """
        if not retry_after_header:
            return 30.0

        try:
            # Try integer seconds first
            return float(retry_after_header.strip())
        except ValueError:
            # Try HTTP date format
            try:
                from email.utils import parsedate_to_datetime

                retry_date = parsedate_to_datetime(retry_after_header)
                now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                delta = retry_date - now
                return max(0.0, delta.total_seconds())
            except (ValueError, TypeError):
                logger.warning(f"Could not parse retry-after header: {retry_after_header}, using 30s default")
                return 30.0

    async def _call_lmstudio(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call LMStudio API (OpenAI-compatible) with recommended settings."""
        # Get recommended settings (temperature 0.0 for deterministic scoring, top_p 0.9, seed 42)
        temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
        seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None
        model_name = (model or "").strip() or self.lmstudio_model

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 2000,
            "temperature": temperature,
            "top_p": top_p,
        }
        if seed is not None:
            payload["seed"] = seed

        async with httpx.AsyncClient() as client:
            # For LM Studio, read timeout must be long enough to allow prompt processing
            # before any response data is sent.
            read_timeout = 600.0
            response = await client.post(
                f"{self.lmstudio_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=httpx.Timeout(120.0, connect=30.0, read=read_timeout),
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"LMStudio API error: {error_detail}")
                raise RuntimeError(f"LMStudio API error: {error_detail}")

            result = response.json()
            # Capture actual model used by LMStudio for accurate UI display
            self.last_lmstudio_model = result.get("model") or self.lmstudio_model
            return result["choices"][0]["message"]["content"]

    def get_available_providers(self) -> list[str]:
        """Get list of available LLM providers."""
        providers = []

        if self.openai_api_key:
            providers.append("openai")

        if self.anthropic_api_key:
            providers.append("anthropic")

        providers.append("lmstudio")  # Always available if LMStudio is running

        return providers


# Global instance
_llm_generation_service = None


def get_llm_generation_service() -> LLMGenerationService:
    """Get the global LLM generation service instance."""
    global _llm_generation_service
    if _llm_generation_service is None:
        _llm_generation_service = LLMGenerationService()
    return _llm_generation_service
