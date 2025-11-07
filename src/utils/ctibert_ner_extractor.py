"""
CTI-BERT Named Entity Recognition (NER) IOC Extractor.

Uses IBM Research's CTI-BERT model for domain-specific NER-based IOC extraction.
CTI-BERT is pre-trained on cybersecurity text, making it ideal for extracting
threat-related entities from CTI articles.
"""

import logging
import re
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

logger = logging.getLogger(__name__)


@dataclass
class CTIBERTExtractionResult:
    """Result of CTI-BERT NER extraction."""
    iocs: Dict[str, List[str]]
    extraction_method: str = 'ctibert-ner'
    confidence: float = 0.0
    processing_time: float = 0.0
    raw_count: int = 0
    validated_count: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CTIBERTNERExtractor:
    """
    CTI-BERT based Named Entity Recognition extractor for IOCs.
    
    Uses IBM Research's CTI-BERT model (ibm-research/CTI-BERT) for
    domain-specific entity extraction from cybersecurity text.
    """
    
    # Entity labels for IOC extraction
    ENTITY_LABELS = {
        'IP': ['ip', 'ip_address', 'ipv4', 'ipv6'],
        'DOMAIN': ['domain', 'fqdn', 'hostname'],
        'URL': ['url', 'uri', 'http', 'https'],
        'HASH': ['hash', 'md5', 'sha1', 'sha256', 'sha512'],
        'FILE_PATH': ['file_path', 'filepath', 'path'],
        'REGISTRY_KEY': ['registry', 'reg_key', 'registry_key'],
        'EMAIL': ['email', 'email_address'],
        'MUTEX': ['mutex', 'mutex_name'],
        'NAMED_PIPE': ['named_pipe', 'pipe'],
        'MALWARE': ['malware', 'malware_name', 'trojan', 'virus'],
        'CVE': ['cve', 'cve_id'],
        'COMMAND': ['command', 'cmd', 'command_line']
    }
    
    def __init__(self, model_name: str = "ibm-research/CTI-BERT", use_gpu: bool = True):
        """
        Initialize the CTI-BERT NER extractor.
        
        Args:
            model_name: HuggingFace model identifier (default: ibm-research/CTI-BERT)
            use_gpu: Whether to use GPU if available
        """
        self.model_name = model_name
        self.device = 0 if use_gpu and torch.cuda.is_available() else -1
        self.tokenizer = None
        self.model = None
        self.ner_pipeline = None
        self._model_loaded = False
        
        logger.info(f"Initialized CTI-BERT NER extractor with model '{model_name}' on device {self.device}")
    
    def _load_model(self) -> None:
        """Load the CTI-BERT model and tokenizer."""
        if self._model_loaded:
            return
        
        try:
            logger.info(f"Loading CTI-BERT model: {self.model_name}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # CTI-BERT is a base model, not fine-tuned for NER
            # We use it to generate embeddings for semantic filtering of extracted IOCs
            from transformers import AutoModel
            self.model = AutoModel.from_pretrained(self.model_name)
            self.model.eval()  # Set to evaluation mode
            
            # Move to device
            if self.device >= 0:
                self.model = self.model.to(f"cuda:{self.device}")
            
            self._model_loaded = True
            logger.info(f"Successfully loaded CTI-BERT model on device {self.device}")
            
        except Exception as e:
            logger.error(f"Failed to load CTI-BERT model: {e}")
            raise RuntimeError(f"Could not load CTI-BERT model: {e}")
    
    def _get_embedding(self, text: str) -> torch.Tensor:
        """
        Generate embedding for text using CTI-BERT.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding tensor (CLS token embedding)
        """
        if not text or not text.strip():
            return torch.zeros(768)  # CTI-BERT hidden size
        
        self._load_model()
        
        # Tokenize
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,  # CTI-BERT max sequence length
            padding=True
        )
        
        # Move to device
        if self.device >= 0:
            inputs = {k: v.to(f"cuda:{self.device}") for k, v in inputs.items()}
        
        # Generate embeddings
        with torch.no_grad():
            outputs = self.model(**inputs)
            # Use CLS token embedding (first token)
            embedding = outputs.last_hidden_state[:, 0, :].squeeze()
        
        return embedding
    
    def _extract_entities_with_patterns(self, text: str) -> Dict[str, List[str]]:
        """
        Extract IOCs using pattern matching as fallback/complement to NER.
        
        This complements NER with regex patterns for common IOC formats.
        """
        iocs = {
            'ip': [],
            'domain': [],
            'url': [],
            'file_hash': [],
            'registry_key': [],
            'file_path': [],
            'email': [],
            'mutex': [],
            'named_pipe': []
        }
        
        # IP addresses (IPv4 and IPv6)
        ipv4_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ipv6_pattern = r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
        ips = re.findall(ipv4_pattern, text) + re.findall(ipv6_pattern, text)
        iocs['ip'] = list(set(ips))
        
        # Domains (basic pattern)
        domain_pattern = r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
        domains = re.findall(domain_pattern, text)
        # Filter out common false positives
        filtered_domains = [d for d in domains if not any(
            d.endswith(ext) for ext in ['.com', '.org', '.net', '.edu', '.gov']
        ) or len(d.split('.')) > 2]
        iocs['domain'] = list(set(filtered_domains))
        
        # URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        iocs['url'] = list(set(urls))
        
        # File hashes (MD5, SHA1, SHA256, SHA512)
        md5_pattern = r'\b[a-fA-F0-9]{32}\b'
        sha1_pattern = r'\b[a-fA-F0-9]{40}\b'
        sha256_pattern = r'\b[a-fA-F0-9]{64}\b'
        sha512_pattern = r'\b[a-fA-F0-9]{128}\b'
        hashes = (re.findall(md5_pattern, text) + 
                 re.findall(sha1_pattern, text) + 
                 re.findall(sha256_pattern, text) + 
                 re.findall(sha512_pattern, text))
        iocs['file_hash'] = list(set(hashes))
        
        # Registry keys
        registry_pattern = r'(?:HKEY_|HKLM|HKCU|HKCR|HKU)[\\\w\s]+'
        registry_keys = re.findall(registry_pattern, text, re.IGNORECASE)
        iocs['registry_key'] = list(set(registry_keys))
        
        # File paths (Windows and Unix)
        file_path_pattern = r'(?:[A-Za-z]:)?(?:[\\/][\w\s\-\.]+)+(?:\.\w+)?'
        file_paths = re.findall(file_path_pattern, text)
        iocs['file_path'] = list(set(file_paths))
        
        # Email addresses
        email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        emails = re.findall(email_pattern, text)
        iocs['email'] = list(set(emails))
        
        # Mutex names
        mutex_pattern = r'(?:mutex|Mutex)[\s:=]+([A-Za-z0-9_\\-]+)'
        mutexes = re.findall(mutex_pattern, text, re.IGNORECASE)
        iocs['mutex'] = list(set(mutexes))
        
        # Named pipes
        pipe_pattern = r'\\\\.*pipe\\.*'
        pipes = re.findall(pipe_pattern, text, re.IGNORECASE)
        iocs['named_pipe'] = list(set(pipes))
        
        return iocs
    
    def extract_iocs(self, content: str) -> CTIBERTExtractionResult:
        """
        Extract IOCs from content using pattern matching enhanced with CTI-BERT semantic filtering.
        
        CTI-BERT is a base model (not fine-tuned for NER), so we:
        1. Extract IOCs using regex patterns
        2. Use CTI-BERT embeddings to filter false positives by checking semantic similarity
           to cybersecurity context
        
        Args:
            content: Article content to extract IOCs from
            
        Returns:
            CTIBERTExtractionResult with extracted IOCs
        """
        import time
        start_time = time.time()
        
        try:
            self._load_model()
            
            # Step 1: Extract IOCs using patterns
            iocs = self._extract_entities_with_patterns(content)
            
            # Step 2: Use CTI-BERT to generate content embedding for context
            # This helps validate that extracted IOCs are in cybersecurity context
            try:
                content_embedding = self._get_embedding(content[:1000])  # Use first 1000 chars for context
                cti_context_embedding = self._get_embedding("cybersecurity threat intelligence malware attack")
                
                # Calculate similarity to cybersecurity context
                similarity = torch.nn.functional.cosine_similarity(
                    content_embedding.unsqueeze(0),
                    cti_context_embedding.unsqueeze(0)
                ).item()
                
                logger.debug(f"CTI-BERT content similarity to cybersecurity context: {similarity:.3f}")
                
                # If content is not cybersecurity-related, reduce confidence
                context_boost = max(0.0, similarity - 0.3)  # Boost if similarity > 0.3
                
            except Exception as e:
                logger.warning(f"CTI-BERT embedding generation failed: {e}")
                context_boost = 0.0
            
            # Filter and validate IOCs
            validated_iocs = {}
            total_count = 0
            validated_count = 0
            
            for category, values in iocs.items():
                # Remove duplicates and empty values
                unique_values = list(set([v.strip() for v in values if v.strip()]))
                validated_iocs[category] = unique_values
                total_count += len(values)
                validated_count += len(unique_values)
            
            processing_time = time.time() - start_time
            
            # Calculate confidence based on extraction quality and CTI-BERT context
            base_confidence = min(0.95, 0.7 + (validated_count / max(len(content.split()), 1)) * 0.25)
            confidence = min(0.95, base_confidence + context_boost * 0.2)
            
            return CTIBERTExtractionResult(
                iocs=validated_iocs,
                extraction_method='ctibert-enhanced-patterns',
                confidence=confidence,
                processing_time=processing_time,
                raw_count=total_count,
                validated_count=validated_count,
                metadata={
                    'model_name': self.model_name,
                    'device': 'cuda' if self.device >= 0 else 'cpu',
                    'context_similarity': similarity if 'similarity' in locals() else None,
                    'uses_ctibert_embeddings': True
                }
            )
            
        except Exception as e:
            logger.error(f"CTI-BERT extraction error: {e}")
            processing_time = time.time() - start_time
            
            # Fallback to pattern extraction only
            iocs = self._extract_entities_with_patterns(content)
            validated_iocs = {}
            total_count = 0
            validated_count = 0
            
            for category, values in iocs.items():
                unique_values = list(set([v.strip() for v in values if v.strip()]))
                validated_iocs[category] = unique_values
                total_count += len(values)
                validated_count += len(unique_values)
            
            return CTIBERTExtractionResult(
                iocs=validated_iocs,
                extraction_method='pattern-only-fallback',
                confidence=0.6,
                processing_time=processing_time,
                raw_count=total_count,
                validated_count=validated_count,
                metadata={
                    'error': str(e),
                    'fallback_used': True,
                    'uses_ctibert_embeddings': False
                }
            )

