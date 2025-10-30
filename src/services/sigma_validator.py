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


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def clean_sigma_rule(rule_content: str) -> str:
    """Clean SIGMA rule by removing markdown formatting and explanatory text"""
    import re

    cleaned = rule_content.strip()

    # Debug logging
    logger.debug(f"Original content starts with: {repr(cleaned[:100])}")

    # Strategy 1: Extract content between code blocks
    code_block_pattern = r'```(?:yaml|yml)?\s*\n(.*?)```'
    code_block_match = re.search(code_block_pattern, cleaned, re.DOTALL)

    if code_block_match:
        cleaned = code_block_match.group(1).strip()
        logger.debug("Extracted content from code block")
    else:
        # Strategy 2: Remove leading explanatory text before YAML starts
        # Look for the first line that starts with a YAML key (e.g., "title:", "id:", "description:")
        lines = cleaned.split('\n')
        yaml_start_idx = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Check if line looks like a YAML key:value pair
            if stripped and ':' in stripped:
                key_part = stripped.split(':')[0].strip()
                # Common SIGMA rule top-level keys
                if key_part in ['title', 'id', 'description', 'status', 'author', 'date',
                                'modified', 'logsource', 'detection', 'falsepositives',
                                'level', 'tags', 'references', 'fields']:
                    yaml_start_idx = i
                    logger.debug(f"Found YAML start at line {i}: {stripped[:50]}")
                    break

        if yaml_start_idx is not None:
            cleaned = '\n'.join(lines[yaml_start_idx:])
            logger.debug(f"Removed {yaml_start_idx} lines of explanatory text")

    # Strategy 3: Remove any remaining markdown code block markers
    if cleaned.startswith('```yaml'):
        cleaned = cleaned[7:].strip()
        logger.debug("Removed ```yaml prefix")
    elif cleaned.startswith('```yml'):
        cleaned = cleaned[6:].strip()
        logger.debug("Removed ```yml prefix")
    elif cleaned.startswith('```'):
        cleaned = cleaned[3:].strip()
        logger.debug("Removed ``` prefix")

    if cleaned.endswith('```'):
        cleaned = cleaned[:-3].strip()
        logger.debug("Removed ``` suffix")

    # Strategy 4: Remove inline text mixed with YAML (e.g., "Here is the rule: title: ...")
    # Look for pattern like "text: title:" and extract from "title:" onwards
    first_line = cleaned.split('\n')[0]
    if 'title:' in first_line and not first_line.strip().startswith('title:'):
        # There's text before 'title:' on the same line
        title_idx = first_line.index('title:')
        rest_of_content = '\n'.join(cleaned.split('\n')[1:])
        cleaned = first_line[title_idx:] + '\n' + rest_of_content
        logger.debug("Removed inline explanatory text before 'title:'")

    # Clean up whitespace
    cleaned = '\n'.join(line.rstrip() for line in cleaned.split('\n'))
    cleaned = cleaned.strip()

    logger.debug(f"Cleaned content starts with: {repr(cleaned[:100])}")

    return cleaned

