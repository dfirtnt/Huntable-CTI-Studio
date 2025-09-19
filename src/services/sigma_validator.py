"""
SIGMA Rule Validation Service using pySigma

Validates LLM-generated SIGMA rules for syntax, structure, and best practices.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import yaml

try:
    from sigma.rule import SigmaRule
    from sigma.exceptions import SigmaError, SigmaDetectionError, SigmaLogsourceError
    PYSIGMA_AVAILABLE = True
except ImportError:
    PYSIGMA_AVAILABLE = False
    SigmaRule = None
    SigmaError = None
    SigmaDetectionError = None
    SigmaLogsourceError = None

logger = logging.getLogger(__name__)

def clean_sigma_rule(rule_content: str) -> str:
    """Clean SIGMA rule by removing markdown formatting"""
    # Remove markdown code blocks
    cleaned = rule_content.strip()
    
    # Remove ```yaml or ``` at the beginning
    if cleaned.startswith('```yaml'):
        cleaned = cleaned[7:]  # Remove ```yaml
    elif cleaned.startswith('```'):
        cleaned = cleaned[3:]   # Remove ```
    
    # Remove ``` at the end
    if cleaned.endswith('```'):
        cleaned = cleaned[:-3]
    
    return cleaned.strip()

@dataclass
class ValidationResult:
    """Result of SIGMA rule validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    rule_info: Optional[Dict[str, Any]] = None

