"""Hybrid IOC Extraction Module.

This module combines iocextract for fast, reliable IOC extraction with optional
LLM validation for context and categorization. This provides the best of both worlds:
speed and accuracy.
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import iocextract

logger = logging.getLogger(__name__)


@dataclass
class IOCExtractionResult:
    """Result of IOC extraction with metadata."""
    iocs: Dict[str, List[str]]
    extraction_method: str  # 'iocextract', 'llm', 'hybrid'
    confidence: float
    processing_time: float
    raw_count: int
    validated_count: int
    metadata: Dict[str, Any]


class HybridIOCExtractor:
    """
    Hybrid IOC extractor that combines iocextract with optional LLM validation.
    
    Phase 1: Fast extraction using iocextract
    Phase 2: Optional LLM validation for context and categorization
    """
    
    def __init__(self, use_llm_validation: bool = False):
        """
        Initialize the hybrid IOC extractor.
        
        Args:
            use_llm_validation: Whether to use LLM for validation/categorization (default: False)
        """
        self.use_llm_validation = use_llm_validation
        self.iocextract = iocextract
        
    def extract_raw_iocs(self, content: str) -> Dict[str, List[str]]:
        """
        Extract raw IOCs using iocextract.
        
        Args:
            content: Text content to extract IOCs from
            
        Returns:
            Dictionary of IOC types and their values
        """
        try:
            # Extract different types of IOCs
            raw_iocs = {
                'ip': list(self.iocextract.extract_ips(content, refang=True)),
                'domain': list(self.iocextract.extract_urls(content, refang=True)),
                'url': list(self.iocextract.extract_urls(content, refang=True)),
                'email': list(self.iocextract.extract_emails(content, refang=True)),
                'file_hash': list(self.iocextract.extract_hashes(content)),
                'registry_key': [],  # iocextract doesn't support registry keys
                'file_path': [],     # iocextract doesn't support file paths
                'mutex': [],         # iocextract doesn't support mutexes
                'named_pipe': []     # iocextract doesn't support named pipes
            }
            
            # Clean up duplicates and empty lists
            cleaned_iocs = {}
            for ioc_type, values in raw_iocs.items():
                # Remove duplicates while preserving order
                unique_values = []
                seen = set()
                for value in values:
                    if value not in seen:
                        unique_values.append(value)
                        seen.add(value)
                cleaned_iocs[ioc_type] = unique_values
            
            # Extract domains from URLs
            if cleaned_iocs['url']:
                domains = []
                for url in cleaned_iocs['url']:
                    try:
                        # Simple domain extraction from URLs
                        if '://' in url:
                            domain = url.split('://')[1].split('/')[0]
                        else:
                            domain = url.split('/')[0]
                        if domain and domain not in domains:
                            domains.append(domain)
                    except:
                        continue
                cleaned_iocs['domain'] = domains
            
            logger.info(f"Extracted {sum(len(v) for v in cleaned_iocs.values())} raw IOCs using iocextract")
            return cleaned_iocs
            
        except Exception as e:
            logger.error(f"Error extracting raw IOCs: {e}")
            return {
                'ip': [], 'domain': [], 'url': [], 'email': [], 'file_hash': [],
                'registry_key': [], 'file_path': [], 'mutex': [], 'named_pipe': []
            }
    
    async def validate_with_llm(self, raw_iocs: Dict[str, List[str]], content: str, api_key: str, ai_model: str = 'chatgpt', cancellation_event: Optional[asyncio.Event] = None) -> tuple[Dict[str, List[str]], str, str]:
        """
        Validate and categorize IOCs using LLM with content.
        
        Args:
            raw_iocs: Raw IOCs extracted by iocextract
            content: Article content (already filtered at API endpoint level if LLM validation enabled)
            api_key: API key (optional for local models)
            ai_model: AI model to use ('chatgpt', 'anthropic', 'lmstudio')
            
        Returns:
            Tuple of (validated_iocs, prompt, response)
        """
        try:
            import httpx
            import os
            from datetime import datetime
            
            # Prepare the validation prompt
            prompt = f"""You are a cybersecurity analyst. Validate and categorize these extracted IOCs from threat intelligence content.

