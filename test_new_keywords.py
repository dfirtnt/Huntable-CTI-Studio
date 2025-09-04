#!/usr/bin/env python3
"""
Test script to verify the new keywords are working properly.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.content import ThreatHuntingScorer

def test_new_keywords():
    """Test the new keywords detection."""
    
    # Sample content with new keywords
    title = "LOLBAS and RMM Detection Techniques"
    content = """
    This article discusses advanced threat hunting techniques using LOLBAS 
    (Living Off the Land Binaries and Scripts) and RMM (Remote Management/Monitoring) tools.
    
    Key concepts covered:
    - LOLBAS: Living Off the Land Binaries and Scripts
    - LOLBINS: Living Off the Land Binaries
    - RMM: Remote Management and Monitoring tools
    
    Registry analysis:
    - HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run
    - CurrentVersion registry keys for persistence
    
    Event log analysis:
    - EventCode 4624: Successful logon
    - EventCode 4688: Process creation
    - EventCode 4103: PowerShell execution
    
    Detection rules:
    - Monitor for LOLBAS usage patterns
    - Track RMM tool installations
    - Alert on CurrentVersion modifications
    """
    
    print("Testing New Keywords Detection")
    print("=" * 40)
    
    result = ThreatHuntingScorer.score_threat_hunting_content(title, content)
    
    print(f"Threat Hunting Score: {result['threat_hunting_score']}/100")
    print(f"Technical Depth Score: {result['technical_depth_score']}/30")
    print(f"Keyword Density: {result['keyword_density']} per 1000 words")
    
    if result['good_keyword_matches']:
        print(f"Good Keywords: {', '.join(result['good_keyword_matches'])}")
    
    if result['threat_hunting_matches']:
        print(f"Threat Hunting Terms: {', '.join(result['threat_hunting_matches'])}")
    
    # Check for specific new keywords
    new_keywords = ['currentversion', 'EventCode', 'lolbas', 'lolbins', 'RMM']
    found_keywords = []
    
    for keyword in new_keywords:
        if keyword in result['good_keyword_matches'] or keyword in result['threat_hunting_matches']:
            found_keywords.append(keyword)
    
    if found_keywords:
        print(f"✅ New keywords detected: {', '.join(found_keywords)}")
    else:
        print("❌ No new keywords detected")

if __name__ == "__main__":
    test_new_keywords()
