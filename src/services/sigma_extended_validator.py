"""
Extended SIGMA rule validator implementing pySigma-Plus checks.

Extends the base sigma_validator with additional structural checks:
- Telemetry feasibility
- Condition graph validation
- Pattern safety
- IOC leakage detection
- Field conformance
- Impossible-selection detection (same single-value-per-event field required to match incompatible values).
"""

import logging
import re
import yaml
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from src.services.sigma_validator import (
    validate_sigma_rule,
    ValidationResult,
    clean_sigma_rule,
    PYSIGMA_AVAILABLE
)

if PYSIGMA_AVAILABLE:
    from sigma.rule import SigmaRule
    from sigma.exceptions import SigmaError, SigmaDetectionError, SigmaLogsourceError

logger = logging.getLogger(__name__)


@dataclass
class ExtendedValidationResult:
    """Extended validation result with pySigma and additional checks."""
    pySigma_passed: bool
    pySigma_errors: List[str]
    telemetry_feasible: bool
    condition_valid: bool
    pattern_safe: bool
    ioc_leakage: bool  # True if IOC leakage detected (bad)
    field_conformance: bool
    selection_feasible: bool
    final_pass: bool
    errors: List[str]
    warnings: List[str]


class SigmaExtendedValidator:
    """
    Extended SIGMA validator with pySigma-Plus checks.
    
    Implements the E2E-SIG structural validation stage:
    1. pySigma validation (hard fail gate)
    2. Extended structural checks
    """
    
    # Valid Windows process-creation fields
    VALID_PROCESS_CREATION_FIELDS = {
        'Image', 'ParentImage', 'CommandLine', 'ParentCommandLine',
        'ProcessId', 'ParentProcessId', 'IntegrityLevel', 'Hashes',
        'CurrentDirectory', 'User', 'LogonId'
    }

    # Single-value-per-event fields (at most one value per log event). Used to detect
    # impossible selections (e.g. Image endswith powershell.exe AND Image endswith wscript.exe).
    SINGLE_VALUE_PER_EVENT_FIELDS = {
        'Image', 'ParentImage', 'ProcessId', 'ParentProcessId',
        'User', 'LogonId', 'CurrentDirectory', 'IntegrityLevel'
    }
    
    # Valid logsource category/product combinations
    VALID_TELEMETRY_COMBINATIONS = {
        ('process_creation', 'windows'),
        ('process_creation', 'linux'),
        ('process_creation', 'macos'),
        ('network_connection', 'windows'),
        ('network_connection', 'linux'),
        ('network_connection', 'macos'),
        ('file_access', 'windows'),
        ('file_access', 'linux'),
        ('file_access', 'macos'),
        ('registry_access', 'windows'),
        ('registry_change', 'windows'),
        ('dns_query', 'windows'),
        ('dns_query', 'linux'),
        ('dns_query', 'macos'),
        ('powershell', 'windows'),
        ('wmi', 'windows'),
    }
    
    def __init__(self):
        """Initialize extended validator."""
        self.ip_pattern = re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        )
        self.domain_pattern = re.compile(
            r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
        )
        self.base64_pattern = re.compile(
            r'[A-Za-z0-9+/]{40,}={0,2}'
        )
        self.guid_pattern = re.compile(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
        )
        self.jwt_pattern = re.compile(
            r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'
        )
    
    def validate(self, rule_yaml: str) -> ExtendedValidationResult:
        """
        Perform extended validation on SIGMA rule.
        
        Args:
            rule_yaml: YAML string containing SIGMA rule
            
        Returns:
            ExtendedValidationResult with all validation checks
        """
        # Step 1: pySigma validation (hard fail gate)
        pySigma_passed = False
        pySigma_errors = []
        
        if PYSIGMA_AVAILABLE:
            try:
                cleaned = clean_sigma_rule(rule_yaml)
                rule_data = yaml.safe_load(cleaned)
                if rule_data:
                    # Try to parse with pySigma
                    # Note: pySigma's SigmaRule.from_yaml may not exist in all versions
                    # Fall back to basic validation if it fails
                    try:
                        sigma_rule = SigmaRule.from_yaml(cleaned)
                        pySigma_passed = True
                    except AttributeError:
                        # SigmaRule.from_yaml might not be available
                        # Try alternative method
                        try:
                            from io import StringIO
                            sigma_rule = SigmaRule.from_yaml(StringIO(cleaned))
                            pySigma_passed = True
                        except Exception:
                            # If all pySigma methods fail, use basic validation
                            pySigma_passed = False
                            pySigma_errors.append("pySigma parsing not available in this version")
            except Exception as e:
                pySigma_errors.append(f"pySigma validation failed: {str(e)}")
                logger.debug(f"pySigma validation error: {e}")
        else:
            # Fallback to basic validation if pySigma not available
            basic_result = validate_sigma_rule(rule_yaml)
            pySigma_passed = basic_result.is_valid
            if not pySigma_passed:
                pySigma_errors = basic_result.errors
        
        # If pySigma fails, return early (hard fail)
        if not pySigma_passed:
            return ExtendedValidationResult(
                pySigma_passed=False,
                pySigma_errors=pySigma_errors,
                telemetry_feasible=False,
                condition_valid=False,
                pattern_safe=False,
                ioc_leakage=False,
                field_conformance=False,
                selection_feasible=False,
                final_pass=False,
                errors=pySigma_errors,
                warnings=[]
            )
        
        # Step 2: Extended checks (only if pySigma passed)
        cleaned = clean_sigma_rule(rule_yaml)
        rule_data = yaml.safe_load(cleaned)
        
        errors = []
        warnings = []
        
        # Telemetry feasibility
        telemetry_feasible = self._check_telemetry_feasibility(rule_data, errors, warnings)
        
        # Condition graph validation
        condition_valid = self._check_condition_graph(rule_data, errors, warnings)
        
        # Pattern safety
        pattern_safe = self._check_pattern_safety(rule_data, errors, warnings)
        
        # IOC leakage
        ioc_leakage = self._check_ioc_leakage(rule_data, errors, warnings)
        
        # Field conformance
        field_conformance = self._check_field_conformance(rule_data, errors, warnings)
        
        # Impossible-selection (same single-value field, incompatible values)
        selection_feasible = self._check_impossible_selections(rule_data, errors, warnings)
        
        final_pass = (
            pySigma_passed and
            telemetry_feasible and
            condition_valid and
            pattern_safe and
            not ioc_leakage and
            field_conformance and
            selection_feasible
        )
        
        return ExtendedValidationResult(
            pySigma_passed=pySigma_passed,
            pySigma_errors=pySigma_errors,
            telemetry_feasible=telemetry_feasible,
            condition_valid=condition_valid,
            pattern_safe=pattern_safe,
            ioc_leakage=ioc_leakage,
            field_conformance=field_conformance,
            selection_feasible=selection_feasible,
            final_pass=final_pass,
            errors=errors,
            warnings=warnings
        )
    
    def _check_telemetry_feasibility(
        self,
        rule_data: Dict[str, Any],
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check if logsource category/product combination is coherent."""
        logsource = rule_data.get('logsource', {})
        if not isinstance(logsource, dict):
            return False
        
        category = logsource.get('category')
        product = logsource.get('product')
        
        if not category and not product:
            warnings.append("Logsource has no category or product")
            return True  # Not an error, just a warning
        
        # Check valid combinations
        if category and product:
            combo = (category, product)
            if combo not in self.VALID_TELEMETRY_COMBINATIONS:
                # Check if it's a known invalid combination
                invalid_combos = {
                    ('network_connection', 'windows'),  # Should use specific network logsource
                }
                if combo in invalid_combos:
                    errors.append(f"Invalid logsource combination: {category} + {product}")
                    return False
        
        # Check for mismatches
        if category == 'process_creation' and product == 'linux':
            # This is valid
            pass
        elif category == 'registry_access' and product != 'windows':
            errors.append(f"Registry logsource requires Windows product, got {product}")
            return False
        
        return True
    
    def _check_condition_graph(
        self,
        rule_data: Dict[str, Any],
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Validate condition graph (all keys referenced exist, no unused selections)."""
        detection = rule_data.get('detection', {})
        if not isinstance(detection, dict):
            return False
        
        if 'condition' not in detection:
            errors.append("Missing detection condition")
            return False
        
        # Get all selection names
        selections = {k for k in detection.keys() if k not in ['condition', 'timeframe']}
        
        # Parse condition to find referenced selections
        condition = detection.get('condition')
        if isinstance(condition, str):
            # Simple condition like "selection" or "selection1 and selection2"
            referenced = set()
            for sel_name in selections:
                if sel_name in condition:
                    referenced.add(sel_name)
            
            # Check for unused selections
            unused = selections - referenced
            if unused:
                warnings.append(f"Unused selections: {', '.join(unused)}")
            
            # Check for referenced but missing selections
            # Extract selection names from condition string
            words = condition.split()
            for word in words:
                word_clean = word.strip('()|&!')
                if word_clean and word_clean not in selections and word_clean not in ['and', 'or', 'not', '1', 'all', 'of', 'them']:
                    # Might be a typo or missing selection
                    if word_clean.isalnum():
                        warnings.append(f"Condition references '{word_clean}' which may not exist")
        
        # Check for always-true logic (e.g., condition: "selection or not selection")
        # This is a simple check - could be enhanced
        if isinstance(condition, str) and ' or not ' in condition.lower():
            # Check if it's the same selection
            parts = condition.lower().split(' or not ')
            if len(parts) == 2 and parts[0].strip() == parts[1].strip():
                errors.append("Condition is always true (selection or not selection)")
                return False
        
        return True
    
    def _check_impossible_selections(
        self,
        rule_data: Dict[str, Any],
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Detect selections that require a single-value-per-event field to match incompatible values (never true)."""
        detection = rule_data.get('detection', {})
        if not isinstance(detection, dict):
            return False
        
        for sel_name, sel_value in detection.items():
            if sel_name in ('condition', 'timeframe'):
                continue
            if not isinstance(sel_value, dict):
                continue
            
            # Group constraints by base field: base_field -> list of (modifier, value_list)
            field_constraints = {}
            for key, val in sel_value.items():
                parts = key.replace('=', '|').split('|')
                base_field = (parts[0] or '').strip().title()
                if base_field not in self.SINGLE_VALUE_PER_EVENT_FIELDS:
                    continue
                modifier = (parts[1].lower() if len(parts) > 1 else '') or ''
                val_list = [val] if not isinstance(val, list) else list(val)
                val_list = [str(v).strip().lower() for v in val_list if v is not None]
                if not val_list:
                    continue
                if base_field not in field_constraints:
                    field_constraints[base_field] = []
                field_constraints[base_field].append((modifier, val_list))
            
            for base_field, constraints in field_constraints.items():
                if len(constraints) < 2:
                    continue
                # Collect values from identity-style modifiers (endswith, startswith, or direct).
                # contains can overlap so we do not treat "different contains" as impossible.
                identity_values = []
                for mod, vals in constraints:
                    if mod in ('endswith', 'startswith', '') or not mod:
                        identity_values.extend(vals)
                if not identity_values:
                    continue
                if len(set(identity_values)) > 1:
                    errors.append(
                        f"Selection requires field {base_field} to match multiple incompatible values (never true)"
                    )
                    return False
        
        return True
    
    def _check_pattern_safety(
        self,
        rule_data: Dict[str, Any],
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check for hazardous patterns (base64, excessive wildcards, etc.)."""
        detection = rule_data.get('detection', {})
        if not isinstance(detection, dict):
            return False
        
        issues_found = False
        
        def check_string_value(value: str, context: str):
            """Check a string value for hazardous patterns."""
            nonlocal issues_found
            
            # Check for base64 blobs > 40 chars
            base64_matches = self.base64_pattern.findall(value)
            for match in base64_matches:
                if len(match) > 40:
                    errors.append(f"{context}: Base64 blob detected (>40 chars): {match[:50]}...")
                    issues_found = True
            
            # Check for unanchored wildcards
            if '*' in value and not any(anchor in value for anchor in ['*', '|startswith', '|endswith', '|contains']):
                # Check if it's a dangerous pattern like (.*|.+)
                if re.search(r'\(\.\*\|\.\+\)', value):
                    errors.append(f"{context}: Dangerous regex pattern (.*|.+) detected")
                    issues_found = True
                elif value.strip() == '*' or value.strip() == '.*':
                    errors.append(f"{context}: Unanchored wildcard pattern")
                    issues_found = True
            
            # Check for multi-line regex
            if '\n' in value and ('|re' in value or '|regex' in value):
                errors.append(f"{context}: Multi-line regex detected")
                issues_found = True
            
            # Check for case-insensitive regex without flags
            if '|re' in value and '(?i)' not in value and '|nocase' not in value:
                # This might be intentional, so just a warning
                warnings.append(f"{context}: Case-sensitive regex - consider adding |nocase")
        
        # Recursively check all string values in detection
        def check_dict(d: Dict, path: str = "detection"):
            for key, value in d.items():
                if key == 'condition':
                    continue
                current_path = f"{path}.{key}"
                if isinstance(value, str):
                    check_string_value(value, current_path)
                elif isinstance(value, dict):
                    check_dict(value, current_path)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, str):
                            check_string_value(item, f"{current_path}[{i}]")
                        elif isinstance(item, dict):
                            check_dict(item, f"{current_path}[{i}]")
        
        check_dict(detection)
        
        return not issues_found
    
    def _check_ioc_leakage(
        self,
        rule_data: Dict[str, Any],
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """
        Check for IOC leakage (IPs, domains, JWTs, GUIDs).
        
        Returns True if IOC leakage detected (bad).
        """
        detection = rule_data.get('detection', {})
        if not isinstance(detection, dict):
            return False
        
        iocs_found = False
        
        def check_string_value(value: str, context: str):
            """Check a string value for IOCs."""
            nonlocal iocs_found
            
            # Check for IP addresses
            if self.ip_pattern.search(value):
                errors.append(f"{context}: IP address detected (IOC leakage)")
                iocs_found = True
            
            # Check for domains (but allow common benign patterns)
            domain_matches = self.domain_pattern.findall(value)
            for domain in domain_matches:
                # Allow common benign domains
                benign_domains = {'microsoft.com', 'windows.com', 'example.com', 'test.com'}
                if domain.lower() not in benign_domains:
                    errors.append(f"{context}: Domain detected (IOC leakage): {domain}")
                    iocs_found = True
            
            # Check for JWTs
            if self.jwt_pattern.search(value):
                errors.append(f"{context}: JWT token detected (IOC leakage)")
                iocs_found = True
            
            # Check for GUIDs (but be lenient - some are legitimate)
            guid_matches = self.guid_pattern.findall(value)
            for guid in guid_matches:
                # Common Windows GUIDs are OK
                common_guids = {
                    '00000000-0000-0000-0000-000000000000',
                    'ffffffff-ffff-ffff-ffff-ffffffffffff'
                }
                if guid.lower() not in common_guids:
                    warnings.append(f"{context}: GUID detected (may be IOC): {guid}")
                    # Don't fail on GUIDs, just warn
        
        # Recursively check all string values
        def check_dict(d: Dict, path: str = "detection"):
            for key, value in d.items():
                if key == 'condition':
                    continue
                current_path = f"{path}.{key}"
                if isinstance(value, str):
                    check_string_value(value, current_path)
                elif isinstance(value, dict):
                    check_dict(value, current_path)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, str):
                            check_string_value(item, f"{current_path}[{i}]")
                        elif isinstance(item, dict):
                            check_dict(item, f"{current_path}[{i}]")
        
        check_dict(detection)
        
        return iocs_found
    
    def _check_field_conformance(
        self,
        rule_data: Dict[str, Any],
        errors: List[str],
        warnings: List[str]
    ) -> bool:
        """Check that only valid Windows process-creation fields are used."""
        logsource = rule_data.get('logsource', {})
        if not isinstance(logsource, dict):
            return False
        
        category = logsource.get('category')
        product = logsource.get('product')
        
        # Only check process_creation on Windows
        if category != 'process_creation' or product != 'windows':
            return True  # Not applicable
        
        detection = rule_data.get('detection', {})
        if not isinstance(detection, dict):
            return False
        
        invalid_fields = []
        
        def check_dict(d: Dict, path: str = "detection"):
            """Recursively check for invalid field names."""
            for key, value in d.items():
                if key == 'condition' or key == 'timeframe':
                    continue
                
                # Check if key looks like a field name (contains = or |)
                if '=' in key or '|' in key:
                    field_name = key.split('=')[0].split('|')[0].strip()
                    if field_name not in self.VALID_PROCESS_CREATION_FIELDS:
                        invalid_fields.append(f"{path}.{key} (field: {field_name})")
                
                if isinstance(value, dict):
                    check_dict(value, f"{path}.{key}")
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            check_dict(item, f"{path}.{key}[{i}]")
        
        check_dict(detection)
        
        if invalid_fields:
            errors.append(f"Invalid fields for Windows process_creation: {', '.join(invalid_fields)}")
            return False
        
        return True

