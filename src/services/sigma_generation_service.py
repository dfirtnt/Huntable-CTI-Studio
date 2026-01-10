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
from src.utils.llm_optimizer import optimize_article_content
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
        article_id: Optional[int] = None,
        qa_feedback: Optional[str] = None,
        sigma_prompt_template: Optional[str] = None
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
            # Use provided template from database if available, otherwise load from file
            sigma_prompt = None
            if sigma_prompt_template:
                # Format the database prompt template with article data
                try:
                    sigma_prompt = sigma_prompt_template.format(
                        title=article_title,
                        source=source_name,
                        url=url or 'N/A',
                        content=content_to_analyze
                    )
                    logger.info(f"Using database prompt template for SIGMA generation (len={len(sigma_prompt)} chars)")
                except (KeyError, AttributeError, ValueError) as e:
                    logger.warning(f"Database prompt template formatting failed ({e}), falling back to file")
                    sigma_prompt = None  # Ensure it's None so we fall through to file loading
            
            if not sigma_prompt:
                # Fallback to file-based prompt
                from src.utils.prompt_loader import format_prompt_async
                sigma_prompt = await format_prompt_async(
                    "sigma_generation",
                    title=article_title,
                    source=source_name,
                    url=url or 'N/A',
                    content=content_to_analyze
                )
                logger.info(f"Using file-based prompt for SIGMA generation (len={len(sigma_prompt)} chars)")
            
            # Ensure we have a valid prompt
            if not sigma_prompt or not isinstance(sigma_prompt, str):
                raise ValueError("Failed to load SIGMA generation prompt from both database and file")
            
            # Handle context window limits for LMStudio
            if ai_model == 'lmstudio':
                lmstudio_model_name = self.llm_service.lmstudio_model
                if not lmstudio_model_name or not isinstance(lmstudio_model_name, str):
                    logger.warning(f"lmstudio_model is None or not a string: {lmstudio_model_name}, using default context window")
                    max_prompt_chars = 8000
                elif '8b' in lmstudio_model_name.lower() or '7b' in lmstudio_model_name.lower():
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
            conversation_log = []
            previous_errors_text = None
            previous_yaml_preview = ""
            
            for attempt in range(max_attempts):
                logger.info(f"SIGMA generation attempt {attempt + 1}/{max_attempts}")
                
                # Initialize attempt-specific variables
                attempt_rules = []
                attempt_validation_results = []
                all_valid = True
                
                feedback_prefix = ""
                if attempt > 0:
                    # Use the sigma_feedback template for structured feedback
                    try:
                        feedback_template = await format_prompt_async(
                            "sigma_feedback",
                            validation_errors=previous_errors_text or "No valid SIGMA YAML detected. Output strictly valid SIGMA YAML starting with 'title:' using 2-space indentation.",
                            original_rule=previous_yaml_preview or "No YAML was detected in the previous attempt."
                        )
                        feedback_prefix = feedback_template
                    except Exception as e:
                        # Fallback to simple feedback if template loading fails
                        logger.warning(f"Failed to load sigma_feedback template, using simple feedback: {e}")
                        feedback_parts = []
                        if previous_errors_text:
                            feedback_parts.append(f"Previous validation errors:\n{previous_errors_text}")
                        else:
                            feedback_parts.append(
                                "Previous attempt failed validation or produced no YAML. "
                                "Output strictly valid SIGMA YAML starting with 'title:' using 2-space indentation."
                            )
                        if previous_yaml_preview:
                            feedback_parts.append(f"Previous YAML attempt:\n{previous_yaml_preview}")
                        feedback_prefix = "\n\n".join(feedback_parts)
                
                # Prepare prompt for this attempt
                if feedback_prefix:
                    current_prompt = f"{feedback_prefix}\n\n{sigma_prompt}"
                else:
                    current_prompt = sigma_prompt
                
                # Add QA feedback if provided (only on first attempt)
                if attempt == 0 and qa_feedback:
                    current_prompt = f"{qa_feedback}\n\n{current_prompt}"
                
                # Call LLM API
                try:
                    sigma_provider = self.llm_service.provider_sigma
                    requested_provider = self.llm_service._canonicalize_provider(ai_model)
                    if ai_model and ai_model != 'lmstudio' and requested_provider != 'lmstudio':
                        sigma_provider = requested_provider
                    sigma_response = await self._call_provider_for_sigma(
                        current_prompt,
                        provider=sigma_provider,
                        execution_id=execution_id,
                        article_id=article_id
                    )
                    
                    # Ensure we have a response (even if empty, store it as string)
                    if sigma_response is None:
                        sigma_response = ""
                    else:
                        sigma_response = str(sigma_response)
                    
                    logger.info(f"SIGMA generation attempt {attempt + 1}: Received response ({len(sigma_response)} chars)")
                except Exception as e:
                    # Log error in conversation log
                    logger.error(f"SIGMA generation attempt {attempt + 1} failed: {e}")
                    conversation_log.append({
                        'attempt': attempt + 1,
                        'messages': [
                            {
                                'role': 'system',
                                'content': 'You are a senior cybersecurity detection engineer specializing in SIGMA rule creation.'
                            },
                            {
                                'role': 'user',
                                'content': current_prompt
                            }
                        ],
                        'llm_response': None,
                        'validation': [],
                        'all_valid': False,
                        'error': str(e)
                    })
                    raise
                
                # Clean and validate response
                cleaned_response = clean_sigma_rule(sigma_response)
                
                # Split into individual rules
                rule_blocks = cleaned_response.split('---')
                # Note: attempt_rules, attempt_validation_results, and all_valid are already initialized above
                
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
                    attempt_validation_results.append(validation_result)
                    validation_results.append(validation_result)
                    
                    if not validation_result.is_valid:
                        all_valid = False
                    
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
                            all_valid = False
                
                # Store conversation log entry (always store, even if response is empty)
                conversation_log.append({
                    'attempt': attempt + 1,
                    'messages': [
                        {
                            'role': 'system',
                            'content': 'You are a senior cybersecurity detection engineer specializing in SIGMA rule creation.'
                        },
                        {
                            'role': 'user',
                            'content': current_prompt
                        }
                    ],
                    'llm_response': sigma_response if sigma_response else "",  # Ensure it's always a string, never None
                    'validation': [
                        {
                            'is_valid': r.is_valid,
                            'errors': r.errors,
                            'warnings': r.warnings,
                            'rule_index': r.metadata.get('rule_index') if r.metadata else None
                        } for r in attempt_validation_results
                    ],
                    'all_valid': all_valid,
                    'error': None
                })
                
                logger.debug(f"Stored conversation log entry for attempt {attempt + 1}: llm_response length={len(sigma_response) if sigma_response else 0}")
                
                # If we got valid rules, break
                if attempt_rules:
                    rules.extend(attempt_rules)
                    break
                
                # Prepare validation feedback for next attempt
                previous_errors = []
                previous_yaml_preview = ""
                # Safety check: ensure attempt_validation_results is a list
                if attempt_validation_results is None:
                    logger.warning(f"SIGMA generation attempt {attempt + 1}: attempt_validation_results is None, initializing as empty list")
                    attempt_validation_results = []
                for result in attempt_validation_results:
                    if not result.is_valid and result.errors:
                        previous_errors.extend(result.errors)
                    if result.content_preview:
                        previous_yaml_preview = result.content_preview
                
                # If nothing to feedback (e.g., no YAML detected), provide explicit guidance
                if not previous_errors and not attempt_rules:
                    previous_errors = [
                        "No valid SIGMA YAML detected. Respond with YAML starting with 'title:' and include "
                        "'logsource' and 'detection' mappings using 2-space indentation. Do not include prose."
                    ]
                
                previous_errors_text = "\n".join(previous_errors) if previous_errors else None
            
            return {
                'rules': rules,
                'metadata': {
                    'total_attempts': len(conversation_log),
                    'valid_rules': len(rules),
                    'validation_results': [
                        {
                            'is_valid': r.is_valid,
                            'errors': r.errors,
                            'warnings': r.warnings
                        } for r in validation_results
                    ],
                    'conversation_log': conversation_log
                },
                'errors': None if rules else (
                    f"No valid SIGMA rules could be generated. Last validation errors: {previous_errors_text}"
                    if previous_errors_text else "No valid SIGMA rules could be generated"
                )
            }
            
        except Exception as e:
            logger.error(f"Error generating SIGMA rules: {e}")
            return {
                'rules': [],
                'metadata': {},
                'errors': str(e)
            }
    
    async def _call_provider_for_sigma(
        self,
        prompt: str,
        *,
        provider: str,
        execution_id: Optional[int] = None,
        article_id: Optional[int] = None
    ) -> str:
        raw_model_name = self.llm_service.model_sigma or self.llm_service.provider_defaults.get(provider, self.llm_service.lmstudio_model)
        
        # Normalize model name for LMStudio (remove prefix and date suffix)
        # e.g., "qwen/qwen3-4b-2507" -> "qwen3-4b"
        model_name = raw_model_name
        if provider == "lmstudio" and model_name:
            # Remove common prefixes (e.g., "qwen/", "mistralai/")
            if "/" in model_name:
                model_name = model_name.split("/")[-1]
            # Remove date suffixes (e.g., "-2507", "-2024")
            import re
            model_name = re.sub(r'-\d{4,8}$', '', model_name)

        messages = [
            {
                "role": "system",
                "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries. No markdown, no explanations. IMPORTANT: If title or description contains special YAML characters (?, :, [, ], {, }, |, &, *, #, @, `), quote the value with double quotes, e.g., title: \"Rule Title with ?\"."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        converted_messages = self.llm_service._convert_messages_for_model(messages, model_name)

        is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
        max_tokens = 2000 if is_reasoning_model else 800

        with trace_llm_call(
            name="generate_sigma",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata={
                "prompt_length": len(prompt),
                "max_tokens": max_tokens,
                "provider": provider
            }
        ) as generation:
            try:
                result = await self.llm_service.request_chat(
                    provider=provider,
                    model_name=model_name,
                    messages=converted_messages,
                    max_tokens=max_tokens,
                    temperature=self.llm_service.temperature_sigma,
                    timeout=300.0,
                    failure_context=f"Failed to generate SIGMA rules via {provider}",
                    top_p=self.llm_service.top_p_sigma,
                    seed=self.llm_service.seed
                )

                message = result['choices'][0]['message']
                content_text = message.get('content', '')
                reasoning_text = message.get('reasoning_content', '')

                if content_text and (content_text.strip().startswith('title:') or 'title:' in content_text[:100]):
                    output = content_text
                    logger.debug("Using 'content' field for SIGMA generation (contains YAML)")
                elif reasoning_text:
                    import re
                    yaml_match = re.search(r'(?:^|\n)title:\s*[^\n]+\n(?:[^\n]+\n)*', reasoning_text, re.MULTILINE)
                    if yaml_match:
                        yaml_start = yaml_match.start()
                        yaml_block = reasoning_text[yaml_start:]
                        output = yaml_block
                        logger.debug("Extracted YAML from 'reasoning_content' field")
                    else:
                        output = reasoning_text
                        logger.debug("Using 'reasoning_content' field for SIGMA generation (no YAML pattern found)")
                else:
                    output = content_text or reasoning_text or ""

                finish_reason = result['choices'][0].get('finish_reason', '')
                if finish_reason == 'length':
                    logger.warning(f"SIGMA generation response was truncated (finish_reason=length). Used {result.get('usage', {}).get('completion_tokens', 0)} tokens. max_tokens={max_tokens} may need to be increased.")

                if not output or len(output.strip()) == 0:
                    logger.error("LLM returned empty response for SIGMA generation")
                    raise ValueError("LLM returned empty response for SIGMA generation. Check the configured provider is responding correctly.")

                usage = result.get('usage', {})

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
                        "finish_reason": finish_reason,
                        "provider": provider
                    }
                )

                return output
            except Exception as e:
                log_llm_error(generation, e)
                raise
