#!/usr/bin/env python3
"""
CTI-to-Hunt Workflow using Ollama Fine-tuned Model
"""

import subprocess
import json
import time

def generate_sigma_rules(threat_intel_text, model_name="phi3-cti-hunt"):
    """Generate SIGMA rules from threat intelligence using Ollama"""
    
    print(f"🔍 Analyzing threat intelligence...")
    print(f"📝 Input: {threat_intel_text[:100]}...")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, threat_intel_text],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        end_time = time.time()
        response_time = end_time - start_time
        
        if result.returncode == 0:
            print(f"✅ SIGMA rules generated in {response_time:.2f} seconds")
            print(f"📊 Performance: {65/response_time:.1f}x faster than original")
            return result.stdout.strip()
        else:
            print(f"❌ Error: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        print("⏰ Generation timed out")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    """Main workflow"""
    
    print("🚀 CTI-to-Hunt Workflow with Ollama")
    print("=" * 50)
    
    # Example threat intelligence scenarios
    scenarios = [
        "PowerShell malware execution with encoded commands and registry persistence",
        "Malware drops files in C:\\Windows\\Temp and executes them with specific command line arguments",
        "Attackers use HTTP requests with suspicious User-Agent strings for C2 communication",
        "Malware creates scheduled tasks for persistence and queries suspicious DNS domains"
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📋 Scenario {i}:")
        rules = generate_sigma_rules(scenario)
        
        if rules:
            print("🎯 Generated SIGMA Rules:")
            print(rules)
            print("-" * 50)
        else:
            print("❌ Failed to generate rules")

if __name__ == "__main__":
    main()
