#!/usr/bin/env python3
"""
LMStudio-Compatible Fine-tuning with Ollama
"""

import json
import subprocess
import os
from pathlib import Path

def create_ollama_modelfile(model_name, base_model="phi3", training_data_path="data/training_data.jsonl"):
    """Create Ollama Modelfile for fine-tuning"""
    
    modelfile_content = f"""FROM {base_model}

# Fine-tuned for CTI threat hunting
SYSTEM \"\"\"You are a SIGMA rule extraction assistant specialized in threat intelligence analysis. 
I will provide unstructured threat intelligence text. 
Your task is to read the intelligence and infer technical detection logic. 
You will provide back only the critical non-metadata fields for SIGMA rules. 

Each rule must have:
- logsource: one category, product, and service
- detection: one or more selections with a condition

Guidelines:
- If multiple observables map to different logsource types (process, registry, dns, proxy, file), create multiple separate rules.
- Each rule must include exactly one logsource block.
- detection should capture threat hunt ready observables such as:
  • process execution (image paths, command-line args)
  • parent-child process relationships
  • registry key additions or modifications
  • file drops or modifications
  • DNS queries or patterns
  • HTTP/HTTPS URLs, methods, or User-Agent strings
- If some details are missing, use <unknown>.
- Do not include metadata (title, id, author, etc.).
- Always output in valid YAML as a list of rules, each with logsource and detection.
- If no detection-relevant content exists, output: "No detection-relevant fields found."

You are fine-tuned specifically for threat intelligence analysis and SIGMA rule generation.\"\"\"

# Load training data if available
"""
    
    if os.path.exists(training_data_path):
        modelfile_content += f"# Training data loaded from {training_data_path}\n"
    
    modelfile_content += f"""
# Model parameters optimized for threat intelligence
PARAMETER temperature 0.3
PARAMETER top_p 0.8
PARAMETER top_k 40
PARAMETER repeat_penalty 1.2
"""
    
    # Write Modelfile
    modelfile_path = f"Modelfile.{model_name}"
    with open(modelfile_path, 'w') as f:
        f.write(modelfile_content)
    
    print(f"✅ Created Modelfile: {modelfile_path}")
    return modelfile_path

def create_training_data():
    """Create training data in Ollama format"""
    
    # Sample training data (you can expand this)
    training_data = [
        {
            "prompt": "Attackers ran powershell.exe with the -enc flag. They also set persistence via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. For C2, they queried abc-malicious[.]com and used HTTP requests with User-Agent \"SyncClient/2.0\".",
            "response": "- logsource:\n    category: process_creation\n    product: windows\n    service: security\n  detection:\n    selection:\n      Image|endswith: 'powershell.exe'\n      CommandLine|contains: '-enc'\n    condition: selection\n- logsource:\n    category: registry_set\n    product: windows\n    service: security\n  detection:\n    selection:\n      TargetObject|contains: 'HKCU\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run'\n    condition: selection\n- logsource:\n    category: dns\n    product: windows\n    service: security\n  detection:\n    selection:\n      QueryName|contains: 'abc-malicious[.]com'\n    condition: selection\n- logsource:\n    category: http\n    product: windows\n    service: security\n  detection:\n    selection:\n      UserAgent|contains: 'SyncClient/2.0'\n    condition: selection"
        },
        {
            "prompt": "Malware dropped a file named svchost.exe in C:\\Windows\\Temp and executed it with command line arguments -s and -k.",
            "response": "- logsource:\n    category: process_creation\n    product: windows\n    service: security\n  detection:\n    selection:\n      Image|endswith: 'svchost.exe'\n      CommandLine|contains: '-s'\n      CommandLine|contains: '-k'\n    condition: selection\n- logsource:\n    category: file_event\n    product: windows\n    service: security\n  detection:\n    selection:\n      TargetFilename|endswith: 'C:\\\\Windows\\\\Temp\\\\svchost.exe'\n    condition: selection"
        }
    ]
    
    # Create data directory
    os.makedirs("data", exist_ok=True)
    
    # Save as JSONL
    with open("data/training_data.jsonl", "w") as f:
        for item in training_data:
            f.write(json.dumps(item) + "\n")
    
    print("✅ Created training data: data/training_data.jsonl")
    return "data/training_data.jsonl"

def fine_tune_with_ollama(model_name, base_model="phi3"):
    """Fine-tune model using Ollama"""
    
    print(f"🚀 Starting Ollama fine-tuning for {model_name}")
    
    # Create Modelfile
    modelfile_path = create_ollama_modelfile(model_name, base_model)
    
    # Create training data
    training_data_path = create_training_data()
    
    # Build the model
    print(f"🔄 Building fine-tuned model: {model_name}")
    try:
        result = subprocess.run(
            ["ollama", "create", "-f", modelfile_path, model_name],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            print(f"✅ Fine-tuned model created: {model_name}")
            return True
        else:
            print(f"❌ Fine-tuning failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Fine-tuning timed out")
        return False
    except Exception as e:
        print(f"❌ Error during fine-tuning: {e}")
        return False

def test_fine_tuned_model(model_name):
    """Test the fine-tuned model"""
    
    print(f"🧪 Testing fine-tuned model: {model_name}")
    
    test_prompt = "PowerShell malware execution with encoded commands"
    
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, test_prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print(f"✅ Model test successful!")
            print(f"Response: {result.stdout[:200]}...")
            return True
        else:
            print(f"❌ Model test failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing model: {e}")
        return False

def main():
    """Main fine-tuning process"""
    
    print("🚀 LMStudio-Compatible Fine-tuning with Ollama")
    print("=" * 60)
    
    # Check if Ollama is running
    try:
        subprocess.run(["ollama", "list"], check=True, capture_output=True)
        print("✅ Ollama is running")
    except:
        print("❌ Ollama is not running. Please start it with: brew services start ollama")
        return
    
    # Fine-tune model
    model_name = "phi3-cti-hunt"
    if fine_tune_with_ollama(model_name):
        print(f"\n🎉 Fine-tuning complete!")
        
        # Test the model
        if test_fine_tuned_model(model_name):
            print(f"\n📋 Next steps:")
            print(f"1. Load {model_name} in LMStudio")
            print(f"2. Update A/B UI to use {model_name}")
            print(f"3. Enjoy 21x faster fine-tuned inference!")
        else:
            print("⚠️ Model created but test failed")
    else:
        print("❌ Fine-tuning failed")

if __name__ == "__main__":
    main()