CRITICAL: Return ONLY valid JSON. Do not include any explanatory text, comments, or markdown formatting.

Rules:
- Validate that IOCs are actually malicious/relevant to threats
- Categorize IOCs into appropriate types (IP, Domain, URL, File Hash, Registry Key, File Path, Email, Mutex, Named Pipe)
- Remove false positives and non-malicious IOCs
- Normalize values (lowercase domains, full paths, valid hash lengths)
- Return empty arrays for categories with no valid IOCs

Raw IOCs extracted:
{json.dumps(raw_iocs, indent=2)}

Article content context:
{content}

Output format (return ONLY this JSON structure):
{{
  "ip": [],
  "domain": [],
  "url": [],
  "file_hash": [],
  "registry_key": [],
  "file_path": [],
  "email": [],
  "mutex": [],
  "named_pipe": []
}}"""

            # Route to appropriate API based on model
            client = httpx.AsyncClient()
            try:
                if ai_model == 'lmstudio':
                    # Use LMStudio API with recommended settings
                    lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
                    lmstudio_model = os.getenv("LMSTUDIO_MODEL", "llama-3.2-1b-instruct")
                    
                    # Get recommended settings (temperature 0.0 for deterministic scoring, top_p 0.9, seed 42)
                    temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
                    top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
                    seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None
                    
                    payload = {
                        "model": lmstudio_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a cybersecurity analyst specializing in IOC validation. Validate and categorize IOCs from threat intelligence articles and return them in valid JSON format only. NEVER include explanatory text, comments, or markdown formatting. Return ONLY the JSON object."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "max_tokens": 2048,
                        "temperature": temperature,
                        "top_p": top_p,
                    }
                    if seed is not None:
                        payload["seed"] = seed
                    
                    # Check for cancellation before making the request
                    if cancellation_event and cancellation_event.is_set():
                        raise asyncio.CancelledError("IOC validation cancelled by client")
                    
                    # Create the request task
                    async def make_request():
                        return await client.post(
                            f"{lmstudio_url}/chat/completions",
                            headers={
                                "Content-Type": "application/json"
                            },
                            json=payload,
                            timeout=120.0
                        )
                    
                    request_task = asyncio.create_task(make_request())
                    
                    # Monitor for cancellation while waiting for response
                    if cancellation_event:
                        async def wait_for_cancellation():
                            await cancellation_event.wait()
                        
                        cancellation_task = asyncio.create_task(wait_for_cancellation())
                        
                        # Wait for either request completion or cancellation
                        done, pending = await asyncio.wait(
                            [request_task, cancellation_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Check which task completed
                        if cancellation_task in done:
                            # Cancellation occurred - cancel the request task and close the client
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
                            # Cancel the cancellation task cleanup
                            try:
                                cancellation_task.cancel()
                                await cancellation_task
                            except asyncio.CancelledError:
                                pass
                            raise asyncio.CancelledError("IOC validation cancelled by client")
                        
                        # Request completed first - cancel the cancellation monitor
                        if not cancellation_task.done():
                            cancellation_task.cancel()
                            try:
                                await cancellation_task
                            except asyncio.CancelledError:
                                pass
                        
                        # Get the response from the completed request task
                        response = await request_task
                    else:
                        # No cancellation support, just await the request
                        response = await request_task
                    
                    # Check for cancellation after the request
                    if cancellation_event and cancellation_event.is_set():
                        raise asyncio.CancelledError("IOC validation cancelled by client")
                else:
                    # Use ChatGPT API for validation
                    chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
                    
                    response = await client.post(
                        chatgpt_api_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a cybersecurity analyst specializing in IOC validation. Validate and categorize IOCs from threat intelligence articles and return them in valid JSON format only. NEVER include explanatory text, comments, or markdown formatting. Return ONLY the JSON object."
                                },
                                {
                                    "role": "user",
                                    "content": prompt
                                }
                            ],
                            "max_tokens": 2048,
                            "temperature": 0.1
                        },
                        timeout=60.0
                    )
                
                if response.status_code != 200:
                    logger.error(f"LLM validation failed: {response.status_code}")
                    raise Exception(f"LLM validation failed with status {response.status_code}")
                
                result = response.json()
                
                # Handle response format
                validated_json = result['choices'][0]['message']['content']
                
                # Parse the validated JSON
                try:
                    validated_iocs = json.loads(validated_json)
                    logger.info(f"LLM validation completed successfully")
                    return validated_iocs, prompt, validated_json
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM validation response: {e}")
                    raise Exception(f"Failed to parse LLM validation response: {e}")
            finally:
                # Ensure client is closed
                try:
                    await client.aclose()
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"Error in LLM validation: {e}")
            raise  # Re-raise the exception so the caller can handle it
    
    async def extract_iocs(self, content: str, api_key: Optional[str] = None, ai_model: str = 'chatgpt', cancellation_event: Optional[asyncio.Event] = None) -> IOCExtractionResult:
        """
        Extract IOCs using hybrid approach.
        
        Args:
            content: Text content to extract IOCs from
            api_key: OpenAI API key for LLM validation (optional)
            ai_model: AI model to use for validation (default: 'chatgpt')
            
        Returns:
            IOCExtractionResult with extracted IOCs and metadata
        """
        import time
        start_time = time.time()
        
        # Phase 1: Fast extraction with iocextract
        raw_iocs = self.extract_raw_iocs(content)
        raw_count = sum(len(v) for v in raw_iocs.values())
        
        # Phase 2: LLM validation (if enabled and IOCs found)
        final_iocs = raw_iocs
        extraction_method = 'iocextract'
        confidence = 0.8  # High confidence for iocextract
        
        if self.use_llm_validation and raw_count > 0:
            try:
                # Use full content for LLM validation (no truncation limit)
                # Content filtering is handled at the API endpoint level when LLM validation is enabled
                # This allows the full filtered content to be sent for better validation context
                # Check for cancellation before LLM validation
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError("IOC extraction cancelled by client")
                
                validated_iocs, prompt, response = await self.validate_with_llm(raw_iocs, content, api_key, ai_model, cancellation_event)
                
                # Check for cancellation after LLM validation
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError("IOC extraction cancelled by client")
                final_iocs = validated_iocs
                extraction_method = 'hybrid'
                confidence = 0.95  # Higher confidence with LLM validation
                logger.info(f"Hybrid extraction completed: {raw_count} raw IOCs -> {sum(len(v) for v in validated_iocs.values())} validated IOCs")
                
                # Store prompt and response in metadata
                llm_metadata = {
                    'prompt': prompt,
                    'response': response
                }
                    
            except Exception as e:
                logger.warning(f"LLM validation failed, using iocextract results: {e}")
                # Reset to iocextract method when LLM validation fails
                extraction_method = 'iocextract'
                confidence = 0.8
                llm_metadata = {}
        
        processing_time = time.time() - start_time
        validated_count = sum(len(v) for v in final_iocs.values())
        
        metadata = {
            'raw_extraction_count': raw_count,
            'validation_applied': self.use_llm_validation and raw_count > 0,
            'llm_validation_successful': extraction_method == 'hybrid'
        }
        
        # Add LLM metadata if available
        if 'llm_metadata' in locals():
            metadata.update(llm_metadata)
        
        return IOCExtractionResult(
            iocs=final_iocs,
            extraction_method=extraction_method,
            confidence=confidence,
            processing_time=processing_time,
            raw_count=raw_count,
            validated_count=validated_count,
            metadata=metadata
        )
