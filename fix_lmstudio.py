#!/usr/bin/env python3
import re

# Read the file
with open('ab_test_web_ui.py', 'r') as f:
    content = f.read()

# Define the system prompt
system_prompt = """You are a SIGMA rule extraction assistant. 
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

Example Input: Attackers ran powershell.exe with the -enc flag. They also set persistence via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. For C2, they queried abc-malicious[.]com and used HTTP requests with User-Agent "SyncClient/2.0".

Example Output:
- logsource:
    category: process_creation
    product: windows
    service: security
  detection:
    selection:
      Image|endswith: 'powershell.exe'
      CommandLine|contains: '-enc'
    condition: selection
- logsource:
    category: registry_set
    product: windows
    service: security
  detection:
    selection:
      TargetObject|contains: 'HKCU\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run'
    condition: selection
- logsource:
    category: dns
    product: windows
    service: security
  detection:
    selection:
      QueryName|contains: 'abc-malicious[.]com'
    condition: selection
- logsource:
    category: http
    product: windows
    service: security
  detection:
    selection:
      UserAgent|contains: 'SyncClient/2.0'
    condition: selection"""

# Replace the generate_with_lmstudio function
old_function = '''def generate_with_lmstudio(prompt, max_tokens=200, temperature=0.7):
    """Generate text using LMStudio API"""
    try:
        data = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        response = requests.post(
            f"{lmstudio_base_url}/v1/chat/completions",
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LMStudio generation error: {str(e)}")
        return f"LMStudio Error: {str(e)}"'''

new_function = f'''def generate_with_lmstudio(prompt, max_tokens=200, temperature=0.7):
    """Generate text using LMStudio API"""
    try:
        system_prompt = """{system_prompt}"""
        data = {{
            "model": "phi-2",
            "messages": [
                {{"role": "system", "content": system_prompt}},
                {{"role": "user", "content": prompt}}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }}
        
        response = requests.post(
            f"{{lmstudio_base_url}}/v1/chat/completions",
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LMStudio generation error: {{str(e)}}")
        return f"LMStudio Error: {{str(e)}}"'''

# Replace the function
content = content.replace(old_function, new_function)

# Write the fixed file
with open('ab_test_web_ui.py', 'w') as f:
    f.write(content)

print("✅ Fixed LMStudio function with system prompt")
