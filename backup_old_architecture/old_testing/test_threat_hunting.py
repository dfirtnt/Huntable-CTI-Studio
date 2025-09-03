#!/usr/bin/env python3
"""
Test script for the new Threat Hunting Detector.

This script demonstrates how the refactored system detects huntable techniques
rather than MITRE ATT&CK taxonomy.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from utils.ttp_extractor import ThreatHuntingDetector

def test_threat_hunting():
    """Test the threat hunting detector with sample content."""
    
    # Sample threat intelligence content
    sample_content = """
    Recent APT29 campaign uses sophisticated RDP exploitation techniques for lateral movement.
    The attackers employ password spraying attacks against multiple accounts and then use
    Pass the Hash techniques to move between systems. They also create scheduled tasks for
    persistence and use process injection to evade detection.
    
    The malware family "DripDropper" has been observed using living off the land techniques,
    including PowerShell execution and WMI queries. The threat actors have been identified
    as a state-sponsored group targeting critical infrastructure.
    
    Key hunting indicators include unusual RDP connections from internal IPs, multiple failed
    login attempts across accounts, and suspicious scheduled task creation. Security teams
    should monitor for LSASS memory dumps and unusual registry modifications.
    """
    
    print("🔍 Testing Threat Hunting Detector")
    print("=" * 60)
    print()
    
    # Initialize detector
    detector = ThreatHuntingDetector()
    
    # Analyze content
    analysis = detector.detect_hunting_techniques(sample_content, 999)
    
    # Display results
    print("📊 Analysis Results:")
    print(f"Article ID: {analysis.article_id}")
    print(f"Total Techniques: {analysis.total_techniques}")
    print(f"Overall Confidence: {analysis.overall_confidence:.2f}")
    print(f"Hunting Priority: {analysis.hunting_priority}")
    print()
    
    if analysis.techniques_by_category:
        print("🎯 Huntable Techniques by Category:")
        print("=" * 50)
        for category, techniques in analysis.techniques_by_category.items():
            print(f"\n📋 {category.upper()}:")
            for i, tech in enumerate(techniques, 1):
                print(f"  {i}. {tech.technique_name}")
                print(f"     Confidence: {tech.confidence:.2f}")
                print(f"     Matched: \"{tech.matched_text}\"")
                print(f"     🎯 Hunting: {tech.hunting_guidance}")
                print()
    
    if analysis.threat_actors:
        print("👥 Threat Actors Detected:")
        print("=" * 30)
        for actor in analysis.threat_actors:
            print(f"  • {actor}")
        print()
    
    if analysis.malware_families:
        print("🦠 Malware Families Detected:")
        print("=" * 30)
        for malware in analysis.malware_families:
            print(f"  • {malware}")
        print()
    
    if analysis.attack_vectors:
        print("⚔️ Attack Vectors Detected:")
        print("=" * 30)
        for vector in analysis.attack_vectors:
            print(f"  • {vector}")
        print()
    
    # Generate detailed report
    print("📋 Detailed Hunting Report:")
    print("=" * 60)
    report = detector.generate_hunting_report(analysis)
    print(report)
    
    print("\n✅ Threat hunting test completed!")

if __name__ == "__main__":
    test_threat_hunting()
