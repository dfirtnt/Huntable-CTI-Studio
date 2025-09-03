#!/usr/bin/env python3
"""
Test script for the TTP Quality Framework.

This script demonstrates how the enhanced system evaluates threat intelligence
content quality based on the user's analysis framework.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from utils.ttp_extractor import ThreatHuntingDetector

def test_quality_framework():
    """Test the TTP quality framework with sample content."""
    
    # Sample high-quality threat intelligence content (based on user's analysis)
    high_quality_content = """
    Sigma Rule: Interlock RAT PHP Variant Detection
    
    title: Interlock RAT PHP Variant - Process Chain Detection
    id: 12345
    status: experimental
    description: Detects Interlock RAT PHP variant using PowerShell to spawn PHP from suspicious locations
    
    detection:
        selection_ps:
            ParentImage|endswith: '\\powershell.exe'
            CommandLine|contains: '-c'
        selection_php:
            Image|contains: '\\AppData\\Roaming\\php\\php.exe'
            CommandLine|contains: '.cfg'
        condition: selection_ps and selection_php
    
    fields:
        - ParentImage
        - Image
        - CommandLine
        - Computer
    
    falsepositives:
        - Admin/PHP developers launching PHP via PowerShell for legitimate config tasks
    
    tags:
        - attack.execution
        - attack.t1059.001
        - attack.persistence
        - attack.t1547.001
        - attack.command_and_control
        - attack.t1090.004
    
    references:
        - https://thedfirreport.com/2025/08/05/interlock-rat-php-variant/
    
    author: The DFIR Report
    
    Additional Context:
    The Interlock RAT PHP variant uses sophisticated process chaining techniques:
    - PowerShell spawns PHP from \\AppData\\Roaming\\php\\php.exe
    - PHP loads configuration from .cfg files
    - Registry persistence via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    - Network communication through trycloudflare.com domains
    
    Hunting Indicators:
    - Monitor for PowerShell spawning PHP processes
    - Check for unusual file creation in AppData directories
    - Look for registry modifications to Run keys
    - Monitor network connections to suspicious domains
    
    MITRE ATT&CK Techniques:
    - T1059.001: Command and Scripting Interpreter: PowerShell
    - T1547.001: Boot or Logon Autostart Execution: Registry Run Keys
    - T1090.004: Proxy: Domain Fronting
    """
    
    # Sample medium-quality content
    medium_quality_content = """
    Threat Intelligence: Recent RDP Exploitation Campaign
    
    Summary: Attackers are using password spraying against RDP servers to gain initial access.
    After successful authentication, they create scheduled tasks for persistence and use
    process injection techniques to evade detection.
    
    Key Indicators:
    - RDP brute force attempts from multiple IP addresses
    - Scheduled task creation with unusual names
    - Process injection using PowerShell
    
    MITRE ATT&CK: T1021 (Remote Services), T1053 (Scheduled Task/Job), T1055 (Process Injection)
    
    Hunting Guidance: Monitor RDP logs for multiple failed attempts, check for unusual scheduled tasks,
    and look for PowerShell processes with unusual parent processes.
    """
    
    # Sample low-quality content
    low_quality_content = """
    Security Alert: Malware Detected
    
    A new malware variant has been identified in the wild. The malware uses various
    techniques to evade detection and maintain persistence on compromised systems.
    
    Organizations should ensure their security controls are up to date and monitor
    for suspicious activity.
    """
    
    print("🔍 Testing TTP Quality Framework")
    print("=" * 80)
    print()
    
    # Initialize detector
    detector = ThreatHuntingDetector()
    
    # Test high-quality content
    print("📊 HIGH-QUALITY CONTENT TEST:")
    print("=" * 50)
    quality_data = detector.calculate_ttp_quality_score(high_quality_content)
    print(f"Quality Level: {quality_data['quality_level']}")
    print(f"Total Score: {quality_data['total_score']}/{quality_data['max_possible']}")
    print()
    
    print("🔍 Detailed Quality Report:")
    print("-" * 40)
    quality_report = detector.generate_quality_report(high_quality_content)
    print(quality_report)
    print()
    
    # Test medium-quality content
    print("📊 MEDIUM-QUALITY CONTENT TEST:")
    print("=" * 50)
    quality_data = detector.calculate_ttp_quality_score(medium_quality_content)
    print(f"Quality Level: {quality_data['quality_level']}")
    print(f"Total Score: {quality_data['total_score']}/{quality_data['max_possible']}")
    print()
    
    # Test low-quality content
    print("📊 LOW-QUALITY CONTENT TEST:")
    print("=" * 50)
    quality_data = detector.calculate_ttp_quality_score(low_quality_content)
    print(f"Quality Level: {quality_data['quality_level']}")
    print(f"Total Score: {quality_data['total_score']}/{quality_data['max_possible']}")
    print()
    
    # Test threat hunting detection on high-quality content
    print("🎯 THREAT HUNTING DETECTION ON HIGH-QUALITY CONTENT:")
    print("=" * 60)
    analysis = detector.detect_hunting_techniques(high_quality_content, 999)
    
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
    
    print("✅ Quality framework test completed!")

if __name__ == "__main__":
    test_quality_framework()
