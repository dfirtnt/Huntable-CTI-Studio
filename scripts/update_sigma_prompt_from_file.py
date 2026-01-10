#!/usr/bin/env python3
"""Update SigmaAgent prompt in database from file."""

import sys
import json
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

api_url = "http://127.0.0.1:8001"

def update_sigma_prompt():
    """Update SigmaAgent prompt from file to database."""
    prompts_dir = project_root / "src" / "prompts"
    sigma_prompt_path = prompts_dir / "sigma_generation.txt"
    
    if not sigma_prompt_path.exists():
        print(f"❌ Prompt file not found: {sigma_prompt_path}")
        return False
    
    # Read prompt from file
    with open(sigma_prompt_path, 'r', encoding='utf-8') as f:
        prompt_content = f.read().strip()
    
    print(f"📄 Loaded prompt from file ({len(prompt_content)} chars)")
    
    # Update via API
    prompt_data = {
        "agent_name": "SigmaAgent",
        "prompt": prompt_content,
        "instructions": "",
        "change_description": "Updated from sigma_generation.txt file"
    }
    
    try:
        response = requests.put(
            f"{api_url}/api/workflow/config/prompts",
            json=prompt_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.ok:
            result = response.json()
            print(f"✅ Successfully updated SigmaAgent prompt in database")
            print(f"   Config version: {result.get('version', 'N/A')}")
            return True
        else:
            error = response.json()
            print(f"❌ Error updating prompt: {error.get('detail', 'Unknown error')}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {api_url}")
        print("   Make sure the web server is running")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    success = update_sigma_prompt()
    sys.exit(0 if success else 1)
