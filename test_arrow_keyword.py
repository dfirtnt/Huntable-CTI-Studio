#!/usr/bin/env python3
"""
Quick test to verify the --> keyword detection.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.content import ThreatHuntingScorer

def test_arrow_keyword():
    """Test the --> keyword detection."""
    
    # Sample content with detection engineering patterns
    title = "Detection Rules for APT Campaign"
    content = """
    Detection engineering team has identified new patterns for APT detection:
    
    YARA Rule Example:
    rule APT_Campaign_2024 {
        strings:
            $s1 = "rundll32.exe" --> "Process execution"
            $s2 = "certutil.exe" --> "Base64 decoding"
            $s3 = "wmic.exe" --> "Lateral movement"
        condition:
            any of them
    }
    
    Sigma Rule Example:
    title: Suspicious Process Execution
    description: Detects suspicious process execution patterns
    detection:
        selection:
            ProcessName: 
                - rundll32.exe --> "DLL execution"
                - mshta.exe --> "HTA execution"
                - powershell.exe --> "PowerShell execution"
    """
    
    print("Testing --> Keyword Detection")
    print("=" * 40)
    
    result = ThreatHuntingScorer.score_threat_hunting_content(title, content)
    
    print(f"Threat Hunting Score: {result['threat_hunting_score']}/100")
    print(f"Good Keywords Found: {', '.join(result['good_keyword_matches'])}")
    
    if '-->' in result['good_keyword_matches']:
        print("✅ --> keyword detected successfully!")
    else:
        print("❌ --> keyword not detected")

if __name__ == "__main__":
    test_arrow_keyword()
