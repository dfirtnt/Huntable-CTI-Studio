#!/usr/bin/env python3
"""
Standalone script to compare two SIGMA rules using the behavioral novelty algorithm.

This script uses the same algorithm as the similarity search: atom Jaccard similarity
and logic shape similarity, without requiring embeddings or database connections.

Usage:
    python3 scripts/compare_sigma_rules.py <rule1.yaml> <rule2.yaml>

Dependencies:
    - yaml (PyYAML)
    - Standard library only
"""

import sys
import yaml
import json
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional, Union
from dataclasses import dataclass, asdict


# ============================================================================
# Data Structures (from sigma_novelty_service.py)
# ============================================================================

@dataclass
class Atom:
    """Atomic predicate representing one irreducible behavioral constraint."""
    field: str
    op: str  # Primary operator (e.g., "contains", "endswith", "re")
    op_type: str  # "literal" or "regex"
    value: str
    value_type: str  # "string", "int", "float", "bool"
    polarity: str  # "positive" or "negative"


@dataclass
class CanonicalRule:
    """Canonical representation of a SIGMA rule."""
    version: str = "1.2"
    logsource: Dict[str, str] = None
    detection: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.logsource is None:
            self.logsource = {}
        if self.detection is None:
            self.detection = {"atoms": [], "logic": {}}


# ============================================================================
# Configuration (from sigma_novelty_service.py)
# ============================================================================

AGGRESSIVE_NORMALIZATION_FIELDS = {
    'CommandLine', 'ProcessCommandLine', 'ParentCommandLine'
}

FIELD_ALIAS_MAP = {
    'CommandLine': 'CommandLine',
    'ProcessCommandLine': 'CommandLine',
    'Image': 'Image',
    'ProcessPath': 'Image',
    'NewProcessName': 'Image',
    'ExecutablePath': 'Image',
    'ParentImage': 'ParentImage',
    'ParentProcessPath': 'ParentImage',
    'ParentProcessName': 'ParentImage',
    'DestinationIp': 'DestinationIp',
    'DestinationIpAddress': 'DestinationIp',
    'DestIp': 'DestinationIp',
    'SourceIp': 'SourceIp',
    'SourceIpAddress': 'SourceIp',
    'SrcIp': 'SourceIp',
    'DestinationPort': 'DestinationPort',
    'DestPort': 'DestinationPort',
    'SourcePort': 'SourcePort',
    'SrcPort': 'SourcePort',
    'QueryName': 'DnsQuery',
    'DnsQuery': 'DnsQuery',
    'Query': 'DnsQuery',
    'TargetFilename': 'FilePath',
    'TargetFileName': 'FilePath',
    'FileName': 'FilePath',
    'FilePath': 'FilePath',
    'TargetObject': 'RegistryPath',
    'RegistryKey': 'RegistryPath',
    'RegistryPath': 'RegistryPath',
}

SERVICE_PENALTY = 0.05


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_field_with_modifiers(field_name: str) -> Tuple[str, List[str]]:
    """Parse field name to extract base field and modifiers."""
    if '|' not in field_name:
        return field_name, []
    parts = field_name.split('|')
    return parts[0], parts[1:] if len(parts) > 1 else []


def _infer_value_type(value: Any) -> str:
    """Infer value type for atom."""
    if isinstance(value, int):
        return "int"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, bool):
        return "bool"
    else:
        return "string"


def _normalize_conservative(value: Any) -> Any:
    """Conservative normalization: trim whitespace, normalize slashes."""
    if isinstance(value, str):
        normalized = value.strip().replace('\\', '/')
        return normalized
    elif isinstance(value, list):
        return [_normalize_conservative(v) for v in value]
    else:
        return value


def _normalize_aggressive(value: Any) -> Any:
    """Aggressive normalization for CommandLine fields."""
    if isinstance(value, str):
        normalized = re.sub(r'\s+', ' ', value.strip())
        normalized = normalized.replace('"', "'").replace('\\', '/')
        return normalized
    elif isinstance(value, list):
        return [_normalize_aggressive(v) for v in value]
    else:
        return value


