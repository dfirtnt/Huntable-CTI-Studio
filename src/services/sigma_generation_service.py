"""
SIGMA Rule Generation Service.

Reusable service for generating SIGMA rules from articles using LLM.
"""

import logging
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path

from src.utils.prompt_loader import format_prompt
from src.services.sigma_validator import validate_sigma_rule, clean_sigma_rule
from src.services.llm_service import LLMService
from src.utils.gpt4o_optimizer import optimize_article_content
from src.utils.langfuse_client import trace_llm_call, log_llm_completion, log_llm_error

logger = logging.getLogger(__name__)


class SigmaGenerationService:
    """Service for generating SIGMA rules from articles."""
    
    def __init__(self, config_models: Optional[Dict[str, str]] = None):
        """
        Initialize SIGMA generation service.
        
        Args:
            config_models: Optional dict of agent models from workflow config.
                          Format: {"RankAgent": "model_name", "ExtractAgent": "...", "SigmaAgent": "..."}
                          If provided, these override environment variables.
        """
        self.llm_service = LLMService(config_models=config_models)
    
    async def generate_sigma_rules(
        self,
        article_title: str,
        article_content: str,
        source_name: str,
        url: str,
        ai_model: str = 'lmstudio',
        api_key: Optional[str] = None,
        max_attempts: int = 3,
        min_confidence: float = 0.7,
        execution_id: Optional[int] = None,
        article_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate SIGMA rules from article content.
        
        Args:
            article_title: Article title
            article_content: Full article content
            source_name: Source name
            url: Article URL
            ai_model: AI model to use ('lmstudio' or 'chatgpt')
            api_key: OpenAI API key (required for ChatGPT)
            max_attempts: Maximum number of generation attempts
            min_confidence: Minimum confidence for content filtering
        
        Returns:
            Dict with 'rules' (list of validated rules), 'metadata', 'errors'
        """
        try:
            # Optimize content with filtering
            optimization_result = await optimize_article_content(
                article_content,
                min_confidence=min_confidence
            )
            
            if optimization_result['success']:
                content_to_analyze = optimization_result['filtered_content']
                logger.info(f"Content optimized: {optimization_result['tokens_saved']} tokens saved")
            else:
                content_to_analyze = article_content
                logger.warning("Content optimization failed, using original content")
            
            # Load SIGMA generation prompt (async to avoid blocking)
            from src.utils.prompt_loader import format_prompt_async
            sigma_prompt = await format_prompt_async(
                "sigma_generation",
                title=article_title,
                source=source_name,
                url=url or 'N/A',
                content=content_to_analyze
            )
            
            # Handle context window limits for LMStudio
            if ai_model == 'lmstudio':
                lmstudio_model_name = self.llm_service.lmstudio_model
                if '8b' in lmstudio_model_name.lower() or '7b' in lmstudio_model_name.lower():
                    max_prompt_chars = 12000
                elif '3b' in lmstudio_model_name.lower():
                    max_prompt_chars = 9000
                else:
                    max_prompt_chars = 8000
                
                if len(sigma_prompt) > max_prompt_chars:
                    logger.warning(f"Truncating prompt from {len(sigma_prompt)} to {max_prompt_chars} chars")
                    sigma_prompt = sigma_prompt[:max_prompt_chars] + "\n\n[Prompt truncated to fit model context window]"
            
            # Generate rules with retry logic
            validation_results = []
            rules = []
            
            for attempt in range(max_attempts):
                logger.info(f"SIGMA generation attempt {attempt + 1}/{max_attempts}")
                
                # Prepare prompt for this attempt
                if attempt == 0:
                    current_prompt = sigma_prompt
                else:
                    # Include validation feedback
                    previous_errors = []
                    previous_yaml = ""
                    for result in validation_results:
                        if not result.is_valid and result.errors:
                            previous_errors.extend(result.errors)
                        if result.content_preview:
                            previous_yaml = result.content_preview
                    
                    if previous_errors:
                        error_feedback = "\n".join(previous_errors)
                        yaml_preview = f"\n\nYOUR PREVIOUS INVALID YAML:\n{previous_yaml}\n" if previous_yaml else ""
                        
                        current_prompt = f"""VALIDATION ERRORS FROM YOUR PREVIOUS ATTEMPT:
{error_feedback}
{yaml_preview}
INSTRUCTIONS TO FIX ERRORS:

If you see "logsource must be a dictionary" error:
WRONG: logsource: Windows Event Log, Sysmon
CORRECT:
logsource:
  category: process_creation
  product: windows

If you see "detection must be a dictionary" error:
WRONG: detection: [selection, condition]
CORRECT:
detection:
  selection:
    CommandLine|contains: 'malware'
  condition: selection

Generate the corrected SIGMA rule for the article titled: "{article_title}"
Output ONLY valid YAML starting with "title:"."""
                    else:
                        break
                
                # Call LLM API
                if ai_model == 'lmstudio':
                    sigma_response = await self._call_lmstudio_for_sigma(current_prompt, execution_id=execution_id, article_id=article_id)
                else:
                    sigma_response = await self._call_openai_for_sigma(current_prompt, api_key)
                
                # Clean and validate response
                cleaned_response = clean_sigma_rule(sigma_response)
                
                # Split into individual rules
                rule_blocks = cleaned_response.split('---')
                attempt_rules = []
                
                for i, block in enumerate(rule_blocks):
                    block = block.strip()
                    if not block:
                        continue
                    
                    # Check if block looks like YAML
                    has_yaml_structure = ':' in block and any(
                        key in block for key in ['title', 'id', 'description', 'logsource', 'detection']
                    )
                    
                    if not has_yaml_structure:
                        logger.warning(f"Skipping block {i+1} - doesn't look like YAML")
                        continue
                    
                    # Validate rule
                    validation_result = validate_sigma_rule(block)
                    if validation_result.metadata is None:
                        validation_result.metadata = {}
                    validation_result.metadata['rule_index'] = i + 1
                    validation_results.append(validation_result)
                    
                    if validation_result.is_valid:
                        try:
                            parsed_yaml = yaml.safe_load(block) if block else {}
                            detection = parsed_yaml.get('detection')
                            
                            if detection and isinstance(detection, dict):
                                rule_metadata = validation_result.metadata or {}
                                rule_metadata.update({
                                    'title': parsed_yaml.get('title'),
                                    'description': parsed_yaml.get('description'),
                                    'id': parsed_yaml.get('id'),
                                    'tags': parsed_yaml.get('tags', []),
                                    'level': parsed_yaml.get('level'),
                                    'status': parsed_yaml.get('status', 'experimental'),
                                    'logsource': parsed_yaml.get('logsource', {}),
                                    'detection': detection
                                })
                                attempt_rules.append(rule_metadata)
                        except Exception as e:
                            logger.warning(f"Failed to parse validated rule: {e}")
                
                # If we got valid rules, break
                if attempt_rules:
                    rules.extend(attempt_rules)
                    break
            
            return {
                'rules': rules,
                'metadata': {
                    'total_attempts': len(validation_results),
                    'valid_rules': len(rules),
                    'validation_results': [
                        {
                            'is_valid': r.is_valid,
                            'errors': r.errors,
                            'warnings': r.warnings
                        } for r in validation_results
                    ]
                },
                'errors': None if rules else "No valid SIGMA rules could be generated"
            }
            
        except Exception as e:
            logger.error(f"Error generating SIGMA rules: {e}")
            return {
                'rules': [],
                'metadata': {},
                'errors': str(e)
            }
    
    async def _call_lmstudio_for_sigma(self, prompt: str, execution_id: Optional[int] = None, article_id: Optional[int] = None) -> str:
        """Call LMStudio API for SIGMA generation."""
        # Use SIGMA-specific model
        model_name = self.llm_service.model_sigma
        
        messages = [
                {
                    "role": "system",
                    "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries. No markdown, no explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
        ]
        
        # Convert system messages for models that don't support them (e.g., Mistral)
        messages = self.llm_service._convert_messages_for_model(messages, model_name)
        
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": 800,
            "temperature": self.llm_service.temperature,
            "top_p": self.llm_service.top_p,
        }
        
        if self.llm_service.seed is not None:
            payload["seed"] = self.llm_service.seed
        
        # Trace LLM call with LangFuse
        with trace_llm_call(
            name="generate_sigma",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata={
                "prompt_length": len(prompt),
                "max_tokens": 800
            }
        ) as generation:
            try:
                result = await self.llm_service._post_lmstudio_chat(
                    payload,
                    model_name=model_name,
                    timeout=300.0,
                    failure_context="Failed to generate SIGMA rules from LMStudio"
                )
                
                output = result['choices'][0]['message']['content']
                usage = result.get('usage', {})
                
                # Log completion to LangFuse
                log_llm_completion(
                    generation,
                    input_messages=messages,
                    output=output,
                    usage={
                        "prompt_tokens": usage.get('prompt_tokens', 0),
                        "completion_tokens": usage.get('completion_tokens', 0),
                        "total_tokens": usage.get('total_tokens', 0)
                    },
                    metadata={
                        "output_length": len(output),
                        "finish_reason": result['choices'][0].get('finish_reason', '')
                    }
                )
                
                return output
            except Exception as e:
                log_llm_error(generation, e)
                raise
    
    async def _call_openai_for_sigma(self, prompt: str, api_key: str) -> str:
        """Call OpenAI API for SIGMA generation."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries. No markdown, no explanations."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.2
                },
                timeout=120.0
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI API error: {response.status_code} - {response.text}")
            
            result = response.json()
            return result['choices'][0]['message']['content']