class SigmaValidator:
    """SIGMA rule validation service using pySigma"""
    
    def __init__(self):
        self.validator = None
        if PYSIGMA_AVAILABLE:
            try:
                # Initialize pySigma validator
                self.validator = None  # pySigma doesn't have a built-in validator
            except Exception as e:
                logger.warning(f"Failed to initialize SIGMA validator: {e}")
    
    def validate_rule(self, rule_yaml: str) -> ValidationResult:
        """
        Validate a SIGMA rule YAML string
        
        Args:
            rule_yaml: YAML string containing SIGMA rule
            
        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        rule_info = None
        
        # Basic YAML validation
        try:
            rule_data = yaml.safe_load(rule_yaml)
            if not isinstance(rule_data, dict):
                errors.append("Rule must be a YAML dictionary")
                return ValidationResult(False, errors, warnings)
        except yaml.YAMLError as e:
            errors.append(f"Invalid YAML syntax: {e}")
            return ValidationResult(False, errors, warnings)
        
        # Basic SIGMA structure validation
        required_fields = ['title', 'logsource', 'detection']
        for field in required_fields:
            if field not in rule_data:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return ValidationResult(False, errors, warnings)
        
        # Extract rule information
        rule_info = {
            'title': rule_data.get('title', ''),
            'id': rule_data.get('id', ''),
            'status': rule_data.get('status', ''),
            'level': rule_data.get('level', ''),
            'tags': rule_data.get('tags', []),
            'logsource': rule_data.get('logsource', {}),
            'detection_fields': list(rule_data.get('detection', {}).keys())
        }
        
        # pySigma validation if available
        if PYSIGMA_AVAILABLE:
            try:
                sigma_rule = SigmaRule.from_yaml(rule_yaml)
                # Basic pySigma validation
                if sigma_rule:
                    warnings.append("Rule passed pySigma validation")
                else:
                    errors.append("Rule failed pySigma validation")
                        
            except SigmaError as e:
                errors.append(f"SIGMA processing error: {e}")
            except Exception as e:
                warnings.append(f"SIGMA validation warning: {e}")
        else:
            warnings.append("pySigma not available - using basic validation only")
        
        # Additional custom validations
        self._validate_detection_logic(rule_data, errors, warnings)
        self._validate_logsource(rule_data, errors, warnings)
        self._validate_metadata(rule_data, errors, warnings)
        
        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings, rule_info)
    
    def _validate_detection_logic(self, rule_data: Dict, errors: List[str], warnings: List[str]):
        """Validate detection logic structure"""
        detection = rule_data.get('detection', {})
        
        if not detection:
            errors.append("Detection section is empty")
            return
        
        # Check for at least one condition
        conditions = [k for k in detection.keys() if not k.startswith('_')]
        if not conditions:
            errors.append("No detection conditions found")
        
        # Validate condition structure
        for condition_name, condition_data in detection.items():
            if condition_name.startswith('_'):
                continue
                
            if isinstance(condition_data, str):
                # Simple condition reference (e.g., "selection")
                continue
            elif not isinstance(condition_data, (list, dict)):
                errors.append(f"Invalid condition '{condition_name}': must be list, dict, or string")
                continue
            
            if isinstance(condition_data, list):
                # List of search identifiers
                for item in condition_data:
                    if not isinstance(item, str):
                        errors.append(f"Invalid search identifier in '{condition_name}': {item}")
            elif isinstance(condition_data, dict):
                # Direct search definition
                if 'keywords' not in condition_data and 'selection' not in condition_data:
                    warnings.append(f"Condition '{condition_name}' has no keywords or selection")
    
    def _validate_logsource(self, rule_data: Dict, errors: List[str], warnings: List[str]):
        """Validate logsource configuration"""
        logsource = rule_data.get('logsource', {})
        
        if not logsource:
            errors.append("Logsource section is empty")
            return
        
        # Check for required logsource fields
        if 'category' not in logsource and 'product' not in logsource and 'service' not in logsource:
            warnings.append("Logsource should specify category, product, or service")
        
        # Validate logsource values
        valid_categories = [
            'process_creation', 'process_access', 'file_access', 'file_change',
            'file_delete', 'file_rename', 'file_write', 'network_connection',
            'dns_query', 'http_request', 'registry_access', 'registry_change',
            'registry_delete', 'registry_rename', 'powershell', 'wmi',
            'sysmon', 'windows', 'linux', 'macos'
        ]
        
        category = logsource.get('category')
        if category and category not in valid_categories:
            warnings.append(f"Unknown logsource category: {category}")
    
    def _validate_metadata(self, rule_data: Dict, errors: List[str], warnings: List[str]):
        """Validate rule metadata"""
        # Check title length
        title = rule_data.get('title', '')
        if len(title) < 10:
            warnings.append("Title is very short (less than 10 characters)")
        elif len(title) > 200:
            warnings.append("Title is very long (more than 200 characters)")
        
        # Check description
        description = rule_data.get('description', '')
        if not description:
            warnings.append("Rule has no description")
        elif len(description) < 20:
            warnings.append("Description is very short")
        
        # Check level
        level = rule_data.get('level', '')
        valid_levels = ['low', 'medium', 'high', 'critical']
        if level and level not in valid_levels:
            warnings.append(f"Unknown severity level: {level}")
        
        # Check status
        status = rule_data.get('status', '')
        valid_statuses = ['experimental', 'test', 'stable']
        if status and status not in valid_statuses:
            warnings.append(f"Unknown status: {status}")
        
        # Check tags
        tags = rule_data.get('tags', [])
        if not tags:
            warnings.append("Rule has no tags")
        
        # Validate tag format
        for tag in tags:
            if not isinstance(tag, str):
                errors.append(f"Invalid tag format: {tag}")
            elif not tag.replace('_', '').replace('-', '').isalnum():
                warnings.append(f"Tag contains special characters: {tag}")

def validate_sigma_rule(rule_yaml: str) -> ValidationResult:
    """
    Convenience function to validate a SIGMA rule
    
    Args:
        rule_yaml: YAML string containing SIGMA rule
        
    Returns:
        ValidationResult with validation status and details
    """
    # Clean the rule content first
    cleaned_content = clean_sigma_rule(rule_yaml)
    
    validator = SigmaValidator()
    return validator.validate_rule(cleaned_content)
