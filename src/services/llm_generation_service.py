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
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or "sk-__JQEX6tg6SSKxcOtqnIj85Jl_SN8FxJBq4XmmeSAtT3BlbkFJYVkz3kCxA93viNKE93bdO3elUwbYg9AR1hYuNBePcA"
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.ollama_url = os.getenv("LLM_API_URL", "http://cti_ollama:11434")
        self.ollama_model = os.getenv("LLM_MODEL", "llama3.2:1b")
        
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
            
            # Select provider
            selected_provider = self._select_provider(provider)
            
            # Generate response
            response = await self._call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=selected_provider
            )
            
            return {
                "response": response,
                "provider": selected_provider,
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
1. Ground every statement in retrieved text. Never hallucinate.
2. If retrieval lacks support, say: "No evidence found in retrieved articles."
3. Extract technical signals: process names, command lines, registry paths, API calls, network indicators, telemetry types.
4. Map behavior to MITRE ATT&CK techniques when possible.
5. Provide detection insight: relevant Sysmon EventIDs, Windows Security events, or Sigma rule elements.
6. Rate confidence as **High / Medium / Low** based on textual support.
7. Write concisely—one short paragraph per section.

== Output Template ==
**Answer:** factual synthesis from retrieved sources.  
**Evidence:** article titles or source IDs with one-line justification.  
**Detection Notes:** Sigma-style cues (EventIDs, keywords, log sources).  
**Confidence:** High / Medium / Low.  
**If context insufficient:** say so and suggest refined query terms.

== Conversation Memory ==
- Assume model retains last ~6–8k tokens of dialogue.  
- Re-reference prior context briefly when relevant.  
- Stay consistent across turns; summarize only when asked."""

        user_prompt_parts = [
            f"Question: {query}\n"
        ]
        
        if conversation_context:
            user_prompt_parts.append(f"Previous conversation:\n{conversation_context}\n")
        
        user_prompt_parts.append(f"Relevant threat intelligence sources:\n{context}")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        return system_prompt, user_prompt
    
    def _select_provider(self, provider: str) -> str:
        """Select the best available LLM provider."""
        if provider == "auto":
            if self.openai_api_key:
                return "openai"
            elif self.anthropic_api_key:
                return "anthropic"
            else:
                return "ollama"
        
        return provider
    
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
                    "model": "gpt-4o",
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
                    "model": "claude-3-haiku-20240307",
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
    
    def get_available_providers(self) -> List[str]:
        """Get list of available LLM providers."""
        providers = []
        
        if self.openai_api_key:
            providers.append("openai")
        
        if self.anthropic_api_key:
            providers.append("anthropic")
        
        providers.append("ollama")  # Always available if Ollama is running
        
        return providers


# Global instance
_llm_generation_service = None


def get_llm_generation_service() -> LLMGenerationService:
    """Get the global LLM generation service instance."""
    global _llm_generation_service
    if _llm_generation_service is None:
        _llm_generation_service = LLMGenerationService()
    return _llm_generation_service