def normalize_logsource(logsource: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Normalize logsource to product|category key and extract service."""
    if not isinstance(logsource, dict):
        return "|", None
    
    product = logsource.get('product', '').lower().strip() if logsource.get('product') else ''
    category = logsource.get('category', '').lower().strip() if logsource.get('category') else ''
    service = logsource.get('service', '').lower().strip() if logsource.get('service') else None
    
    return f"{product}|{category}", service


# ============================================================================
# Atom Extraction (from sigma_novelty_service.py)
# ============================================================================

def extract_atomic_predicates(detection: Dict[str, Any]) -> List[Atom]:
    """Extract atomic predicates from detection block."""
    atoms = []
    
    if not isinstance(detection, dict):
        return atoms
    
    for key, value in detection.items():
        if key == 'condition':
            continue
        
        if not isinstance(value, dict):
            continue
        
        for field_name, field_value in value.items():
            base_field, modifiers = _parse_field_with_modifiers(field_name)
            
            # Apply field alias normalization
            base_field_lower = base_field.lower() if base_field else ''
            canonical_field = base_field
            for map_key, map_value in FIELD_ALIAS_MAP.items():
                if map_key.lower() == base_field_lower:
                    canonical_field = map_value
                    break
            if canonical_field == base_field and base_field:
                canonical_field = base_field[0].upper() + base_field[1:] if len(base_field) > 1 else base_field.upper()
            
            # Normalize modifiers
            normalized_modifiers = []
            for mod in modifiers:
                if mod.lower() != 'all':
                    normalized_modifiers.append(mod)
            
            # Determine primary operator
            primary_op = normalized_modifiers[0].lower() if normalized_modifiers else 'contains'
            op_type = 'regex' if primary_op == 're' else 'literal'
            
            # Determine polarity
            polarity = "positive"
            if key.startswith('filter') or 'not' in str(detection.get('condition', '')).lower():
                condition = str(detection.get('condition', '')).lower()
                if f'not {key}' in condition or f'not {base_field}' in condition:
                    polarity = "negative"
            
            # Explode lists into separate atoms
            if isinstance(field_value, list):
                for item in field_value:
                    atoms.append(Atom(
                        field=canonical_field,
                        op=primary_op,
                        op_type=op_type,
                        value=str(item),
                        value_type=_infer_value_type(item),
                        polarity=polarity
                    ))
            else:
                atoms.append(Atom(
                    field=canonical_field,
                    op=primary_op,
                    op_type=op_type,
                    value=str(field_value),
                    value_type=_infer_value_type(field_value),
                    polarity=polarity
                ))
    
    return atoms


# ============================================================================
# Logic Canonicalization (simplified)
# ============================================================================

def canonicalize_detection_logic(detection: Dict[str, Any], atoms: List[Atom]) -> Dict[str, Any]:
    """Canonicalize detection logic into deterministic form (simplified)."""
    condition = detection.get('condition', '')
    
    # Simple conversion: map selections to atom indices
    selection_to_atoms = {}
    atom_idx = 0
    
    for key, value in detection.items():
        if key == 'condition':
            continue
        if not isinstance(value, dict):
            continue
        
        field_indices = []
        for field_name, field_value in value.items():
            if isinstance(field_value, list):
                field_indices.extend(range(atom_idx, atom_idx + len(field_value)))
                atom_idx += len(field_value)
            else:
                field_indices.append(atom_idx)
                atom_idx += 1
        
        if field_indices:
            if len(field_indices) == 1:
                selection_to_atoms[key] = {"ATOM": field_indices[0]}
            else:
                selection_to_atoms[key] = {"OR": [{"ATOM": idx} for idx in field_indices]}
    
    # Parse condition (simplified - assumes simple AND/OR)
    if not condition:
        # Default: AND of all selections
        if selection_to_atoms:
            selections = list(selection_to_atoms.values())
            if len(selections) == 1:
                return selections[0]
            return {"AND": selections}
        return {}
    
    # Simple condition parsing (handles: selection1 and selection2, selection1 or selection2)
    condition_lower = condition.lower()
    if ' and ' in condition_lower or '&' in condition:
        parts = re.split(r'\s+(?:and|&)\s+', condition, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts]
        logic_parts = [selection_to_atoms.get(p, {"ATOM": 0}) for p in parts if p in selection_to_atoms]
        if len(logic_parts) == 1:
            return logic_parts[0]
        return {"AND": logic_parts} if logic_parts else {}
    elif ' or ' in condition_lower or '|' in condition:
        parts = re.split(r'\s+(?:or|\|)\s+', condition, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts]
        logic_parts = [selection_to_atoms.get(p, {"ATOM": 0}) for p in parts if p in selection_to_atoms]
        if len(logic_parts) == 1:
            return logic_parts[0]
        return {"OR": logic_parts} if logic_parts else {}
    else:
        # Single selection
        if condition in selection_to_atoms:
            return selection_to_atoms[condition]
        return {}


# ============================================================================
# Canonical Rule Building
# ============================================================================

def build_canonical_rule(rule_data: Dict[str, Any]) -> CanonicalRule:
    """Build canonical rule from SIGMA rule data."""
    logsource_key, _ = normalize_logsource(rule_data.get('logsource', {}))
    product, category = logsource_key.split('|') if '|' in logsource_key else ('', '')
    
    detection = rule_data.get('detection', {})
    atoms = extract_atomic_predicates(detection)
    logic = canonicalize_detection_logic(detection, atoms)
    
    return CanonicalRule(
        version="1.2",
        logsource={"product": product, "category": category},
        detection={
            "atoms": [asdict(atom) for atom in atoms],
            "logic": logic
        }
    )


# ============================================================================
# Similarity Computation
# ============================================================================

def _atom_to_key(atom: Union[Dict[str, Any], Atom]) -> str:
    """Convert atom to normalized key for comparison."""
    if isinstance(atom, Atom):
        return f"{atom.field}|{atom.op}|{atom.op_type}|{atom.value}"
    else:
        field = atom.get('field', '')
        op = atom.get('op', '')
        op_type = atom.get('op_type', 'literal')
        value = atom.get('value', '')
        return f"{field}|{op}|{op_type}|{value}"


def compute_atom_jaccard(rule1: CanonicalRule, rule2: CanonicalRule) -> float:
    """Compute Jaccard similarity over positive atoms only."""
    atoms1 = rule1.detection.get('atoms', [])
    atoms2 = rule2.detection.get('atoms', [])
    
    positive_atoms1 = [a for a in atoms1 if a.get('polarity', 'positive') == 'positive']
    positive_atoms2 = [a for a in atoms2 if a.get('polarity', 'positive') == 'positive']
    
    set1 = {_atom_to_key(a) for a in positive_atoms1}
    set2 = {_atom_to_key(a) for a in positive_atoms2}
    
    if not set1 and not set2:
        return 1.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0


def _count_nodes(logic: Dict[str, Any]) -> int:
    """Count total nodes in logic tree."""
    if 'ATOM' in logic:
        return 1
    elif 'AND' in logic or 'OR' in logic:
        operands = logic.get('AND', logic.get('OR', []))
        return 1 + sum(_count_nodes(op) for op in operands)
    elif 'NOT' in logic:
        return 1 + _count_nodes(logic['NOT'])
    else:
        return 0


def _count_operator(logic: Dict[str, Any], op_name: str) -> int:
    """Count occurrences of specific operator."""
    count = 0
    if op_name in logic:
        count = 1
        if op_name == 'NOT':
            count += _count_operator(logic[op_name], op_name)
        else:
            operands = logic.get(op_name, [])
            for op in operands:
                count += _count_operator(op, op_name)
    elif 'AND' in logic or 'OR' in logic:
        operands = logic.get('AND', logic.get('OR', []))
        for op in operands:
            count += _count_operator(op, op_name)
    elif 'NOT' in logic:
        count += _count_operator(logic['NOT'], op_name)
    
    return count


def _compute_logic_depth(logic: Dict[str, Any]) -> int:
    """Compute maximum depth of logic tree."""
    if 'ATOM' in logic:
        return 1
    elif 'AND' in logic or 'OR' in logic:
        operands = logic.get('AND', logic.get('OR', []))
        if operands:
            return 1 + max(_compute_logic_depth(op) for op in operands)
        return 1
    elif 'NOT' in logic:
        return 1 + _compute_logic_depth(logic['NOT'])
    else:
        return 0


def _compute_logic_metrics(logic: Dict[str, Any]) -> Dict[str, int]:
    """Compute logic metrics."""
    return {
        'node_count': _count_nodes(logic),
        'and_count': _count_operator(logic, 'AND'),
        'or_count': _count_operator(logic, 'OR'),
        'not_count': _count_operator(logic, 'NOT'),
        'max_depth': _compute_logic_depth(logic)
    }


def compute_logic_shape_similarity(rule1: CanonicalRule, rule2: CanonicalRule) -> float:
    """Compute similarity of logic AST shapes."""
    logic1 = rule1.detection.get('logic', {})
    logic2 = rule2.detection.get('logic', {})
    
    str1 = json.dumps(logic1, sort_keys=True)
    str2 = json.dumps(logic2, sort_keys=True)
    
    if str1 == str2:
        return 1.0
    
    metrics1 = _compute_logic_metrics(logic1)
    metrics2 = _compute_logic_metrics(logic2)
    
    distances = []
    weights = {
        'node_count': 0.3,
        'and_count': 0.2,
        'or_count': 0.2,
        'not_count': 0.1,
        'max_depth': 0.2
    }
    normalization_factor = 10.0
    
    for metric_name, weight in weights.items():
        val1 = metrics1.get(metric_name, 0)
        val2 = metrics2.get(metric_name, 0)
        max_val = max(val1, val2, 1)
        diff = abs(val1 - val2) / (max_val + normalization_factor)
        distances.append(weight * diff)
    
    similarity = 1.0 - sum(distances)
    return max(0.0, min(1.0, similarity))


def _compute_service_penalty(service1: Optional[str], service2: Optional[str]) -> float:
    """Compute service mismatch penalty."""
    if service1 and service2:
        if service1 != service2:
            return SERVICE_PENALTY
    return 0.0


def _compute_filter_penalty(rule1: CanonicalRule, rule2: CanonicalRule) -> float:
    """Compute filter divergence penalty."""
    atoms1 = rule1.detection.get('atoms', [])
    atoms2 = rule2.detection.get('atoms', [])
    
    negative_atoms1 = [a for a in atoms1 if a.get('polarity', 'positive') == 'negative']
    negative_atoms2 = [a for a in atoms2 if a.get('polarity', 'positive') == 'negative']
    
    if not negative_atoms1 and not negative_atoms2:
        return 0.0
    
    set1 = {_atom_to_key(a) for a in negative_atoms1}
    set2 = {_atom_to_key(a) for a in negative_atoms2}
    
    if not set1 and not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    filter_jaccard = intersection / union if union > 0 else 0.0
    
    jaccard_threshold = 0.5
    max_penalty = 0.10
    
    if filter_jaccard < jaccard_threshold:
        penalty = max_penalty * (1.0 - filter_jaccard)
        return min(penalty, max_penalty)
    
    return 0.0


def compute_weighted_similarity(
    atom_jaccard: float,
    logic_similarity: float,
    service_penalty: float = 0.0,
    filter_penalty: float = 0.0
) -> float:
    """Compute weighted similarity score with penalties."""
    similarity = (
        0.70 * atom_jaccard +
        0.30 * logic_similarity -
        service_penalty -
        filter_penalty
    )
    return max(0.0, min(1.0, similarity))


# ============================================================================
# Main Comparison Logic
# ============================================================================

def load_rule_file(file_path: str) -> Dict[str, Any]:
    """Load and parse a SIGMA YAML rule file (handles RTF files with YAML content)."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # If RTF file, try to extract YAML content
        if file_path.lower().endswith('.rtf'):
            # RTF files often contain YAML wrapped in RTF formatting
            # Try to find YAML block (look for common YAML patterns)
            yaml_patterns = [
                r'```yaml\s*\n(.*?)\n```',  # Markdown code block
                r'---\s*\n(.*?)\n---',      # YAML document separator
                r'(title:\s*.*?)(?:\n\n|\Z)',  # YAML content
            ]
            
            yaml_content = None
            for pattern in yaml_patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    yaml_content = match.group(1)
                    break
            
            # If no pattern match, try to extract text between braces or after RTF header
            if not yaml_content:
                # Remove RTF control words (simplified)
                yaml_content = re.sub(r'\\[a-z]+\d*\s?', '', content)
                yaml_content = re.sub(r'\{[^}]*\}', '', yaml_content)
                yaml_content = yaml_content.strip()
            
            if yaml_content:
                rule_data = yaml.safe_load(yaml_content)
            else:
                raise ValueError(f"Could not extract YAML content from RTF file: {file_path}")
        else:
            rule_data = yaml.safe_load(content)
        
        if not rule_data:
            raise ValueError(f"Empty or invalid YAML file: {file_path}")
        return rule_data
    except yaml.YAMLError as e:
        print(f"YAML parsing error in {file_path}: {e}", file=sys.stderr)
        print("Note: If this is an RTF file, ensure it contains valid YAML content.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading rule file {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


def compare_rules(rule1_path: str, rule2_path: str) -> Dict[str, Any]:
    """Compare two SIGMA rules using the behavioral novelty algorithm."""
    # Load rules
    rule1_data = load_rule_file(rule1_path)
    rule2_data = load_rule_file(rule2_path)
    
    # Build canonical rules
    canonical_rule1 = build_canonical_rule(rule1_data)
    canonical_rule2 = build_canonical_rule(rule2_data)
    
    # Extract logsource info for service penalty
    _, service1 = normalize_logsource(rule1_data.get('logsource', {}))
    _, service2 = normalize_logsource(rule2_data.get('logsource', {}))
    
    # Compute metrics
    atom_jaccard = compute_atom_jaccard(canonical_rule1, canonical_rule2)
    logic_similarity = compute_logic_shape_similarity(canonical_rule1, canonical_rule2)
    service_penalty = _compute_service_penalty(service1, service2)
    filter_penalty = _compute_filter_penalty(canonical_rule1, canonical_rule2)
    
    # Early exit for perfect match
    if atom_jaccard == 1.0 and service_penalty == 0.0 and filter_penalty == 0.0:
        weighted_sim = 1.0
    else:
        weighted_sim = compute_weighted_similarity(
            atom_jaccard, logic_similarity, service_penalty, filter_penalty
        )
    
    # Build result
    result = {
        'rule1': {
            'file': rule1_path,
            'id': rule1_data.get('id', 'N/A'),
            'title': rule1_data.get('title', 'N/A')
        },
        'rule2': {
            'file': rule2_path,
            'id': rule2_data.get('id', 'N/A'),
            'title': rule2_data.get('title', 'N/A')
        },
        'similarity_metrics': {
            'atom_jaccard': round(atom_jaccard, 4),
            'logic_shape_similarity': round(logic_similarity, 4),
            'service_penalty': round(service_penalty, 4),
            'filter_penalty': round(filter_penalty, 4)
        },
        'weighted_similarity': round(weighted_sim, 4),
        'algorithm': {
            'name': 'behavioral_novelty',
            'version': '1.2',
            'formula': '0.70 * atom_jaccard + 0.30 * logic_similarity - service_penalty - filter_penalty'
        }
    }
    
    return result


def main():
    """Main entry point."""
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <rule1.yaml> <rule2.yaml>", file=sys.stderr)
        sys.exit(1)
    
    rule1_path = sys.argv[1]
    rule2_path = sys.argv[2]
    
    # Validate files exist
    if not Path(rule1_path).exists():
        print(f"Error: Rule file not found: {rule1_path}", file=sys.stderr)
        sys.exit(1)
    
    if not Path(rule2_path).exists():
        print(f"Error: Rule file not found: {rule2_path}", file=sys.stderr)
        sys.exit(1)
    
    # Compare rules
    try:
        result = compare_rules(rule1_path, rule2_path)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error comparing rules: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
