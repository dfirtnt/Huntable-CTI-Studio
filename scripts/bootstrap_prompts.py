#!/usr/bin/env python3
"""
Bootstrap prompts from files into the database.
"""
import requests
import os
import json
from pathlib import Path

api_url = os.getenv("API_URL", "http://localhost:8001")

# Load prompts from files
prompts_dir = Path(__file__).parent.parent / "src" / "prompts"
loaded_prompts = {}

# Example for CmdlineExtract
cmdline_prompt_path = prompts_dir / "CmdlineExtract"
if cmdline_prompt_path.exists():
    with open(cmdline_prompt_path, 'r') as f:
        loaded_prompts["CmdlineExtract"] = {
            "prompt": f.read(),
            "instructions": "" # Instructions are now part of the prompt JSON
        }

# Call the bootstrap API endpoint
response = requests.post(f"{api_url}/api/workflow/config/prompts/bootstrap", json={"prompts": loaded_prompts})
print(f"Bootstrap response: {response.status_code}")
print(response.text)

