"""LLM-Powered Content Quality Assessment for CTI Scraper.

This module provides LLM-based quality assessment to complement the existing
TTP detection engine, filling the gap between documented framework and actual implementation.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


@dataclass
class LLMQualityAssessment:
    """Results from LLM-based quality assessment."""
    
    # Content Structure (0-25 points)
    content_structure_score: int
    structure_breakdown: Dict[str, int]
    structure_reasoning: str
    
    # Technical Depth (0-25 points)  
    technical_depth_score: int
    technical_breakdown: Dict[str, int]
    technical_reasoning: str
    
    # Overall Intelligence Value (0-25 points)
    intelligence_value_score: int
    value_breakdown: Dict[str, int]
    value_reasoning: str
    
    # Tactical vs Strategic Classification
    tactical_score: int  # 0-100
    strategic_score: int  # 0-100
    classification: str  # "Tactical", "Strategic", "Hybrid"
    
    # Combined Quality Score (0-75 points)
    total_quality_score: int
    quality_level: str  # "Excellent", "Good", "Fair", "Limited"
    
    # LLM Recommendations
    recommendations: List[str]
    hunting_priority: str  # "High", "Medium", "Low"


class LLMQualityAssessor:
    """
    LLM-powered quality assessment for threat intelligence content.
    
    Works alongside the existing TTP detector to provide comprehensive
    quality evaluation that fills the gap in the documented framework.
    """
    
    def __init__(self):
        """Initialize the LLM quality assessor."""
        self.quality_thresholds = {
            "excellent": 60,
            "good": 45,
            "fair": 30,
            "limited": 0
        }
    
    def assess_content_quality(self, content: str, ttp_analysis: Optional[Dict] = None) -> LLMQualityAssessment:
        """
        Assess content quality using LLM-powered analysis.
        
        Args:
            content: Article content to assess
            ttp_analysis: Optional TTP analysis from existing detector
            
        Returns:
            LLMQualityAssessment with comprehensive quality scores
        """
        try:
            # For now, implement rule-based assessment that mimics LLM analysis
            # This can be replaced with actual LLM calls later
            
            # Content Structure Assessment (0-25 points)
            structure_score, structure_breakdown, structure_reasoning = self._assess_content_structure(content)
            
            # Technical Depth Assessment (0-25 points)
            technical_score, technical_breakdown, technical_reasoning = self._assess_technical_depth(content)
            
            # Intelligence Value Assessment (0-25 points)
            value_score, value_breakdown, value_reasoning = self._assess_intelligence_value(content, ttp_analysis)
            
            # Tactical vs Strategic Classification
            tactical_score, strategic_score, classification = self._assess_tactical_vs_strategic(content)
            
            # Calculate total score
            total_score = structure_score + technical_score + value_score
            
            # Determine quality level
            quality_level = self._determine_quality_level(total_score)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                structure_score, technical_score, value_score, 
                tactical_score, strategic_score, ttp_analysis
            )
            
            # Determine hunting priority
            hunting_priority = self._determine_hunting_priority(
                total_score, tactical_score, ttp_analysis
            )
            
            return LLMQualityAssessment(
                content_structure_score=structure_score,
                structure_breakdown=structure_breakdown,
                structure_reasoning=structure_reasoning,
                technical_depth_score=technical_score,
                technical_breakdown=technical_breakdown,
                technical_reasoning=technical_reasoning,
                intelligence_value_score=value_score,
                value_breakdown=value_breakdown,
                value_reasoning=value_reasoning,
                tactical_score=tactical_score,
                strategic_score=strategic_score,
                classification=classification,
                total_quality_score=total_score,
                quality_level=quality_level,
                recommendations=recommendations,
                hunting_priority=hunting_priority
            )
            
        except Exception as e:
            logger.error(f"LLM quality assessment failed: {e}")
            # Return default assessment on error
            return self._create_default_assessment()
    
    def _assess_content_structure(self, content: str) -> tuple[int, Dict[str, int], str]:
        """Assess content structure and organization (0-25 points)."""
        score = 0
        breakdown = {}
        reasoning = []
        
        # Length assessment (0-10 points)
        if len(content) > 2000:
            length_score = 10
            reasoning.append("Comprehensive content length (>2000 chars)")
        elif len(content) > 1000:
            length_score = 7
            reasoning.append("Good content length (1000-2000 chars)")
        elif len(content) > 500:
            length_score = 4
            reasoning.append("Basic content length (500-1000 chars)")
        else:
            length_score = 0
            reasoning.append("Insufficient content length (<500 chars)")
        
        score += length_score
        breakdown["length"] = length_score
        
        # Formatting assessment (0-15 points)
        formatting_score = 0
        
        # Check for headers and sections
        if re.search(r'#{1,6}\s+\w+', content) or re.search(r'<h[1-6]>', content):
            formatting_score += 5
            reasoning.append("Clear headers and sections present")
        
        # Check for lists and bullet points
        if re.search(r'[-*•]\s+\w+', content) or re.search(r'<li>', content):
            formatting_score += 4
            reasoning.append("Lists and bullet points present")
        
        # Check for code blocks
        if re.search(r'```|`\w+`|<code>', content):
            formatting_score += 3
            reasoning.append("Code blocks or inline code present")
        
        # Check for tables
        if re.search(r'<table>|<tr>|<td>', content):
            formatting_score += 3
            reasoning.append("Tables or structured data present")
        
        score += formatting_score
        breakdown["formatting"] = formatting_score
        
        reasoning_text = "; ".join(reasoning)
        return score, breakdown, reasoning_text
    
    def _assess_technical_depth(self, content: str) -> tuple[int, Dict[str, int], str]:
        """Assess technical depth and specificity (0-25 points)."""
        score = 0
        breakdown = {}
        reasoning = []
        
        # Technical terminology (0-10 points)
        technical_terms = [
            'process injection', 'dll injection', 'registry modification',
            'lsass', 'mimikatz', 'pass the hash', 'living off the land',
            'process hollowing', 'code injection', 'memory injection',
            'wmi', 'powershell', 'cmd', 'rundll32', 'wscript',
            'scheduled task', 'service installation', 'startup key'
        ]
        
        term_count = sum(1 for term in technical_terms if term.lower() in content.lower())
        if term_count >= 5:
            term_score = 10
            reasoning.append("High technical terminology density")
        elif term_count >= 3:
            term_score = 7
            reasoning.append("Good technical terminology coverage")
        elif term_count >= 1:
            term_score = 4
            reasoning.append("Basic technical terminology present")
        else:
            term_score = 0
            reasoning.append("Limited technical terminology")
        
        score += term_score
        breakdown["technical_terminology"] = term_score
        
        # Practical details (0-15 points)
        practical_score = 0
        
        # Check for step-by-step procedures
        if re.search(r'\d+\.\s+\w+|step\s+\d+|first|then|next|finally', content, re.IGNORECASE):
            practical_score += 8
            reasoning.append("Step-by-step procedures present")
        
        # Check for configuration examples
        if re.search(r'config|setting|parameter|option|value\s*=|path\s*=', content, re.IGNORECASE):
            practical_score += 4
            reasoning.append("Configuration examples present")
        
        # Check for tool usage
        if re.search(r'tool|software|application|utility|command|script', content, re.IGNORECASE):
            practical_score += 3
            reasoning.append("Tool usage information present")
        
        score += practical_score
        breakdown["practical_details"] = practical_score
        
        reasoning_text = "; ".join(reasoning)
        return score, breakdown, reasoning_text
    
    def _assess_intelligence_value(self, content: str, ttp_analysis: Optional[Dict] = None) -> tuple[int, Dict[str, int], str]:
        """Assess threat intelligence value (0-25 points)."""
        score = 0
        breakdown = {}
        reasoning = []
        
        # TTP coverage (0-15 points)
        if ttp_analysis and 'total_techniques' in ttp_analysis:
            technique_count = ttp_analysis.get('total_techniques', 0)
            if technique_count >= 3:
                ttp_score = 15
                reasoning.append("Multiple TTPs detected (3+)")
            elif technique_count >= 1:
                ttp_score = 10
                reasoning.append("TTPs detected (1-2)")
            else:
                ttp_score = 5
                reasoning.append("General attack patterns mentioned")
        else:
            # Estimate TTP coverage from content
            ttp_patterns = [
                'technique', 'tactic', 'procedure', 'attack vector',
                'exploit', 'vulnerability', 'compromise', 'breach'
            ]
            pattern_count = sum(1 for pattern in ttp_patterns if pattern.lower() in content.lower())
            if pattern_count >= 3:
                ttp_score = 10
                reasoning.append("Multiple attack patterns mentioned")
            elif pattern_count >= 1:
                ttp_score = 5
                reasoning.append("Attack patterns mentioned")
            else:
                ttp_score = 0
                reasoning.append("Limited attack pattern coverage")
        
        score += ttp_score
        breakdown["ttp_coverage"] = ttp_score
        
        # Actionable insights (0-10 points)
        actionable_score = 0
        
        # Check for defensive recommendations
        if re.search(r'recommend|mitigation|defense|protection|prevention|detection', content, re.IGNORECASE):
            actionable_score += 5
            reasoning.append("Defensive recommendations present")
        
        # Check for detection methods
        if re.search(r'detect|monitor|alert|log|event|indicator', content, re.IGNORECASE):
            actionable_score += 3
            reasoning.append("Detection methods mentioned")
        
        # Check for response procedures
        if re.search(r'response|incident|contain|eradicate|recover', content, re.IGNORECASE):
            actionable_score += 2
            reasoning.append("Response procedures mentioned")
        
        score += actionable_score
        breakdown["actionable_insights"] = actionable_score
        
        reasoning_text = "; ".join(reasoning)
        return score, breakdown, reasoning_text
    
    def _assess_tactical_vs_strategic(self, content: str) -> tuple[int, int, str]:
        """Assess tactical vs strategic intelligence value."""
        tactical_score = 0
        strategic_score = 0
        
        # Tactical indicators (specific, actionable)
        tactical_indicators = [
            'command line', 'registry key', 'file path', 'process name',
            'ip address', 'domain', 'hash', 'timestamp', 'user agent',
            'specific tool', 'exact command', 'precise location'
        ]
        
        # Strategic indicators (general, awareness)
        strategic_indicators = [
            'trend', 'overview', 'summary', 'background', 'context',
            'general threat', 'industry risk', 'overall picture',
            'broad pattern', 'general awareness', 'high-level'
        ]
        
        # Count tactical indicators
        tactical_count = sum(1 for indicator in tactical_indicators if indicator.lower() in content.lower())
        tactical_score = min(tactical_count * 10, 100)
        
        # Count strategic indicators
        strategic_count = sum(1 for indicator in strategic_indicators if indicator.lower() in content.lower())
        strategic_score = min(strategic_count * 10, 100)
        
        # Determine classification
        if tactical_score >= 70 and strategic_score < 30:
            classification = "Tactical"
        elif strategic_score >= 70 and tactical_score < 30:
            classification = "Strategic"
        else:
            classification = "Hybrid"
        
        return tactical_score, strategic_score, classification
    
    def _determine_quality_level(self, total_score: int) -> str:
        """Determine overall quality level based on total score."""
        if total_score >= self.quality_thresholds["excellent"]:
            return "Excellent"
        elif total_score >= self.quality_thresholds["good"]:
            return "Good"
        elif total_score >= self.quality_thresholds["fair"]:
            return "Fair"
        else:
            return "Limited"
    
    def _generate_recommendations(self, structure_score: int, technical_score: int, 
                                value_score: int, tactical_score: int, 
                                strategic_score: int, ttp_analysis: Optional[Dict]) -> List[str]:
        """Generate actionable recommendations based on assessment."""
        recommendations = []
        
        # Structure recommendations
        if structure_score < 15:
            recommendations.append("Improve content structure with better formatting and organization")
        
        # Technical recommendations
        if technical_score < 15:
            recommendations.append("Add more technical details and specific examples")
        
        # Value recommendations
        if value_score < 15:
            recommendations.append("Include more actionable threat intelligence and TTPs")
        
        # Tactical vs Strategic recommendations
        if tactical_score < 50:
            recommendations.append("Add more specific, actionable details for threat hunting")
        if strategic_score < 50:
            recommendations.append("Provide broader context and strategic overview")
        
        # TTP-specific recommendations
        if ttp_analysis and ttp_analysis.get('total_techniques', 0) < 2:
            recommendations.append("Include more specific MITRE ATT&CK techniques")
        
        if not recommendations:
            recommendations.append("Content meets high quality standards for threat intelligence")
        
        return recommendations
    
    def _determine_hunting_priority(self, total_score: int, tactical_score: int, 
                                  ttp_analysis: Optional[Dict]) -> str:
        """Determine hunting priority based on quality and tactical value."""
        if total_score >= 60 and tactical_score >= 70:
            return "High"
        elif total_score >= 45 and tactical_score >= 50:
            return "Medium"
        else:
            return "Low"
    
    def _create_default_assessment(self) -> LLMQualityAssessment:
        """Create a default assessment when analysis fails."""
        return LLMQualityAssessment(
            content_structure_score=0,
            structure_breakdown={},
            structure_reasoning="Assessment failed",
            technical_depth_score=0,
            technical_breakdown={},
            technical_reasoning="Assessment failed",
            intelligence_value_score=0,
            value_breakdown={},
            value_reasoning="Assessment failed",
            tactical_score=0,
            strategic_score=0,
            classification="Unknown",
            total_quality_score=0,
            quality_level="Limited",
            recommendations=["Quality assessment failed - review content manually"],
            hunting_priority="Low"
        )
    
    def generate_quality_report(self, assessment: LLMQualityAssessment) -> str:
        """Generate a detailed quality assessment report."""
        report = []
        report.append("🔍 LLM Quality Assessment Report")
        report.append("=" * 60)
        report.append(f"Overall Quality: {assessment.quality_level}")
        report.append(f"Total Score: {assessment.total_quality_score}/75")
        report.append(f"Tactical Score: {assessment.tactical_score}/100")
        report.append(f"Strategic Score: {assessment.strategic_score}/100")
        report.append(f"Classification: {assessment.classification}")
        report.append("")
        
        report.append("📊 Quality Factor Breakdown:")
        report.append("-" * 40)
        report.append(f"Content Structure: {assessment.content_structure_score}/25")
        report.append(f"Technical Depth: {assessment.technical_depth_score}/25")
        report.append(f"Intelligence Value: {assessment.intelligence_value_score}/25")
        report.append("")
        
        report.append("💡 Recommendations:")
        report.append("-" * 20)
        for rec in assessment.recommendations:
            report.append(f"• {rec}")
        
        report.append("")
        report.append("🎯 Hunting Priority:")
        report.append("-" * 20)
        report.append(f"Priority: {assessment.hunting_priority}")
        report.append(f"Reasoning: Based on quality score ({assessment.total_quality_score}/75) and tactical value ({assessment.tactical_score}/100)")
        
        report.append("")
        report.append("✅ Assessment Complete!")
        
        return "\n".join(report)


# Convenience function for easy integration
def assess_content_quality(content: str, ttp_analysis: Optional[Dict] = None) -> LLMQualityAssessment:
    """
    Convenience function to assess content quality.
    
    Args:
        content: Article content to assess
        ttp_analysis: Optional TTP analysis from existing detector
        
    Returns:
        LLMQualityAssessment with comprehensive quality scores
    """
    assessor = LLMQualityAssessor()
    return assessor.assess_content_quality(content, ttp_analysis)