@dataclass
class ValidationResult:
    """Result of SIGMA rule validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    metadata: Optional[Dict[str, Any]] = None
    content_preview: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SigmaRule:
    """SIGMA rule representation."""
    
    def __init__(self, rule_data: Dict):
        self.rule_data = rule_data
        self._validate_required_fields()
        self._validate_logsource()
        self._validate_detection()
        self._validate_level()
    
    def _validate_required_fields(self):
        """Validate required fields."""
        required_fields = ['title', 'logsource', 'detection']
        for field in required_fields:
            if field not in self.rule_data:
                raise ValidationError(f"Missing required field: {field}")
    
    def _validate_logsource(self):
        """Validate logsource configuration."""
        logsource = self.rule_data.get('logsource', {})
        if not logsource:
            raise ValidationError("Logsource section is empty")
        
        category = logsource.get('category')
        if category:
            valid_categories = [
                'process_creation', 'process_access', 'file_access', 'file_change',
                'file_delete', 'file_rename', 'file_write', 'network_connection',
                'dns_query', 'http_request', 'registry_access', 'registry_change',
                'registry_delete', 'registry_rename', 'powershell', 'wmi',
                'sysmon', 'windows', 'linux', 'macos'
            ]
            if category not in valid_categories:
                raise ValidationError(f"Invalid logsource category: {category}")
    
    def _validate_detection(self):
        """Validate detection logic."""
        detection = self.rule_data.get('detection', {})
        if not detection:
            raise ValidationError("Detection section is empty")
        
        # Check for condition key specifically
        if 'condition' not in detection:
            raise ValidationError("Missing detection condition")
    
    def _validate_level(self):
        """Validate level field."""
        level = self.rule_data.get('level')
        if level:
            valid_levels = ['low', 'medium', 'high', 'critical']
            if level not in valid_levels:
                raise ValidationError(f"Invalid level: {level}")
    
    @property
    def title(self) -> str:
        return self.rule_data.get('title', '')
    
    @property
    def description(self) -> str:
        return self.rule_data.get('description', '')
    
    @property
    def level(self) -> str:
        return self.rule_data.get('level', 'medium')
    
    @property
    def logsource(self) -> Dict:
        return self.rule_data.get('logsource', {})
    
    @property
    def detection(self) -> Dict:
        return self.rule_data.get('detection', {})
    
    def to_dict(self) -> Dict:
        """Convert rule to dictionary."""
        return self.rule_data
    
    def to_yaml(self) -> str:
        """Convert rule to YAML string."""
        return yaml.dump(self.rule_data, default_flow_style=False)

class SigmaValidator:
    """SIGMA rule validation service using pySigma"""
    
    def __init__(self):
        self.validator = None
        self.custom_validators = {}
        self.whitelists = {}
        self.blacklists = {}
        
        if PYSIGMA_AVAILABLE:
            try:
                # Initialize pySigma validator
                self.validator = None  # pySigma doesn't have a built-in validator
            except Exception as e:
                logger.warning(f"Failed to initialize SIGMA validator: {e}")
    
    def add_validator(self, name: str, validator_func):
        """Add a custom validator function."""
        self.custom_validators[name] = validator_func
    
    def add_whitelist(self, field: str, allowed_values: List[str]):
        """Add a whitelist for a field."""
        self.whitelists[field] = allowed_values
    
    def add_blacklist(self, field: str, forbidden_values: List[str]):
        """Add a blacklist for a field."""
        self.blacklists[field] = forbidden_values
    
    def validate_rule(self, rule_data: Dict) -> ValidationResult:
        """
        Validate a SIGMA rule dictionary
        
        Args:
            rule_data: Dictionary containing SIGMA rule data
            
        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        
        # Basic structure validation
        if not isinstance(rule_data, dict):
            errors.append("Rule must be a dictionary")
            return ValidationResult(False, errors, warnings)
        
        # Basic SIGMA structure validation
        required_fields = ['title', 'logsource', 'detection']
        for field in required_fields:
            if field not in rule_data:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return ValidationResult(False, errors, warnings)
        
        # Extract rule information safely (handle incorrect types)
        detection = rule_data.get('detection', {})
        detection_fields = list(detection.keys()) if isinstance(detection, dict) else []

        rule_info = {
            'title': rule_data.get('title', ''),
            'id': rule_data.get('id', ''),
            'status': rule_data.get('status', ''),
            'level': rule_data.get('level', ''),
            'tags': rule_data.get('tags', []),
            'logsource': rule_data.get('logsource', {}),
            'detection_fields': detection_fields
        }
        
        # Custom validators
        for name, validator_func in self.custom_validators.items():
            try:
                custom_errors = validator_func(rule_data)
                if custom_errors:
                    errors.extend(custom_errors)
            except Exception as e:
                errors.append(f"Custom validator '{name}' failed: {e}")
        
        # Whitelist validation
        for field, allowed_values in self.whitelists.items():
            value = rule_data.get(field)
            if value and value not in allowed_values:
                errors.append(f"Field '{field}' not in whitelist")
        
        # Blacklist validation
        for field, forbidden_values in self.blacklists.items():
            value = rule_data.get(field)
            if value and value in forbidden_values:
                errors.append(f"Field '{field}' is blacklisted")
        
        # Additional custom validations
        self._validate_detection_logic(rule_data, errors, warnings)
        self._validate_logsource(rule_data, errors, warnings)
        self._validate_metadata(rule_data, errors, warnings)
        
        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings, rule_info)
    
    def validate_rules(self, rules: List[Dict]) -> List[ValidationResult]:
        """Validate multiple rules in batch."""
        results = []
        for rule_data in rules:
            result = self.validate_rule(rule_data)
            results.append(result)
        return results
    
    def _validate_detection_logic(self, rule_data: Dict, errors: List[str], warnings: List[str]):
        """Validate detection logic structure"""
        detection = rule_data.get('detection', {})

        if not detection:
            errors.append("Detection section is empty")
            return

        # CRITICAL: detection must be a dictionary, not a list or string
        if not isinstance(detection, dict):
            errors.append(f"Detection must be a dictionary/object, not {type(detection).__name__}. Example: detection:\\n  selection:\\n    CommandLine|contains: 'malware'\\n  condition: selection")
            return

        # Check for 'condition' key - required in SIGMA
        if 'condition' not in detection:
            errors.append("Detection must contain a 'condition' key. Example: condition: selection")
            return

        # Check for at least one selection/filter
        selections = [k for k in detection.keys() if k not in ['condition', 'timeframe']]
        if not selections:
            errors.append("Detection must have at least one selection or filter (e.g., 'selection:', 'filter:')")
            return
        
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

        # CRITICAL: logsource must be a dictionary, not a string
        if not isinstance(logsource, dict):
            errors.append(f"Logsource must be a dictionary/object, not {type(logsource).__name__}. Example: logsource:\\n  category: process_creation\\n  product: windows")
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
            errors.append(f"Invalid logsource category: {category}")
    
    def _validate_metadata(self, rule_data: Dict, errors: List[str], warnings: List[str]):
        """Validate rule metadata"""
        # Check title length
        title = rule_data.get('title', '')
        if len(title) < 10:
            errors.append("Title is too short (less than 10 characters)")
        elif len(title) > 200:
            warnings.append("Title is very long (more than 200 characters)")
        
        # Check description
        description = rule_data.get('description', '')
        if not description:
            errors.append("Rule has no description")
        elif len(description) < 20:
            warnings.append("Description is very short")
        
        # Check level (case-insensitive)
        level = rule_data.get('level', '')
        valid_levels = ['low', 'medium', 'high', 'critical', 'informational']
        if level and level.lower() not in valid_levels:
            errors.append(f"Invalid level: {level}. Must be one of: {', '.join(valid_levels)}")
        
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
        # SIGMA tags can contain dots (attack.t1059.001), hyphens, and underscores
        for tag in tags:
            if not isinstance(tag, str):
                errors.append(f"Invalid tag format: {tag}. Tags must be simple strings, not dictionaries or objects. Example: tags:\\n  - attack.execution\\n  - attack.t1059.001")
            elif not tag.replace('.', '').replace('_', '').replace('-', '').isalnum():
                warnings.append(f"Tag contains invalid special characters: {tag}")

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
    
    # Parse YAML to dictionary
    try:
        rule_data = yaml.safe_load(cleaned_content)
        if rule_data is None:
            content_preview = cleaned_content[:200] + "..." if len(cleaned_content) > 200 else cleaned_content
            return ValidationResult(False, ["Empty or invalid YAML content"], [], content_preview=content_preview)
    except yaml.YAMLError as e:
        # Provide more helpful error message with content preview
        content_preview = cleaned_content[:200] + "..." if len(cleaned_content) > 200 else cleaned_content
        return ValidationResult(False, [f"Invalid YAML syntax: {e}\n\nContent preview:\n{content_preview}"], [], content_preview=content_preview)
    
    validator = SigmaValidator()
    return validator.validate_rule(rule_data)
