"""Hybrid IOC Extraction Module.

This module combines iocextract for fast, reliable IOC extraction with optional
LLM validation for context and categorization. This provides the best of both worlds:
speed and accuracy.
"""

import logging
import json
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
    
    def __init__(self, use_llm_validation: bool = True):
        """
        Initialize the hybrid IOC extractor.
        
        Args:
            use_llm_validation: Whether to use LLM for validation/categorization
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
                'named_pipe': [],    # iocextract doesn't support named pipes
                'process_cmdline': [], # iocextract doesn't support process/cmdline
                'event_id': []       # iocextract doesn't support event IDs
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
                'registry_key': [], 'file_path': [], 'mutex': [], 'named_pipe': [],
                'process_cmdline': [], 'event_id': []
            }
    
    async def validate_with_llm(self, raw_iocs: Dict[str, List[str]], content: str, api_key: str) -> Dict[str, List[str]]:
        """
        Validate and categorize IOCs using LLM.
        
        Args:
            raw_iocs: Raw IOCs extracted by iocextract
            content: Original content for context
            api_key: OpenAI API key
            
        Returns:
            Validated and categorized IOCs
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
- Categorize IOCs into appropriate types (IP, Domain, URL, File Hash, Registry Key, File Path, Email, Mutex, Named Pipe, Process/Command-Line, Event ID)
- Remove false positives and non-malicious IOCs
- Normalize values (lowercase domains, full paths, valid hash lengths)
- Return empty arrays for categories with no valid IOCs

Raw IOCs extracted:
{json.dumps(raw_iocs, indent=2)}

Original content context:
{content[:2000]}...

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
  "named_pipe": [],
  "process_cmdline": [],
  "event_id": []
}}"""

            # Use ChatGPT API for validation
            chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    chatgpt_api_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4",
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
                    return raw_iocs  # Return raw IOCs if LLM fails
                
                result = response.json()
                validated_json = result['choices'][0]['message']['content']
                
                # Parse the validated JSON
                try:
                    validated_iocs = json.loads(validated_json)
                    logger.info(f"LLM validation completed successfully")
                    return validated_iocs
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM validation response: {e}")
                    return raw_iocs  # Return raw IOCs if parsing fails
                    
        except Exception as e:
            logger.error(f"Error in LLM validation: {e}")
            return raw_iocs  # Return raw IOCs if validation fails
    
    async def extract_iocs(self, content: str, api_key: Optional[str] = None) -> IOCExtractionResult:
        """
        Extract IOCs using hybrid approach.
        
        Args:
            content: Text content to extract IOCs from
            api_key: OpenAI API key for LLM validation (optional)
            
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
        
        if self.use_llm_validation and raw_count > 0 and api_key:
            try:
                validated_iocs = await self.validate_with_llm(raw_iocs, content, api_key)
                final_iocs = validated_iocs
                extraction_method = 'hybrid'
                confidence = 0.95  # Higher confidence with LLM validation
                logger.info(f"Hybrid extraction completed: {raw_count} raw IOCs -> {sum(len(v) for v in validated_iocs.values())} validated IOCs")
            except Exception as e:
                logger.warning(f"LLM validation failed, using iocextract results: {e}")
        
        processing_time = time.time() - start_time
        validated_count = sum(len(v) for v in final_iocs.values())
        
        return IOCExtractionResult(
            iocs=final_iocs,
            extraction_method=extraction_method,
            confidence=confidence,
            processing_time=processing_time,
            raw_count=raw_count,
            validated_count=validated_count,
            metadata={
                'raw_extraction_count': raw_count,
                'validation_applied': self.use_llm_validation and raw_count > 0 and api_key,
                'llm_validation_successful': extraction_method == 'hybrid'
            }
        )
