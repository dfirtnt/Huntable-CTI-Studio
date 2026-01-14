"""
SIGMA Rule Behavioral Novelty Assessment Service

Determines whether a newly submitted SIGMA rule is BEHAVIORALLY NOVEL
relative to an existing SIGMA rule repository.

Behavioral novelty answers: "Does this rule detect meaningfully new telemetry behavior?"
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from enum import Enum

logger = logging.getLogger(__name__)


class NoveltyLabel(str, Enum):
    """Novelty classification labels."""
    DUPLICATE = "DUPLICATE"
    SIMILAR = "SIMILAR"
    NOVEL = "NOVEL"


@dataclass
class Atom:
    """Atomic predicate representing one irreducible behavioral constraint."""
    field: str
    op: str  # Primary operator (e.g., "contains", "endswith", "re")
    op_type: str  # "literal" or "regex" (determined by operator)
    value: str
    value_type: str  # "string", "int", "float", "bool"
    polarity: str  # "positive" or "negative" (NOT logic)


@dataclass
class CanonicalRule:
    """Canonical representation of a SIGMA rule."""
    version: str = "1.0"
    logsource: Dict[str, str] = None  # {"product": "...", "category": "..."}
    detection: Dict[str, Any] = None  # {"atoms": [...], "logic": {...}}
    
    def __post_init__(self):
        if self.logsource is None:
            self.logsource = {}
        if self.detection is None:
            self.detection = {"atoms": [], "logic": {}}


class SigmaNoveltyService:
    """Service for assessing behavioral novelty of SIGMA rules (v1.2)."""
    
    # Canonical version
    CANONICAL_VERSION = "1.2"
    
    # Fields that require aggressive normalization
    AGGRESSIVE_NORMALIZATION_FIELDS = {
        'CommandLine', 'ProcessCommandLine', 'ParentCommandLine'
    }
    
    # Field alias map (v1.2) - maps equivalent field names to canonical form
    FIELD_ALIAS_MAP = {
        # Process execution
        'CommandLine': 'CommandLine',
        'ProcessCommandLine': 'CommandLine',
        'Image': 'Image',
        'ProcessPath': 'Image',
        'NewProcessName': 'Image',
        'ExecutablePath': 'Image',
        'ParentImage': 'ParentImage',
        'ParentProcessPath': 'ParentImage',
        'ParentProcessName': 'ParentImage',
        # Network
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
        # DNS
        'QueryName': 'DnsQuery',
        'DnsQuery': 'DnsQuery',
        'Query': 'DnsQuery',
        # File system
        'TargetFilename': 'FilePath',
        'TargetFileName': 'FilePath',
        'FileName': 'FilePath',
        'FilePath': 'FilePath',
        # Registry
        'TargetObject': 'RegistryPath',
        'RegistryKey': 'RegistryPath',
        'RegistryPath': 'RegistryPath',
    }
    
    # Service penalty configuration (v1.2)
    SERVICE_PENALTY = 0.05
    
    def __init__(self, db_session=None):
        """
        Initialize the novelty service.
        
        Args:
            db_session: Optional SQLAlchemy session for database queries
        """
        self.db_session = db_session
    
    def assess_novelty(
        self,
        proposed_rule: Dict[str, Any],
        threshold: float = 0.0,
        top_k: int = 20
    ) -> Dict[str, Any]:
        """
        Assess behavioral novelty of a proposed SIGMA rule.
        
        Args:
            proposed_rule: SIGMA rule dictionary (from YAML parse)
            threshold: Minimum similarity threshold (0-1)
            top_k: Maximum number of candidates to retrieve
            
        Returns:
            Dictionary with novelty classification and explainability
        """
        try:
            # Step 1: Build canonical rule
            canonical_rule = self.build_canonical_rule(proposed_rule)
            
            # Step 2: Generate fingerprints
            exact_hash = self.generate_exact_hash(canonical_rule)
            canonical_text = self.generate_canonical_text(canonical_rule)
            logsource_key, proposed_service = self.normalize_logsource(proposed_rule.get('logsource', {}))
            
            # Step 3: Retrieve candidates (hard gate: same logsource_key)
            logger.debug(f"Retrieving candidates for logsource_key: '{logsource_key}'")
            candidates = self.retrieve_candidates(
                exact_hash=exact_hash,
                logsource_key=logsource_key,
                top_k=top_k
            )
            logger.debug(f"Retrieved {len(candidates)} candidates for logsource_key '{logsource_key}'")
            
            # Step 4: Compute similarity metrics for each candidate
            matches = []
            for candidate in candidates:
                # Parse candidate rule if needed
                if isinstance(candidate, dict):
                    candidate_canonical = self.build_canonical_rule(candidate)
                else:
                    # Assume it's already a CanonicalRule
                    candidate_canonical = candidate
                
                # Compute metrics
                atom_jaccard = self.compute_atom_jaccard(
                    canonical_rule, candidate_canonical
                )
                
                # Compute service penalty (v1.2)
                candidate_service = None
                if isinstance(candidate, dict):
                    _, candidate_service = self.normalize_logsource(candidate.get('logsource', {}))
                service_penalty = self._compute_service_penalty(proposed_service, candidate_service)
                
                # Compute filter divergence penalty (v1.2)
                filter_penalty = self._compute_filter_penalty(canonical_rule, candidate_canonical)
                
                # Early exit for proven event equivalence (v1.2)
                # If all atoms are identical, no service mismatch, and no filter divergence,
                # the rules match the exact same EDR events - return 1.0 immediately
                if atom_jaccard == 1.0 and service_penalty == 0.0 and filter_penalty == 0.0:
                    weighted_sim = 1.0
                    logic_similarity = None  # Not computed - N/A when atoms are identical
                else:
                    # Compute logic shape similarity only if needed
                    logic_similarity = self.compute_logic_shape_similarity(
                        canonical_rule, candidate_canonical
                    )
                    
                    # Weighted similarity with penalties
                    weighted_sim = self.compute_weighted_similarity(
                        atom_jaccard, logic_similarity,
                        service_penalty=service_penalty, filter_penalty=filter_penalty
                    )
                
                if weighted_sim >= threshold:
                    # Generate explainability
                    explainability = self.generate_explainability(
                        canonical_rule, candidate_canonical, candidate
                    )
                    
                    matches.append({
                        'rule_id': candidate.get('rule_id', '') if isinstance(candidate, dict) else '',
                        'atom_jaccard': atom_jaccard,
                        'logic_shape_similarity': logic_similarity,
                        'similarity': weighted_sim,
                        **explainability
                    })
            
            # Sort by similarity (descending)
            matches.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Step 5: Classify novelty
            novelty_label, novelty_score = self.classify_novelty(
                exact_hash, matches
            )
            
            return {
                'novelty_label': novelty_label,
                'novelty_score': novelty_score,
                'logsource_key': logsource_key,
                'exact_hash': exact_hash,
                'top_matches': matches[:10],  # Top 10 for explainability
                'canonical_rule': asdict(canonical_rule)  # For debugging
            }
            
        except Exception as e:
            logger.error(f"Failed to assess novelty: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'novelty_label': NoveltyLabel.NOVEL,
                'novelty_score': 1.0,
                'logsource_key': '',
                'error': str(e),
                'top_matches': []
            }
    
    def build_canonical_rule(self, rule_data: Dict[str, Any]) -> CanonicalRule:
        """
        Build canonical rule from SIGMA rule data.
        
        Args:
            rule_data: Parsed SIGMA rule dictionary
            
        Returns:
            CanonicalRule object
        """
        # Normalize logsource
        logsource_key, _ = self.normalize_logsource(rule_data.get('logsource', {}))
        product, category = logsource_key.split('|') if '|' in logsource_key else ('', '')
        
        # Extract atoms from detection
        detection = rule_data.get('detection', {})
        atoms = self.extract_atomic_predicates(detection)
        
        # Canonicalize detection logic
        logic = self.canonicalize_detection_logic(detection, atoms)
        
        return CanonicalRule(
            version=self.CANONICAL_VERSION,
            logsource={"product": product, "category": category},
            detection={
                "atoms": [asdict(atom) for atom in atoms],
                "logic": logic
            }
        )
    
    def normalize_logsource(self, logsource: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        Normalize logsource to product|category key and extract service (v1.2).
        
        Args:
            logsource: Logsource dictionary
            
        Returns:
            Tuple of (logsource_key, service) where logsource_key is "product|category"
        """
        if not isinstance(logsource, dict):
            logger.warning(f"Invalid logsource type: {type(logsource)}, expected dict")
            return "|", None
        
        product = logsource.get('product', '').lower().strip() if logsource.get('product') else ''
        category = logsource.get('category', '').lower().strip() if logsource.get('category') else ''
        service = logsource.get('service', '').lower().strip() if logsource.get('service') else None
        
        logsource_key = f"{product}|{category}"
        logger.debug(f"Normalized logsource: {logsource} -> '{logsource_key}' (service: {service})")
        return logsource_key, service
    
    def normalize_detection(
        self,
        detection: Dict[str, Any],
        field_name: str
    ) -> Dict[str, Any]:
        """
        Normalize detection values with field-aware normalization.
        
        Args:
            detection: Detection dictionary
            field_name: Field name being normalized
            
        Returns:
            Normalized detection dictionary
        """
        if not isinstance(detection, dict):
            return detection
        
        normalized = {}
        
        for key, value in detection.items():
            if key == 'condition':
                normalized[key] = value
                continue
            
            # Normalize field values
            if isinstance(value, dict):
                normalized[key] = {}
                for field, field_value in value.items():
                    base_field, modifiers = self._parse_field_with_modifiers(field)
                    
                    # Apply normalization based on field type
                    if base_field in self.AGGRESSIVE_NORMALIZATION_FIELDS:
                        normalized_value = self._normalize_aggressive(field_value)
                    else:
                        normalized_value = self._normalize_conservative(field_value)
                    
                    # Reconstruct field with modifiers
                    if modifiers:
                        field_key = f"{base_field}|{'|'.join(modifiers)}"
                    else:
                        field_key = base_field
                    
                    normalized[key][field_key] = normalized_value
            else:
                normalized[key] = value
        
        return normalized
    
    def _normalize_conservative(self, value: Any) -> Any:
        """Conservative normalization: trim whitespace, normalize slashes."""
        if isinstance(value, str):
            # Trim whitespace
            normalized = value.strip()
            # Normalize path separators (Windows <-> Unix)
            normalized = normalized.replace('\\', '/')
            return normalized
        elif isinstance(value, list):
            return [self._normalize_conservative(v) for v in value]
        else:
            return value
    
    def _normalize_aggressive(self, value: Any) -> Any:
        """Aggressive normalization for CommandLine fields."""
        if isinstance(value, str):
            # Collapse repeated whitespace
            normalized = re.sub(r'\s+', ' ', value.strip())
            # Normalize quoting
            normalized = normalized.replace('"', "'")
            # Normalize path separators
            normalized = normalized.replace('\\', '/')
            # TODO: Normalize argument ordering when semantics imply sets
            return normalized
        elif isinstance(value, list):
            return [self._normalize_aggressive(v) for v in value]
        else:
            return value
    
    def extract_atomic_predicates(self, detection: Dict[str, Any]) -> List[Atom]:
        """
        Extract atomic predicates from detection block.
        
        Lists are exploded into separate atoms. Logic explicitly represents OR/AND.
        
        Normalizes `contains|all` to separate `contains` atoms (semantically equivalent
        to multiple `contains` checks combined with AND logic).
        
        Args:
            detection: Detection dictionary
            
        Returns:
            List of Atom objects
        """
        atoms = []
        
        if not isinstance(detection, dict):
            return atoms
        
        # Process all selection blocks
        for key, value in detection.items():
            if key == 'condition':
                continue
            
            if not isinstance(value, dict):
                continue
            
            # Extract atoms from this selection
            for field_name, field_value in value.items():
                base_field, modifiers = self._parse_field_with_modifiers(field_name)
                
                # Apply field alias normalization (v1.2)
                # Make lookup case-insensitive (map uses title case)
                base_field_lower = base_field.lower() if base_field else ''
                # Find matching key in map (case-insensitive)
                canonical_field = base_field
                for map_key, map_value in self.FIELD_ALIAS_MAP.items():
                    if map_key.lower() == base_field_lower:
                        canonical_field = map_value
                        break
                # If no match found, use title case version of original
                if canonical_field == base_field and base_field:
                    canonical_field = base_field[0].upper() + base_field[1:] if len(base_field) > 1 else base_field.upper()
                
                # Normalize `contains|all` to `contains` - semantically equivalent
                # `contains|all: [a, b, c]` means "all of a, b, c must be present"
                # which is equivalent to `contains: a AND contains: b AND contains: c`
                normalized_modifiers = []
                has_all_modifier = False
                for mod in modifiers:
                    if mod.lower() == 'all':
                        has_all_modifier = True
                        # Don't add 'all' to ops - it's handled by condition logic
                    else:
                        normalized_modifiers.append(mod)
                
                # Determine primary operator and op_type (v1.2)
                if normalized_modifiers:
                    primary_op = normalized_modifiers[0].lower()
                else:
                    primary_op = 'contains'  # Default operator
                
                # Determine op_type: regex if operator is 're', otherwise literal
                op_type = 'regex' if primary_op == 're' else 'literal'
                
                # Determine polarity (check for NOT in condition or filter blocks)
                polarity = "positive"
                if key.startswith('filter') or 'not' in str(detection.get('condition', '')).lower():
                    # Check if this field is negated in condition
                    condition = str(detection.get('condition', '')).lower()
                    if f'not {key}' in condition or f'not {base_field}' in condition:
                        polarity = "negative"
                
                # Explode lists into separate atoms
                # For `contains|all`, each value becomes a separate atom (AND semantics)
                if isinstance(field_value, list):
                    for item in field_value:
                        atom = Atom(
                            field=canonical_field,
                            op=primary_op,
                            op_type=op_type,
                            value=str(item),
                            value_type=self._infer_value_type(item),
                            polarity=polarity
                        )
                        atoms.append(atom)
                else:
                    atom = Atom(
                        field=canonical_field,
                        op=primary_op,
                        op_type=op_type,
                        value=str(field_value),
                        value_type=self._infer_value_type(field_value),
                        polarity=polarity
                    )
                    atoms.append(atom)
        
        return atoms
    
    def _parse_field_with_modifiers(self, field_name: str) -> Tuple[str, List[str]]:
        """Parse field name to extract base field and modifiers."""
        if '|' not in field_name:
            return field_name, []
        
        parts = field_name.split('|')
        base_field = parts[0]
        modifiers = parts[1:] if len(parts) > 1 else []
        
        return base_field, modifiers
    
    def _infer_value_type(self, value: Any) -> str:
        """Infer value type for atom."""
        if isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, bool):
            return "bool"
        else:
            return "string"
    
    def parse_condition_ast(self, condition: str) -> Dict[str, Any]:
        """
        Parse condition string into AST.
        
        Supports: and/or/not, parentheses, 1 of/all of macros.
        
        Args:
            condition: Condition string (e.g., "selection1 and (selection2 or selection3)")
            
        Returns:
            AST dictionary
        """
        if not condition:
            return {"type": "empty"}
        
        # Tokenize
        tokens = self._tokenize_condition(condition)
        
        # Parse into AST
        ast = self._parse_tokens(tokens)
        
        return ast
    
    def _tokenize_condition(self, condition: str) -> List[str]:
        """Tokenize condition string."""
        # Normalize whitespace
        condition = re.sub(r'\s+', ' ', condition.strip())
        
        # Split on operators and parentheses
        tokens = []
        current = ""
        
        for char in condition:
            if char in '()':
                if current.strip():
                    tokens.append(current.strip())
                    current = ""
                tokens.append(char)
            elif char in '&|!':
                if current.strip():
                    tokens.append(current.strip())
                    current = ""
                tokens.append(char)
            else:
                current += char
        
        if current.strip():
            tokens.append(current.strip())
        
        return tokens
    
    def _parse_tokens(self, tokens: List[str]) -> Dict[str, Any]:
        """Parse tokens into AST (simplified recursive descent)."""
        if not tokens:
            return {"type": "empty"}
        
        # Simple parser for: selection, and, or, not, parentheses, 1 of, all of
        # This is a simplified implementation - full parser would handle precedence
        
        i = 0
        
        def parse_expression():
            nonlocal i
            left = parse_term()
            
            while i < len(tokens) and tokens[i].lower() in ['and', 'or', '&', '|']:
                op = tokens[i].lower()
                if op in ['&', 'and']:
                    op = 'and'
                elif op in ['|', 'or']:
                    op = 'or'
                i += 1
                right = parse_term()
                left = {"type": op, "left": left, "right": right}
            
            return left
        
        def parse_term():
            nonlocal i
            if i >= len(tokens):
                return {"type": "empty"}
            
            if tokens[i] == '(':
                i += 1
                expr = parse_expression()
                if i < len(tokens) and tokens[i] == ')':
                    i += 1
                return expr
            elif tokens[i].lower() == 'not' or tokens[i] == '!':
                i += 1
                return {"type": "not", "operand": parse_term()}
            elif tokens[i].lower().startswith('1 of'):
                # Macro: 1 of selection*
                i += 1
                pattern = tokens[i] if i < len(tokens) else ""
                i += 1
                return {"type": "1_of", "pattern": pattern}
            elif tokens[i].lower().startswith('all of'):
                # Macro: all of selection*
                i += 1
                pattern = tokens[i] if i < len(tokens) else ""
                i += 1
                return {"type": "all_of", "pattern": pattern}
            else:
                # Selection reference
                sel = tokens[i]
                i += 1
                return {"type": "selection", "name": sel}
        
        return parse_expression()
    
    def canonicalize_detection_logic(
        self,
        detection: Dict[str, Any],
        atoms: List[Atom]
    ) -> Dict[str, Any]:
        """
        Canonicalize detection logic into deterministic form.
        
        Args:
            detection: Detection dictionary
            atoms: List of extracted atoms
            
        Returns:
            Canonical logic dictionary
        """
        condition = detection.get('condition', '')
        
        # Parse condition into AST
        ast = self.parse_condition_ast(str(condition))
        
        # Expand macros (1 of selection*, all of selection*)
        ast = self._expand_macros(ast, detection)
        
        # Normalize AST (flatten nested AND/OR, sort deterministically)
        ast = self._normalize_ast(ast)
        
        # Convert to atom-index-based logic
        logic = self._convert_to_atom_logic(ast, atoms, detection)
        
        return logic
    
    def _expand_macros(
        self,
        ast: Dict[str, Any],
        detection: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Expand Sigma macros (1 of selection*, all of selection*) into explicit logic."""
        if ast.get('type') == '1_of':
            # 1 of selection* → OR(selections matching pattern)
            pattern = ast.get('pattern', '')
            selections = self._find_selections_matching_pattern(detection, pattern)
            if len(selections) == 1:
                return {"type": "selection", "name": selections[0]}
            elif len(selections) > 1:
                result = {"type": "or", "operands": []}
                for sel in selections:
                    result["operands"].append({"type": "selection", "name": sel})
                return result
        elif ast.get('type') == 'all_of':
            # all of selection* → AND(selections matching pattern)
            pattern = ast.get('pattern', '')
            selections = self._find_selections_matching_pattern(detection, pattern)
            if len(selections) == 1:
                return {"type": "selection", "name": selections[0]}
            elif len(selections) > 1:
                result = {"type": "and", "operands": []}
                for sel in selections:
                    result["operands"].append({"type": "selection", "name": sel})
                return result
        
        # Recursively expand children
        if 'left' in ast:
            ast['left'] = self._expand_macros(ast['left'], detection)
        if 'right' in ast:
            ast['right'] = self._expand_macros(ast['right'], detection)
        if 'operand' in ast:
            ast['operand'] = self._expand_macros(ast['operand'], detection)
        if 'operands' in ast:
            ast['operands'] = [self._expand_macros(op, detection) for op in ast['operands']]
        
        return ast
    
    def _find_selections_matching_pattern(
        self,
        detection: Dict[str, Any],
        pattern: str
    ) -> List[str]:
        """Find selection keys matching pattern (e.g., 'selection*')."""
        selections = []
        
        # Simple pattern matching (supports * wildcard)
        # Escape regex special characters except *
        pattern_escaped = re.escape(pattern).replace(r'\*', '.*')
        
        try:
            pattern_re = re.compile(f'^{pattern_escaped}$')
        except re.error:
            # If pattern is invalid, fall back to simple string matching
            logger.warning(f"Invalid pattern '{pattern}', using simple matching")
            pattern_prefix = pattern.replace('*', '')
            for key in detection.keys():
                if key != 'condition' and key.startswith(pattern_prefix):
                    selections.append(key)
            return sorted(selections)
        
        for key in detection.keys():
            if key != 'condition' and pattern_re.match(key):
                selections.append(key)
        
        return sorted(selections)  # Deterministic order
    
    def _normalize_ast(self, ast: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize AST: flatten nested AND/OR, sort deterministically."""
        if ast.get('type') in ['and', 'or']:
            # Collect all operands (flatten nested)
            operands = []
            self._collect_operands(ast, ast['type'], operands)
            
            # Sort deterministically
            operands.sort(key=lambda x: json.dumps(x, sort_keys=True))
            
            # Rebuild as binary tree or n-ary
            if len(operands) == 1:
                return operands[0]
            elif len(operands) == 2:
                return {
                    "type": ast['type'],
                    "left": operands[0],
                    "right": operands[1]
                }
            else:
                # Build balanced tree
                return self._build_balanced_tree(operands, ast['type'])
        elif 'operand' in ast:
            ast['operand'] = self._normalize_ast(ast['operand'])
        elif 'left' in ast and 'right' in ast:
            ast['left'] = self._normalize_ast(ast['left'])
            ast['right'] = self._normalize_ast(ast['right'])
        
        return ast
    
    def _collect_operands(
        self,
        node: Dict[str, Any],
        op_type: str,
        operands: List[Dict[str, Any]]
    ):
        """Collect all operands of same type (flatten nested)."""
        if node.get('type') == op_type:
            if 'left' in node:
                self._collect_operands(node['left'], op_type, operands)
            if 'right' in node:
                self._collect_operands(node['right'], op_type, operands)
            if 'operands' in node:
                for op in node['operands']:
                    self._collect_operands(op, op_type, operands)
        else:
            operands.append(node)
    
    def _build_balanced_tree(
        self,
        operands: List[Dict[str, Any]],
        op_type: str
    ) -> Dict[str, Any]:
        """Build balanced binary tree from operands."""
        if len(operands) == 1:
            return operands[0]
        elif len(operands) == 2:
            return {"type": op_type, "left": operands[0], "right": operands[1]}
        else:
            mid = len(operands) // 2
            left = self._build_balanced_tree(operands[:mid], op_type)
            right = self._build_balanced_tree(operands[mid:], op_type)
            return {"type": op_type, "left": left, "right": right}
    
    def _convert_to_atom_logic(
        self,
        ast: Dict[str, Any],
        atoms: List[Atom],
        detection: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert AST to atom-index-based logic."""
        # Map selections to atom indices, preserving field-level grouping
        # Fields in a selection are ANDed; values in a list are ORed (unless |all modifier)
        selection_to_atoms = {}
        atom_idx = 0
        
        for key, value in detection.items():
            if key == 'condition':
                continue
            if not isinstance(value, dict):
                continue
            
            # Group atoms by field (fields are ANDed, values within field are ORed/ANDed based on modifier)
            field_groups = []
            for field_name, field_value in value.items():
                base_field, modifiers = self._parse_field_with_modifiers(field_name)
                has_all = 'all' in [m.lower() for m in modifiers]
                
                if isinstance(field_value, list):
                    field_indices = list(range(atom_idx, atom_idx + len(field_value)))
                    atom_idx += len(field_value)
                    # If |all modifier, values are ANDed; otherwise ORed
                    if has_all:
                        field_groups.append({"AND": [{"ATOM": idx} for idx in field_indices]})
                    else:
                        field_groups.append({"OR": [{"ATOM": idx} for idx in field_indices]})
                else:
                    field_indices = [atom_idx]
                    atom_idx += 1
                    field_groups.append({"ATOM": field_indices[0]})
            
            # All fields in a selection are ANDed together
            if len(field_groups) == 1:
                selection_to_atoms[key] = field_groups[0]
            else:
                selection_to_atoms[key] = {"AND": field_groups}
        
        # Convert AST to use atom indices
        def convert_node(node):
            if node.get('type') == 'selection':
                sel_name = node.get('name', '')
                if sel_name in selection_to_atoms:
                    # selection_to_atoms now contains pre-built logic structure
                    return selection_to_atoms[sel_name]
                else:
                    return {"ATOM": 0}  # Fallback
            elif node.get('type') in ['and', 'or']:
                left = convert_node(node.get('left', {}))
                right = convert_node(node.get('right', {}))
                op = node['type'].upper()
                return {op: [left, right]}
            elif node.get('type') == 'not':
                operand = convert_node(node.get('operand', {}))
                return {"NOT": operand}
            else:
                return {}
        
        return convert_node(ast)
    
    def generate_exact_hash(self, canonical_rule: CanonicalRule) -> str:
        """Generate SHA256 hash of canonical JSON."""
        canonical_json = json.dumps(
            asdict(canonical_rule),
            sort_keys=True,
            separators=(',', ':')
        )
        hash_obj = hashlib.sha256(canonical_json.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def generate_canonical_text(self, canonical_rule: CanonicalRule) -> str:
        """Generate deterministic text representation for hashing/embeddings."""
        parts = []
        
        # Logsource
        logsource = canonical_rule.logsource
        parts.append(f"logsource {logsource.get('product', '')}:{logsource.get('category', '')}")
        
        # Logic
        logic = canonical_rule.detection.get('logic', {})
        logic_str = self._logic_to_string(logic)
        parts.append(logic_str)
        
        # Atoms (sorted)
        atoms = canonical_rule.detection.get('atoms', [])
        for atom in sorted(atoms, key=lambda x: json.dumps(x, sort_keys=True)):
            field = atom.get('field', '')
            ops = '|'.join(atom.get('ops', []))
            value = atom.get('value', '')
            polarity = atom.get('polarity', 'positive')
            
            if ops:
                atom_str = f"{field}|{ops}:{value}"
            else:
                atom_str = f"{field}:{value}"
            
            if polarity == "negative":
                atom_str = f"NOT({atom_str})"
            
            parts.append(atom_str)
        
        return '\n'.join(parts)
    
    def _logic_to_string(self, logic: Dict[str, Any]) -> str:
        """Convert logic dictionary to string representation."""
        if 'ATOM' in logic:
            return f"ATOM[{logic['ATOM']}]"
        elif 'AND' in logic:
            operands = [self._logic_to_string(op) for op in logic['AND']]
            return f"AND({', '.join(operands)})"
        elif 'OR' in logic:
            operands = [self._logic_to_string(op) for op in logic['OR']]
            return f"OR({', '.join(operands)})"
        elif 'NOT' in logic:
            return f"NOT({self._logic_to_string(logic['NOT'])})"
        else:
            return "EMPTY"
    
    def retrieve_candidates(
        self,
        exact_hash: str,
        logsource_key: str,
        top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieve candidate rules for comparison.
        
        Hard gate: same logsource_key
        
        Args:
            exact_hash: Exact hash of proposed rule
            logsource_key: Logsource key (product|category)
            top_k: Maximum number of candidates
            
        Returns:
            List of candidate rule dictionaries
        """
        if not self.db_session:
            logger.warning("No database session provided, returning empty candidates")
            return []
        
        try:
            from src.database.models import SigmaRuleTable
            
            # First, check for exact hash match (duplicate)
            # Check if exact_hash column exists (may not be migrated yet)
            try:
                exact_match = self.db_session.query(SigmaRuleTable).filter(
                    SigmaRuleTable.exact_hash == exact_hash
                ).first()
                
                if exact_match:
                    return [{
                        'rule_id': exact_match.rule_id,
                        'title': exact_match.title,
                        'logsource': exact_match.logsource,
                        'detection': exact_match.detection,
                        'exact_hash_match': True
                    }]
            except Exception:
                # Column may not exist yet
                pass
            
            # Retrieve candidates with same logsource_key (HARD GATE - per spec)
            # If logsource_key is empty or invalid, return empty (no candidates)
            if not logsource_key or logsource_key == '|':
                logger.warning(f"Invalid logsource_key '{logsource_key}', returning no candidates")
                return []
            
            try:
                candidates = self.db_session.query(SigmaRuleTable).filter(
                    SigmaRuleTable.logsource_key == logsource_key
                ).limit(top_k).all()
            except Exception as e:
                # If column doesn't exist or query fails, log error and return empty
                # DO NOT fall back to all rules - this violates the hard gate requirement
                logger.error(f"Failed to query candidates by logsource_key '{logsource_key}': {e}")
                logger.error("Returning empty candidates to enforce logsource gate")
                return []
            
            return [{
                'rule_id': c.rule_id,
                'title': c.title,
                'logsource': c.logsource,
                'detection': c.detection,
                'exact_hash': getattr(c, 'exact_hash', None)
            } for c in candidates]
            
        except Exception as e:
            logger.error(f"Failed to retrieve candidates: {e}")
            return []
    
    def compute_atom_jaccard(
        self,
        rule1: CanonicalRule,
        rule2: CanonicalRule
    ) -> float:
        """
        Compute Jaccard similarity over positive atoms only.
        
        Args:
            rule1: First canonical rule
            rule2: Second canonical rule
            
        Returns:
            Jaccard similarity (0-1)
        """
        atoms1 = rule1.detection.get('atoms', [])
        atoms2 = rule2.detection.get('atoms', [])
        
        # Filter to positive atoms only
        positive_atoms1 = [a for a in atoms1 if a.get('polarity', 'positive') == 'positive']
        positive_atoms2 = [a for a in atoms2 if a.get('polarity', 'positive') == 'positive']
        
        # Create sets for comparison (normalize atom representation)
        set1 = {self._atom_to_key(a) for a in positive_atoms1}
        set2 = {self._atom_to_key(a) for a in positive_atoms2}
        
        if not set1 and not set2:
            return 1.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _atom_to_key(self, atom: Union[Dict[str, Any], Atom]) -> str:
        """Convert atom to normalized key for comparison (v1.2: includes op_type)."""
        if isinstance(atom, Atom):
            field = atom.field
            op = atom.op
            op_type = atom.op_type
            value = atom.value
        else:
            field = atom.get('field', '')
            op = atom.get('op', '')
            op_type = atom.get('op_type', 'literal')
            value = atom.get('value', '')
        
        return f"{field}|{op}|{op_type}|{value}"
    
    def compute_logic_shape_similarity(
        self,
        rule1: CanonicalRule,
        rule2: CanonicalRule
    ) -> float:
        """
        Compute similarity of logic AST shapes (v1.2: enhanced metrics).
        
        Args:
            rule1: First canonical rule
            rule2: Second canonical rule
            
        Returns:
            Similarity score (0-1)
        """
        logic1 = rule1.detection.get('logic', {})
        logic2 = rule2.detection.get('logic', {})
        
        # Convert to normalized string representations
        str1 = json.dumps(logic1, sort_keys=True)
        str2 = json.dumps(logic2, sort_keys=True)
        
        if str1 == str2:
            return 1.0
        
        # Enhanced metrics (v1.2)
        metrics1 = self._compute_logic_metrics(logic1)
        metrics2 = self._compute_logic_metrics(logic2)
        
        # Weighted distance calculation
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
    
    def _compute_logic_metrics(self, logic: Dict[str, Any]) -> Dict[str, int]:
        """Compute enhanced logic metrics (v1.2)."""
        return {
            'node_count': self._count_nodes(logic),
            'and_count': self._count_operator(logic, 'AND'),
            'or_count': self._count_operator(logic, 'OR'),
            'not_count': self._count_operator(logic, 'NOT'),
            'max_depth': self._compute_logic_depth(logic)
        }
    
    def _count_nodes(self, logic: Dict[str, Any]) -> int:
        """Count total nodes in logic tree."""
        if 'ATOM' in logic:
            return 1
        elif 'AND' in logic or 'OR' in logic:
            operands = logic.get('AND', logic.get('OR', []))
            return 1 + sum(self._count_nodes(op) for op in operands)
        elif 'NOT' in logic:
            return 1 + self._count_nodes(logic['NOT'])
        else:
            return 0
    
    def _count_operator(self, logic: Dict[str, Any], op_name: str) -> int:
        """Count occurrences of specific operator."""
        count = 0
        if op_name in logic:
            count = 1
            if op_name == 'NOT':
                count += self._count_operator(logic[op_name], op_name)
            else:
                operands = logic.get(op_name, [])
                for op in operands:
                    count += self._count_operator(op, op_name)
        elif 'AND' in logic or 'OR' in logic:
            operands = logic.get('AND', logic.get('OR', []))
            for op in operands:
                count += self._count_operator(op, op_name)
        elif 'NOT' in logic:
            count += self._count_operator(logic['NOT'], op_name)
        
        return count
    
    def _compute_logic_depth(self, logic: Dict[str, Any]) -> int:
        """Compute maximum depth of logic tree."""
        if 'ATOM' in logic:
            return 1
        elif 'AND' in logic or 'OR' in logic:
            operands = logic.get('AND', logic.get('OR', []))
            if operands:
                return 1 + max(self._compute_logic_depth(op) for op in operands)
            return 1
        elif 'NOT' in logic:
            return 1 + self._compute_logic_depth(logic['NOT'])
        else:
            return 0
    
    def _count_operators(self, logic: Dict[str, Any]) -> int:
        """Count number of operators in logic tree."""
        count = 0
        if 'AND' in logic or 'OR' in logic:
            count = 1
            operands = logic.get('AND', logic.get('OR', []))
            for op in operands:
                count += self._count_operators(op)
        elif 'NOT' in logic:
            count = 1 + self._count_operators(logic['NOT'])
        
        return count
    
    def compute_weighted_similarity(
        self,
        atom_jaccard: float,
        logic_similarity: float,
        service_penalty: float = 0.0,
        filter_penalty: float = 0.0
    ) -> float:
        """
        Compute weighted similarity score with penalties (v1.2).
        
        Args:
            atom_jaccard: Atom Jaccard similarity (0-1)
            logic_similarity: Logic shape similarity (0-1)
            service_penalty: Service mismatch penalty (0-1)
            filter_penalty: Filter divergence penalty (0-1)
            
        Returns:
            Weighted similarity (0-1), clamped to [0.0, 1.0]
        """
        similarity = (
            0.70 * atom_jaccard +
            0.30 * logic_similarity -
            service_penalty -
            filter_penalty
        )
        return max(0.0, min(1.0, similarity))
    
    def classify_novelty(
        self,
        exact_hash: str,
        matches: List[Dict[str, Any]]
    ) -> Tuple[str, float]:
        """
        Classify novelty based on exact hash and similarity metrics.
        
        Args:
            exact_hash: Exact hash of proposed rule
            matches: List of match dictionaries with similarity metrics
            
        Returns:
            Tuple of (novelty_label, novelty_score)
        """
        # Check for exact hash match (duplicate)
        if matches and matches[0].get('exact_hash_match'):
            return (NoveltyLabel.DUPLICATE, 0.0)
        
        if not matches:
            return (NoveltyLabel.NOVEL, 1.0)
        
        top_match = matches[0]
        atom_jaccard = top_match.get('atom_jaccard', 0.0)
        logic_similarity = top_match.get('logic_shape_similarity', 0.0)
        weighted_sim = top_match.get('similarity', 0.0)
        
        # Classification thresholds (per spec)
        # Handle None for logic_similarity (early exit case)
        if logic_similarity is None:
            logic_similarity = 1.0  # Early exit means perfect match
        
        if atom_jaccard > 0.95 and logic_similarity > 0.95:
            return (NoveltyLabel.DUPLICATE, 1.0 - weighted_sim)
        elif atom_jaccard > 0.80:
            return (NoveltyLabel.SIMILAR, 1.0 - weighted_sim)
        else:
            return (NoveltyLabel.NOVEL, 1.0 - weighted_sim)
    
    def generate_explainability(
        self,
        proposed: CanonicalRule,
        candidate: CanonicalRule,
        candidate_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate explainability output showing differences.
        
        Args:
            proposed: Proposed canonical rule
            candidate: Candidate canonical rule
            candidate_metadata: Metadata about candidate rule
            
        Returns:
            Dictionary with explainability fields
        """
        atoms1 = proposed.detection.get('atoms', [])
        atoms2 = candidate.detection.get('atoms', [])
        
        # Separate positive and negative atoms
        positive_atoms1 = [a for a in atoms1 if a.get('polarity', 'positive') == 'positive']
        negative_atoms1 = [a for a in atoms1 if a.get('polarity', 'positive') == 'negative']
        positive_atoms2 = [a for a in atoms2 if a.get('polarity', 'positive') == 'positive']
        negative_atoms2 = [a for a in atoms2 if a.get('polarity', 'positive') == 'negative']
        
        # Find shared, added, removed atoms
        set1 = {self._atom_to_key(a) for a in positive_atoms1}
        set2 = {self._atom_to_key(a) for a in positive_atoms2}
        
        shared_keys = set1 & set2
        added_keys = set2 - set1
        removed_keys = set1 - set2
        
        # Convert keys back to atom strings
        shared_atoms = [self._atom_to_string(a) for a in positive_atoms1 if self._atom_to_key(a) in shared_keys]
        added_atoms = [self._atom_to_string(a) for a in positive_atoms2 if self._atom_to_key(a) in added_keys]
        removed_atoms = [self._atom_to_string(a) for a in positive_atoms1 if self._atom_to_key(a) in removed_keys]
        
        # Filter differences (negative atoms)
        filter_differences = []
        if negative_atoms1 or negative_atoms2:
            neg_set1 = {self._atom_to_key(a) for a in negative_atoms1}
            neg_set2 = {self._atom_to_key(a) for a in negative_atoms2}
            filter_diff_keys = (neg_set1 | neg_set2) - (neg_set1 & neg_set2)
            filter_differences = [
                self._atom_to_string(a) for a in (negative_atoms1 + negative_atoms2)
                if self._atom_to_key(a) in filter_diff_keys
            ]
        
        return {
            'shared_atoms': shared_atoms,
            'added_atoms': added_atoms,
            'removed_atoms': removed_atoms,
            'filter_differences': filter_differences
        }
    
    def _atom_to_string(self, atom: Dict[str, Any]) -> str:
        """Convert atom to human-readable string (v1.2)."""
        field = atom.get('field', '')
        op = atom.get('op', '')
        value = atom.get('value', '')
        
        if op:
            return f"{field}|{op}:{value}"
        else:
            return f"{field}:{value}"
    
    def _compute_service_penalty(self, service1: Optional[str], service2: Optional[str]) -> float:
        """
        Compute service mismatch penalty (v1.2).
        
        Penalty applied only if both services are present and different.
        No penalty if either is missing.
        
        Returns:
            Penalty value (0.0 or SERVICE_PENALTY)
        """
        if service1 and service2:
            if service1 != service2:
                return self.SERVICE_PENALTY
        return 0.0
    
    def _compute_filter_penalty(
        self,
        rule1: CanonicalRule,
        rule2: CanonicalRule
    ) -> float:
        """
        Compute filter divergence penalty (v1.2).
        
        Penalizes rules that differ in NOT logic (negative atoms).
        
        Returns:
            Penalty value (0.0 to max_penalty)
        """
        atoms1 = rule1.detection.get('atoms', [])
        atoms2 = rule2.detection.get('atoms', [])
        
        # Filter to negative atoms only
        negative_atoms1 = [a for a in atoms1 if a.get('polarity', 'positive') == 'negative']
        negative_atoms2 = [a for a in atoms2 if a.get('polarity', 'positive') == 'negative']
        
        if not negative_atoms1 and not negative_atoms2:
            return 0.0
        
        # Compute Jaccard similarity for negative atoms
        set1 = {self._atom_to_key(a) for a in negative_atoms1}
        set2 = {self._atom_to_key(a) for a in negative_atoms2}
        
        if not set1 and not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        filter_jaccard = intersection / union if union > 0 else 0.0
        
        # Apply penalty if below threshold
        jaccard_threshold = 0.5
        max_penalty = 0.10
        
        if filter_jaccard < jaccard_threshold:
            penalty = max_penalty * (1.0 - filter_jaccard)
            return min(penalty, max_penalty)
        
        return 0.0
