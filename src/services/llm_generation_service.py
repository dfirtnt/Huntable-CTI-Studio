"""
LLM Generation Service for RAG

Provides LLM-based response generation for RAG queries using multiple providers.
Supports OpenAI, Ollama, and Anthropic Claude.
"""

import os
import logging
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMGenerationService:
    """Service for generating synthesized responses using various LLM providers."""
    
    def __init__(self):
        """Initialize the LLM generation service."""
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.ollama_url = os.getenv("LLM_API_URL", "http://cti_ollama:11434")
        self.ollama_model = os.getenv("LLM_MODEL", "llama3.2:1b")
        
        # LMStudio configuration
        self.lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        self.lmstudio_model = os.getenv("LMSTUDIO_MODEL", "meta-llama-3.1-8b-instruct")
        
        logger.info("Initialized LLM Generation Service")
    
    async def generate_rag_response(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        provider: str = "auto"
    ) -> Dict[str, Any]:
        """
        Generate a synthesized response using retrieved chunks.
        
        Args:
            query: User's original query
            retrieved_chunks: List of retrieved article chunks
            conversation_history: Previous conversation context
            provider: LLM provider ("openai", "anthropic", "ollama", "auto")
            
        Returns:
            Dictionary with generated response and metadata
        """
        try:
            # Build context from retrieved chunks
            context = self._build_context(retrieved_chunks)
            
            # Create conversation context
            conversation_context = self._build_conversation_context(conversation_history)
            
            # Generate prompt
            system_prompt, user_prompt = self._create_rag_prompt(
                query, context, conversation_context
            )
            
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
                provider=selected_provider
            )
            
            return {
                "response": response,
                "provider": selected_provider,
                "model_name": model_name,
                "model_display_name": model_display_name,
                "chunks_used": len(retrieved_chunks),
                "context_length": len(context),
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate RAG response: {e}")
            raise
    
    def _build_context(self, retrieved_chunks: List[Dict[str, Any]]) -> str:
        """Build context string from retrieved chunks."""
        context_parts = []
        
        for i, chunk in enumerate(retrieved_chunks, 1):
            title = chunk.get('title', 'Unknown Title')
            source = chunk.get('source_name', 'Unknown Source')
            content = chunk.get('content', '')
            url = chunk.get('canonical_url', '')
            similarity = chunk.get('similarity', 0.0)
            
            context_parts.append(
                f"Source {i}: {title} (from {source})\n"
                f"Relevance: {similarity:.1%}\n"
                f"Content: {content}\n"
                f"URL: {url}\n"
            )
        
        return "\n".join(context_parts)
    
    def _build_conversation_context(self, conversation_history: Optional[List[Dict[str, Any]]]) -> str:
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
    
    def _create_rag_prompt(
        self, 
        query: str, 
        context: str, 
        conversation_context: str
    ) -> tuple[str, str]:
        """Create system and user prompts for RAG generation."""
        
        system_prompt = """SYSTEM PROMPT — Huntable Analyst (RAG Chat Completion)

You are **Huntable Analyst**, a Retrieval-Augmented Cyber Threat Intelligence assistant.  
You analyze retrieved CTI article content to answer user questions about threat behavior, TTPs, and detection engineering.

== Core Behavior ==
1. Extract technical signals: process names, command lines, registry paths, API calls, network indicators, telemetry types.
2. Provide detection insight: relevant Sysmon EventIDs, Windows Security events, or Sigma rule elements.
3. Rate confidence as **High / Medium / Low** based on textual support.

== Output Template ==
**Answer:** factual synthesis from retrieved sources.  
**Evidence:** article titles or source IDs with one-line justification.  
**Detection Notes:** Sigma-style cues (EventIDs, keywords, log sources).  
**Confidence:** High / Medium / Low.  
**If context insufficient:** say so and suggest refined query terms.

== Conversation Memory ==
- Modern models (GPT-4o-mini: 128k, Claude Haiku: 200k) retain extensive dialogue history
- Reference prior context naturally when relevant
- Maintain conversation continuity across many turns
- Only summarize when explicitly requested or context approaches limits"""

        user_prompt_parts = [
            f"Question: {query}\n"
        ]
        
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
        if provider == "ollama":
            return self.ollama_model
        if provider == "tinyllama":
            return "tinyllama"
        if provider == "lmstudio":
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
            "ollama": "ollama",
            "llama": "ollama",
            "llama3": "ollama",
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
            "ollama": "Ollama",
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
            base_provider = "ollama"
            detail = "tinyllama"
        elif provider == "ollama":
            detail = model_name or self.ollama_model or "ollama-model"
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

        normalized_requested = (
            None if requested_provider in {None, "", "auto"} else requested_provider
        )
        if normalized_requested and normalized_requested != provider:
            display = (
                f"{display} (fallback from {self._format_provider_name(normalized_requested)})"
            )

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

        if (
            self.lmstudio_model
            and self.lmstudio_model != "local-model"
            and "lmstudio" not in excluded
        ):
            return "lmstudio"

        if "tinyllama" not in excluded and self.ollama_model == "tinyllama":
            return "tinyllama"

        return "ollama"
    
    async def _call_llm(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        provider: str
    ) -> str:
        """Call the specified LLM provider."""
        
        if provider == "openai":
            return await self._call_openai(system_prompt, user_prompt)
        elif provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt)
        elif provider == "ollama":
            return await self._call_ollama(system_prompt, user_prompt)
        elif provider == "tinyllama":
            return await self._call_ollama_with_model(system_prompt, user_prompt, "tinyllama")
        elif provider == "lmstudio":
            return await self._call_lmstudio(system_prompt, user_prompt)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI API."""
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise RuntimeError(f"OpenAI API error: {error_detail}")
            
            result = response.json()
            return result['choices'][0]['message']['content']
    
    async def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Call Anthropic Claude API."""
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 2000,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ]
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"Anthropic API error: {error_detail}")
                raise RuntimeError(f"Anthropic API error: {error_detail}")
            
            result = response.json()
            return result['content'][0]['text']
    
    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Call local Ollama API."""
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 2000
                    }
                },
                timeout=120.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"Ollama API error: {error_detail}")
                raise RuntimeError(f"Ollama API error: {error_detail}")
            
            result = response.json()
            return result['response']
    
    async def _call_ollama_with_model(self, system_prompt: str, user_prompt: str, model_name: str) -> str:
        """Call Ollama API with specific model."""
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 2000
                    }
                },
                timeout=120.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"Ollama API error for {model_name}: {error_detail}")
                raise RuntimeError(f"Ollama API error for {model_name}: {error_detail}")
            
            result = response.json()
            return result['response']
    
    async def _call_lmstudio(self, system_prompt: str, user_prompt: str) -> str:
        """Call LMStudio API (OpenAI-compatible)."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.lmstudio_url}/chat/completions",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.lmstudio_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=120.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"LMStudio API error: {error_detail}")
                raise RuntimeError(f"LMStudio API error: {error_detail}")
            
            result = response.json()
            return result['choices'][0]['message']['content']
    
    def get_available_providers(self) -> List[str]:
        """Get list of available LLM providers."""
        providers = []
        
        if self.openai_api_key:
            providers.append("openai")
        
        if self.anthropic_api_key:
            providers.append("anthropic")
        
        providers.append("ollama")  # Always available if Ollama is running
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
