#!/usr/bin/env python3
"""
Test script for TTP extraction capabilities.
Demonstrates how to analyze threat intelligence content for TTPs.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from utils.ttp_extractor import TTPExtractor


def test_ttp_extraction():
    """Test TTP extraction with sample threat intelligence content."""
    
    # Sample threat intelligence content (real-world examples)
    sample_content = """
    APT29 (Cozy Bear) has been observed using sophisticated techniques including:
    
    - PowerShell execution for command and control (T1059)
    - Process injection to evade detection (T1055)
    - Living off the Land (LotL) techniques
    - Supply chain attacks against software vendors
    - Spear phishing campaigns targeting government officials
    
    The group uses multiple persistence mechanisms including:
    - Registry modifications for startup persistence
    - Scheduled tasks for automated execution
    - Remote services for lateral movement (T1021)
    
    Their command and control infrastructure leverages:
    - HTTP/HTTPS traffic for communication (T1071)
    - DNS tunneling for data exfiltration
    - Multiple C2 servers for redundancy
    
    Recent campaigns have shown increased use of:
    - Fileless attacks and memory-based techniques
    - Social engineering and pretexting
    - Watering hole attacks against think tanks
    """
    
    print("🔍 Testing TTP Extraction Capabilities")
    print("=" * 50)
    
    # Initialize TTP extractor
    ttp_extractor = TTPExtractor()
    
    # Analyze the sample content
    print("📝 Analyzing sample threat intelligence content...")
    analysis = ttp_extractor.extract_ttps(sample_content, article_id=999)
    
    # Display results
    print("\n📊 TTP Analysis Results:")
    print(f"Total TTP Matches: {analysis.total_matches}")
    print(f"Confidence Score: {analysis.confidence_score:.2f}")
    
    if analysis.tactics_found:
        print(f"\n🎯 Tactics Identified:")
        for tactic in sorted(analysis.tactics_found):
            print(f"  • {tactic}")
    
    if analysis.techniques_found:
        print(f"\n🔧 Techniques Identified:")
        for tech_id in sorted(analysis.techniques_found):
            tech_data = ttp_extractor.mitre_data.get("techniques", {}).get(tech_id, {})
            tech_name = tech_data.get("name", "Unknown")
            print(f"  • {tech_id}: {tech_name}")
    
    if analysis.threat_actor_mentions:
        print(f"\n👥 Threat Actors Mentioned:")
        for actor in analysis.threat_actor_mentions:
            print(f"  • {actor}")
    
    if analysis.malware_families:
        print(f"\n🦠 Malware Families Mentioned:")
        for malware in analysis.malware_families:
            print(f"  • {malware}")
    
    if analysis.attack_vectors:
        print(f"\n⚔️ Attack Vectors Identified:")
        for vector in analysis.attack_vectors:
            print(f"  • {vector}")
    
    if analysis.ttp_matches:
        print(f"\n📋 Detailed TTP Matches:")
        for i, match in enumerate(analysis.ttp_matches, 1):
            print(f"  {i}. {match.technique_id}: {match.technique_name}")
            print(f"     Tactic: {match.tactic}")
            print(f"     Confidence: {match.confidence:.2f}")
            print(f"     Matched: '{match.matched_text}'")
            print(f"     Context: {match.context[:100]}...")
            print()
    
    # Generate and display full report
    print("\n📄 Full TTP Report:")
    print("=" * 50)
    report = ttp_extractor.generate_ttp_report(analysis)
    print(report)


def test_mitre_data_loading():
    """Test MITRE ATT&CK data loading capabilities."""
    
    print("\n🔧 Testing MITRE Data Loading")
    print("=" * 30)
    
    ttp_extractor = TTPExtractor()
    
    print(f"MITRE Techniques Loaded: {len(ttp_extractor.technique_patterns)}")
    print(f"MITRE Tactics Loaded: {len(ttp_extractor.tactic_patterns)}")
    print(f"Procedure Patterns: {len(ttp_extractor.procedure_patterns)}")
    
    # Show some loaded techniques
    print("\n📚 Sample Loaded Techniques:")
    for i, (tech_id, patterns) in enumerate(list(ttp_extractor.technique_patterns.items())[:5]):
        tech_data = ttp_extractor.mitre_data.get("techniques", {}).get(tech_id, {})
        tech_name = tech_data.get("name", "Unknown")
        print(f"  • {tech_id}: {tech_name}")
        print(f"    Patterns: {len(patterns)}")
    
    print("\n📚 Sample Loaded Tactics:")
    for i, tactic in enumerate(list(ttp_extractor.tactic_patterns.keys())[:5]):
        patterns = ttp_extractor.tactic_patterns[tactic]
        print(f"  • {tactic}: {len(patterns)} patterns")


if __name__ == "__main__":
    try:
        test_ttp_extraction()
        test_mitre_data_loading()
        
        print("\n✅ TTP Extraction Test Complete!")
        print("\n💡 Next Steps:")
        print("  1. Use './threat-intel analyze' to analyze collected articles")
        print("  2. Export results with '--format json' or '--format csv'")
        print("  3. Adjust confidence threshold with '--confidence 0.7'")
        print("  4. Analyze specific sources with '--source source_name'")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
