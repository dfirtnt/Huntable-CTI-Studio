"""
SIGMA Huntability/Detection Utility Scorer.

Evaluates SIGMA rules for huntability using a rubric-based scoring system.
"""

import logging
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HuntabilityScore:
    """Huntability score result."""
    score: float  # 0-10
    false_positive_risk: str  # "low", "medium", "high"
    coverage_notes: str
    breakdown: Dict[str, float]  # Score breakdown by category


class SigmaHuntabilityScorer:
    """
    Scores SIGMA rules for huntability and detection utility.
    
    Evaluates:
    - Command-line specificity
    - TTP clarity
    - Parent/child correctness
    - Telemetry feasibility
    - False-positive risk
    - Overfitting risk
    """
    
    def __init__(self):
        """Initialize huntability scorer."""
        pass
    
    def score_rule(self, rule_yaml: str, rule_data: Optional[Dict] = None) -> HuntabilityScore:
        """
        Score a SIGMA rule for huntability.
        
        Args:
            rule_yaml: SIGMA rule as YAML string
            rule_data: Parsed rule data (optional, will parse if not provided)
            
        Returns:
            HuntabilityScore with 0-10 score and risk assessment
        """
        if rule_data is None:
            import yaml
            try:
                rule_data = yaml.safe_load(rule_yaml)
            except Exception as e:
                logger.error(f"Failed to parse rule: {e}")
                return HuntabilityScore(
                    score=0.0,
                    false_positive_risk="high",
                    coverage_notes="Failed to parse rule",
                    breakdown={}
                )
        
        if not rule_data or not isinstance(rule_data, dict):
            return HuntabilityScore(
                score=0.0,
                false_positive_risk="high",
                coverage_notes="Invalid rule structure",
                breakdown={}
            )
        
        detection = rule_data.get('detection', {})
        if not isinstance(detection, dict):
            return HuntabilityScore(
                score=0.0,
                false_positive_risk="high",
                coverage_notes="No detection section",
                breakdown={}
            )
        
        # Score each category
        cmdline_score = self._score_commandline_specificity(detection)
        ttp_score = self._score_ttp_clarity(rule_data, detection)
        parent_child_score = self._score_parent_child_correctness(detection)
        telemetry_score = self._score_telemetry_feasibility(rule_data)
        fp_risk = self._assess_false_positive_risk(detection)
        overfitting_score = self._score_overfitting_risk(detection)
        
        # Weighted average
        weights = {
            'commandline_specificity': 0.25,
            'ttp_clarity': 0.20,
            'parent_child': 0.15,
            'telemetry_feasibility': 0.15,
            'overfitting': 0.25
        }
        
        total_score = (
            cmdline_score * weights['commandline_specificity'] +
            ttp_score * weights['ttp_clarity'] +
            parent_child_score * weights['parent_child'] +
            telemetry_score * weights['telemetry_feasibility'] +
            overfitting_score * weights['overfitting']
        )
        
        # Normalize to 0-10
        total_score = min(10.0, max(0.0, total_score * 10))
        
        breakdown = {
            'commandline_specificity': cmdline_score * 10,
            'ttp_clarity': ttp_score * 10,
            'parent_child': parent_child_score * 10,
            'telemetry_feasibility': telemetry_score * 10,
            'overfitting': overfitting_score * 10
        }
        
        coverage_notes = self._generate_coverage_notes(
            cmdline_score, ttp_score, parent_child_score, telemetry_score, fp_risk
        )
        
        return HuntabilityScore(
            score=total_score,
            false_positive_risk=fp_risk,
            coverage_notes=coverage_notes,
            breakdown=breakdown
        )
    
    def _score_commandline_specificity(self, detection: Dict) -> float:
        """Score command-line specificity (0-1)."""
        score = 0.0
        
        # Check for CommandLine field
        has_commandline = False
        commandline_values = []
        
        def find_commandlines(d: Dict):
            for key, value in d.items():
                if 'commandline' in key.lower() or 'command' in key.lower():
                    has_commandline = True
                    if isinstance(value, str):
                        commandline_values.append(value)
                    elif isinstance(value, list):
                        commandline_values.extend([v for v in value if isinstance(v, str)])
                elif isinstance(value, dict):
                    find_commandlines(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            find_commandlines(item)
        
        find_commandlines(detection)
        
        if not has_commandline:
            return 0.3  # Low score if no commandline
        
        # Check specificity of commandlines
        specific_count = 0
        for cmd in commandline_values:
            # Check if it's specific (not just wildcards)
            if '*' not in cmd or len(cmd.replace('*', '').strip()) > 10:
                specific_count += 1
        
        if commandline_values:
            score = specific_count / len(commandline_values)
        else:
            score = 0.5
        
        return score
    
    def _score_ttp_clarity(self, rule_data: Dict, detection: Dict) -> float:
        """Score TTP clarity (0-1)."""
        score = 0.5  # Base score
        
        # Check for tags (MITRE ATT&CK)
        tags = rule_data.get('tags', [])
        attack_tags = [t for t in tags if 'attack.' in str(t).lower()]
        if attack_tags:
            score += 0.3
        
        # Check description quality
        description = rule_data.get('description', '')
        if len(description) > 50:
            score += 0.1
        if 'ttp' in description.lower() or 'technique' in description.lower():
            score += 0.1
        
        return min(1.0, score)
    
    def _score_parent_child_correctness(self, detection: Dict) -> float:
        """Score parent/child process correctness (0-1)."""
        score = 0.5  # Base score
        
        has_image = False
        has_parent = False
        
        def find_process_fields(d: Dict):
            nonlocal has_image, has_parent
            for key, value in d.items():
                key_lower = key.lower()
                if 'image' in key_lower and 'parent' not in key_lower:
                    has_image = True
                elif 'parentimage' in key_lower or 'parent_image' in key_lower:
                    has_parent = True
                elif isinstance(value, dict):
                    find_process_fields(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            find_process_fields(item)
        
        find_process_fields(detection)
        
        if has_image:
            score += 0.3
        if has_parent:
            score += 0.2
        
        return min(1.0, score)
    
    def _score_telemetry_feasibility(self, rule_data: Dict) -> float:
        """Score telemetry feasibility (0-1)."""
        logsource = rule_data.get('logsource', {})
        if not isinstance(logsource, dict):
            return 0.3
        
        category = logsource.get('category')
        product = logsource.get('product')
        
        # Valid combinations get higher scores
        valid_combos = {
            ('process_creation', 'windows'),
            ('process_creation', 'linux'),
            ('network_connection', 'windows'),
            ('registry_access', 'windows')
        }
        
        if (category, product) in valid_combos:
            return 1.0
        elif category and product:
            return 0.7
        elif category or product:
            return 0.5
        else:
            return 0.3
    
    def _assess_false_positive_risk(self, detection: Dict) -> str:
        """Assess false-positive risk level."""
        risk_factors = 0
        
        # Check for overly broad patterns
        def check_broad_patterns(d: Dict):
            nonlocal risk_factors
            for key, value in d.items():
                if isinstance(value, str):
                    # Check for unanchored wildcards
                    if value.strip() == '*' or value.strip() == '.*':
                        risk_factors += 2
                    # Check for very short patterns
                    if len(value.replace('*', '').strip()) < 3:
                        risk_factors += 1
                elif isinstance(value, dict):
                    check_broad_patterns(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            if item.strip() == '*' or item.strip() == '.*':
                                risk_factors += 2
                        elif isinstance(item, dict):
                            check_broad_patterns(item)
        
        check_broad_patterns(detection)
        
        if risk_factors >= 3:
            return "high"
        elif risk_factors >= 1:
            return "medium"
        else:
            return "low"
    
    def _score_overfitting_risk(self, detection: Dict) -> float:
        """Score overfitting risk (higher score = less overfitting, 0-1)."""
        ioc_indicators = 0
        
        # Check for IOC-like patterns
        ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
        domain_pattern = re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b')
        
        def check_iocs(d: Dict):
            nonlocal ioc_indicators
            for key, value in d.items():
                if isinstance(value, str):
                    if ip_pattern.search(value):
                        ioc_indicators += 2
                    if domain_pattern.search(value):
                        ioc_indicators += 1
                elif isinstance(value, dict):
                    check_iocs(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            if ip_pattern.search(item):
                                ioc_indicators += 2
                            if domain_pattern.search(item):
                                ioc_indicators += 1
                        elif isinstance(item, dict):
                            check_iocs(item)
        
        check_iocs(detection)
        
        # More IOCs = more overfitting = lower score
        if ioc_indicators == 0:
            return 1.0
        elif ioc_indicators <= 1:
            return 0.8
        elif ioc_indicators <= 2:
            return 0.6
        else:
            return 0.3
    
    def _generate_coverage_notes(
        self,
        cmdline_score: float,
        ttp_score: float,
        parent_child_score: float,
        telemetry_score: float,
        fp_risk: str
    ) -> str:
        """Generate coverage notes based on scores."""
        notes = []
        
        if cmdline_score < 0.5:
            notes.append("Low command-line specificity")
        if ttp_score < 0.5:
            notes.append("Limited TTP clarity")
        if parent_child_score < 0.5:
            notes.append("Weak parent/child process tracking")
        if telemetry_score < 0.7:
            notes.append("Telemetry feasibility concerns")
        if fp_risk == "high":
            notes.append("High false-positive risk")
        
        if not notes:
            return "Good coverage across all categories"
        
        return "; ".join(notes)

